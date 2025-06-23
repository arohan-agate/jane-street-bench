# Runs benchmarks on reasoning models from OpenAI, Anthropic, and Gemini.
# Produces one JSON results file per model in ./results/.
#
# Usage:
#   1. Populate .env with OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY.
#   2. (Optional) Test mode
#   3. Run:
#        python src/benchmark_reasoning.py
#
# This will generate (in project_root/results/):
#   - results_o4-mini.json
#   - results_claude-3-opus-20240229.json
#   - results_gemini-1.5-pro.json
#
# Dependencies: openai, anthropic, google-generativeai, pandas, pillow, python-dotenv
# --------------------------------------------

import os
import base64
import io
import json
import pathlib
import re
import time
import collections
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv, find_dotenv
from PIL import Image

#  CONFIG 
BASE            = Path(__file__).resolve().parent.parent
CSV_PATH        = BASE / "data" / "puzzles" / "puzzles.csv"
IMG_MAX_PX      = 600
JPEG_Q          = 70
RETRY_CUSHION   = 0.3

PROVIDERS = [
    "openai",      #  o4-mini-2025-04-16
    # "anthropic",   #  claude-3-opus-20240229
    # "gemini",      #  gemini-1.5-pro
]

# Testing without API calls, set TEST_MODE=1
TEST_MODE = 0

# MODEL CONFIG 
MODEL_MAP = {
    "openai":  "o3-2025-04-16" #"o3-2025-04-16",
    # "anthropic": "claude-3-opus-20240229",
    # "gemini":   "gemini-1.5-pro",
}

OUTFILE_MAP = {
    "openai":    BASE / "results" / "results_o3-2025-04-16.json",
    # "anthropic": BASE / "results" / "results_claude-3-opus-20240229.json",
    # "gemini":    BASE / "results" / "results_gemini-1.5-pro.json",
}

# Two temperature one for each run:
ATTEMPTS = [0.25, 0.30]

TPM_LIMIT   = 200_000  
RPM_LIMIT   = 1000     
COMPLETION_MAX = 200   

#  AUTH / CLIENT SETUP 
load_dotenv(find_dotenv())

# Preload the full puzzle df:
df = pd.read_csv(CSV_PATH)

#  HELPERS 
def jpeg_b64(path: pathlib.Path) -> str:
    """Read an image, downsize to IMG_MAX_PX, and return a base64‐encoded JPEG."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((IMG_MAX_PX, IMG_MAX_PX))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_Q)
        return base64.b64encode(buf.getvalue()).decode()


def build_msgs_openai(rec):
    """Construct OpenAI‐style chat message list."""
    text = rec["puzzleText"]
    name = rec["name"]
    img_part = None
    if rec.get("hasImage", False):
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            p = BASE / "data" / "puzzles" / "puzzle_images" / name / f"0_0.{ext}"
            if p.exists():
                b64 = jpeg_b64(p)
                img_part = {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                }
                break

    system = {"role": "system",
              "content": "You are an expert Jane Street puzzle solver. Return ONLY the final numeric or textual answer—no explanation."}
    user_parts = [{"type": "text", "text": text}]
    if img_part:
        user_parts.append(img_part)

    return [system, {"role": "user", "content": user_parts}]


def build_msgs_anthropic(rec):
    """Construct Anthropic‐style (system_str, parts_list)."""
    text = rec["puzzleText"]
    name = rec["name"]
    img_part = None
    if rec.get("hasImage", False):
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            p = BASE / "data" / "puzzles" / "puzzle_images" / name / f"0_0.{ext}"
            if p.exists():
                b64 = jpeg_b64(p)
                img_part = {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
                }
                break

    system_txt = "You are an expert Jane Street puzzle solver. Return ONLY the final numeric or textual answer—no explanation."
    parts = [{"type": "text", "text": text}]
    if img_part:
        parts.append(img_part)

    return system_txt, parts


def build_msgs_gemini(rec):
    """Construct Gemini prompt: a list of strings/PIL.Image."""
    text = rec["puzzleText"]
    name = rec["name"]
    pil_img = None
    if rec.get("hasImage", False):
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            p = BASE / "data" / "puzzles" / "puzzle_images" / name / f"0_0.{ext}"
            if p.exists():
                pil_img = Image.open(p)
                break

    prompt = "You are an expert Jane Street puzzle solver. Return ONLY the final numeric or textual answer—no explanation.\n\n" + text
    if pil_img:
        return [prompt, pil_img]
    else:
        return [prompt]


def rough_tokens_openai(messages):
    """Estimate OpenAI tokens as roughly len(chars)/4 + 1."""
    chars = 0
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, list):
            for part in c:
                text = part.get("text", "") or part.get("image_url", {}).get("url", "")
                chars += len(text)
        else:
            if isinstance(c, str):
                chars += len(c)
    return chars // 4 + 1


def wait_quota_openai(needed):
    """Block until at least `needed` tokens are available under TPM_LIMIT."""
    now = time.time()
    while bucket and now - bucket[0][0] > 60:
        bucket.popleft()
    used = sum(tokens for _, tokens in bucket)
    if used + needed > TPM_LIMIT:
        time.sleep(60 - (now - bucket[0][0]) + 0.2)


def wait_quota_requests(bucket, limit):
    """Block until there's capacity under limit requests/minute."""
    now = time.time()
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        time.sleep(60 - (now - bucket[0]) + 0.2)


