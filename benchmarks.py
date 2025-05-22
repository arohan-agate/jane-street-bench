#!/usr/bin/env python
# benchmarks.py – regenerate remaining answers, skip existing, zero 429s
# --------------------------------------------------
# deps: openai, pandas, pillow, python-dotenv
# --------------------------------------------------

import base64, io, json, pathlib, re, time, collections
from datetime import datetime as dt

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from PIL import Image

# ---------- CONFIG -------------------------------------------------------
MODEL           = "gpt-4o-mini"
ATTEMPTS        = [0.25, 0.30]
CSV_PATH        = "data/puzzles/puzzles.csv"
OUT_PATH        = pathlib.Path("results_gpt-4o-mini.json")
TPM_LIMIT       = 200_000            # tokens-per-minute quota
COMPLETION_MAX  = 200                # max tokens the model can emit
IMG_MAX_PX      = 600
JPEG_Q          = 70
RETRY_CUSHION_S = 0.3                # cushion after server hint

# ---------- AUTH & DATA -------------------------------------------------
load_dotenv()
client = OpenAI()
df = pd.read_csv(CSV_PATH)

bucket = collections.deque()         # (timestamp, tokens) in last 60s
retry_re = re.compile(r"in (\d+)ms")

# ---------- HELPERS -----------------------------------------------------
def jpeg_b64(path: pathlib.Path) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((IMG_MAX_PX, IMG_MAX_PX))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_Q)
        return base64.b64encode(buf.getvalue()).decode()


def build_msgs(rec):
    text = rec["puzzleText"]
    name = rec["name"]
    img_part = None
    if rec["hasImage"]:
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            p = pathlib.Path(f"data/puzzles/puzzle_images/{name}/0_0.{ext}")
            if p.exists():
                img_part = {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64(p)}"}
                }
                break
    system = {
        "role": "system",
        "content": (
            "You are an expert Jane Street puzzle solver. "
            "Return ONLY the final numeric or textual answer—no explanation."
        )
    }
    user_parts = [{"type": "text", "text": text}]
    if img_part:
        user_parts.append(img_part)
    return [system, {"role": "user", "content": user_parts}]


def rough_tokens(msgs):
    # Approximate: 1 token ≈ 4 characters
    chars = 0
    for m in msgs:
        content = m["content"]
        if isinstance(content, list):
            for part in content:
                txt = part.get("text") or part.get("image_url", {}).get("url", "")
                chars += len(txt)
        else:
            chars += len(content)
    return chars // 4 + 1


def wait_quota(needed):
    now = time.time()
    while bucket and now - bucket[0][0] > 60:
        bucket.popleft()
    used = sum(t for _, t in bucket)
    if used + needed > TPM_LIMIT:
        time.sleep(60 - (now - bucket[0][0]) + 0.2)


def safe_call(**kwargs):
    while True:
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            m = retry_re.search(str(e))
            wait = int(m.group(1)) / 1000 if m else 1.0
            time.sleep(wait + RETRY_CUSHION_S)


def needs_rerun(ans_list, attempt_no):
    for a in ans_list:
        if a.get("attempt") == attempt_no and a.get("answer", "").strip():
            return False
    return True

# ---------- LOAD EXISTING RESULTS ----------------------------------------
if OUT_PATH.exists():
    results = json.loads(OUT_PATH.read_text())
else:
    results = {}

# ---------- MAIN LOOP ---------------------------------------------------
for _, row in df.iterrows():
    pid = str(int(row["id"]))
    answers = results.get(pid, {"name": row["name"], "answers": []})["answers"]

    # Skip if puzzleText is missing or not a string
    if not isinstance(row.get("puzzleText"), str):
        print(f"Skipping puzzle {pid}: no text")
        continue

    # Skip entire puzzle if both attempts are done
    if pid in results and not any(needs_rerun(answers, idx) for idx in range(1, len(ATTEMPTS)+1)):
        continue

    msgs = build_msgs(row)
    try:
        p_tok = rough_tokens(msgs)
    except Exception:
        print(f"Skipping puzzle {pid}: token estimation failed")
        continue

    for idx, temp in enumerate(ATTEMPTS, start=1):
        if not needs_rerun(answers, idx):
            continue

        wait_quota(p_tok + COMPLETION_MAX)
        print(f"{dt.now().time()}  Puzzle {pid}  attempt {idx}")

        resp = safe_call(
            model=MODEL,
            messages=msgs,
            temperature=temp,
            max_tokens=COMPLETION_MAX,
        )
        bucket.append((time.time(), resp.usage.total_tokens))

        entry = {
            "attempt": idx,
            "temperature": temp,
            "answer": resp.choices[0].message.content.strip(),
            "prompt_tokens": resp.usage.prompt_tokens or 0,
            "completion_tokens": resp.usage.completion_tokens or 0,
            "total_tokens": resp.usage.total_tokens or 0,
        }
        # replace any existing for this attempt
        answers = [a for a in answers if a.get("attempt") != idx] + [entry]
        results[pid] = {"name": row["name"], "answers": answers}
        OUT_PATH.write_text(json.dumps(results, indent=2))

print("\nBenchmark complete. Results written to", OUT_PATH)