def safe_call_openai(client, **kw):
    from openai import RateLimitError
    while True:
        try:
            return client.chat.completions.create(**kw)
        except RateLimitError as e:
            m = re.search(r"in (\d+)ms", str(e))
            wait = (int(m.group(1)) / 1000) if m else 1.0
            time.sleep(wait + RETRY_CUSHION)


def safe_call_claude(client, system_txt, parts, **kw):
    import anthropic
    while True:
        try:
            return client.messages.create(model=MODEL_MAP["anthropic"],
                                          system=system_txt,
                                          messages=[{"role": "user", "content": parts}],
                                          **kw)
        except anthropic.RateLimitError as e:
            m = re.search(r"in (\d+)ms", str(e))
            wait = (int(m.group(1)) / 1000) if m else 60.0
            time.sleep(wait + RETRY_CUSHION)


def safe_call_gemini(client, contents, **kw):
    import google.generativeai as genai
    generation_config = genai.types.GenerationConfig(
        temperature=kw.get("temperature", 0.25),
        max_output_tokens=kw.get("max_output_tokens", COMPLETION_MAX)
    )
    while True:
        try:
            return client.generate_content(contents=contents, generation_config=generation_config)
        except Exception as e:
            msg = str(e).lower()
            if any(x in msg for x in ["rate limit", "quota", "429", "exhausted"]):
                print(f"Gemini rate/quota hit; sleeping 60s…")
                time.sleep(60 + RETRY_CUSHION)
                continue
            raise


def needs_rerun(answers, attempt_no):
    """True if we have not yet stored a non‐empty answer for this attempt."""
    for a in answers:
        if a.get("attempt") == attempt_no and a.get("answer", "").strip():
            return False
    return True


#  MAIN BENCHMARK LOOP 
for PROVIDER in PROVIDERS:
    print(f"\n=== Starting benchmark for {PROVIDER.upper()} ===")

    MODEL = MODEL_MAP[PROVIDER]
    OUT_PATH = OUTFILE_MAP[PROVIDER]

    # Instantiate client and rate‐limit trackers
    if PROVIDER == "openai":
        from openai import OpenAI, RateLimitError
        client = OpenAI()
        bucket = collections.deque()
    elif PROVIDER == "anthropic":
        import anthropic
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY in .env")
        client = anthropic.Anthropic(api_key=key)
        request_bucket = collections.deque()
    else:  # PROVIDER == "gemini"
        import google.generativeai as genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Missing GEMINI_API_KEY in .env")
        genai.configure(api_key=key)
        # client is already a model instance
        client = genai.GenerativeModel(f"models/{MODEL}")
        request_bucket = collections.deque()

    # Load or initialize results
    if OUT_PATH.exists():
        results = json.loads(OUT_PATH.read_text())
    else:
        results = {}

    # Iterate over all puzzles
    for _, row in df.iterrows():
        pid = str(int(row["id"]))
        record = results.get(pid, {"name": row["name"], "answers": []})
        answers = record["answers"]

        # Skip if puzzleText missing or not a string
        if not isinstance(row.get("puzzleText"), str):
            continue

        # If all attempts done, skip
        if pid in results and not any(needs_rerun(answers, i) for i in range(1, len(ATTEMPTS) + 1)):
            continue

        # Build provider‐specific messages/prompts
        if PROVIDER == "openai":
            msgs = build_msgs_openai(row)
            try:
                p_tok = rough_tokens_openai(msgs)
            except:
                print(f"Skipping {pid}: failed token estimate")
                continue

        elif PROVIDER == "anthropic":
            system_txt, parts = build_msgs_anthropic(row)

        else:  # PROVIDER == "gemini"
            msgs = build_msgs_gemini(row)

        # Loop over attempts
        for idx, temp in enumerate(ATTEMPTS, start=1):
            if not needs_rerun(answers, idx):
                continue

            # TEST_MODE short‐circuit
            if TEST_MODE:
                print(f"{dt.now().time()}  [TEST_MODE] Puzzle {pid} attempt {idx} ({PROVIDER})")
                fake_ans = f"[{PROVIDER.upper()}‐TEST‐ANSWER]"
                answers = [a for a in answers if a.get("attempt") != idx] + [{
                    "attempt": idx,
                    "temperature": temp,
                    "answer": fake_ans,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }]
                results[pid] = {"name": row["name"], "answers": answers}
                continue

            # REAL API CALL MODE
            if PROVIDER == "openai":
                wait_quota_openai(p_tok)
                print(f"{dt.now().time()}  Puzzle {pid}  attempt {idx}")
                resp = safe_call_openai(
                    client=client,
                    model=MODEL,
                    messages=msgs,
                )
                bucket.append((time.time(), resp.usage.total_tokens))
                ans   = resp.choices[0].message.content.strip()
                usage = (resp.usage.prompt_tokens, resp.usage.completion_tokens, resp.usage.total_tokens)


            elif PROVIDER == "anthropic":
                wait_quota_requests(request_bucket, RPM_LIMIT)
                print(f"{dt.now().time()}  Puzzle {pid} attempt {idx} (Claude)")
                resp = safe_call_claude(client,
                                        system_txt,
                                        parts,
                                        temperature=temp,
                                        max_tokens=COMPLETION_MAX)
                request_bucket.append(time.time())
                ans = resp.content[0].text.strip()
                usage = (resp.usage.input_tokens,
                         resp.usage.output_tokens,
                         resp.usage.input_tokens + resp.usage.output_tokens)

            else:  # PROVIDER == "gemini"
                wait_quota_requests(request_bucket, RPM_LIMIT)
                print(f"{dt.now().time()}  Puzzle {pid} attempt {idx} (Gemini)")
                resp = safe_call_gemini(client,
                                       contents=msgs,
                                       temperature=temp,
                                       max_output_tokens=COMPLETION_MAX)
                request_bucket.append(time.time())

                try:
                    ans = resp.text.strip()
                except Exception:
                    ans = "ERROR: Cannot extract text"
                    if getattr(resp, "prompt_feedback", None):
                        bf = resp.prompt_feedback.block_reason or ""
                        ans += f" (Blocked: {bf})"
                    print(f"Warning: Puzzle {pid} attempt {idx} (Gemini) – couldn’t extract text")

                meta = getattr(resp, "usage_metadata", None)
                usage = (
                    getattr(meta, "prompt_token_count", 0),
                    getattr(meta, "candidates_token_count", 0),
                    getattr(meta, "total_token_count", 0),
                )

            # Record the single attempt
            entry = {
                "attempt": idx,
                "temperature": temp,
                "answer": ans,
                "prompt_tokens": usage[0],
                "completion_tokens": usage[1],
                "total_tokens": usage[2],
            }
            # Replace any existing attempt entry
            answers = [a for a in answers if a.get("attempt") != idx] + [entry]
            results[pid] = {"name": row["name"], "answers": answers}

        # Write out incrementally
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(results, indent=2))

    print(f"\n✓ Finished {PROVIDER.upper()} → wrote {OUT_PATH.name}")
