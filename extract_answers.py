#!/usr/bin/env python
# extract_answers.py
# --------------------------------------------
# deps: openai, pandas, pillow, python-dotenv

import base64, io, pathlib, re, time
from datetime import datetime as dt

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from PIL import Image

# ------------- CONFIG -----------------------
CSV_IN   = pathlib.Path("data/puzzles/puzzles.csv")
CSV_OUT  = pathlib.Path("data/puzzles/puzzles_with_answers.csv")
MODEL    = "gpt-4o-mini"
FIXED_PAUSE = 3.0               # seconds between calls (very safe)
JPEG_PX  = 600                  # image down-sample size
JPEG_Q   = 70                   # jpeg quality
# --------------------------------------------

load_dotenv()
client = OpenAI()

def jpeg_b64(path: pathlib.Path, max_px=JPEG_PX, q=JPEG_Q):
    with Image.open(path) as im:
        im = im.convert("RGB"); im.thumbnail((max_px, max_px))
        buf = io.BytesIO(); im.save(buf, format="JPEG", quality=q)
        return base64.b64encode(buf.getvalue()).decode()

def build_prompt(sol_text: str, img_path: pathlib.Path | None):
    system = {
        "role": "system",
        "content": (
            "You are reading official Jane Street puzzle solutions. "
            "Return ONLY the final answer (numeric or textual). "
            "No extra words, punctuation, or explanation."
        ),
    }

    user_parts = [{"type": "text", "text": sol_text.strip()}]
    if img_path:
        user_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64(img_path)}"}
        })

    return [system, {"role": "user", "content": user_parts}]

# --------- Load CSV & ensure answer col -----
df = pd.read_csv(CSV_IN)
if "answer" not in df.columns:
    df["answer"] = pd.NA

# ---------- Helper: parse retry sleep -------
retry_re = re.compile(r"in (\d+)ms")

def get_retry_seconds(err: RateLimitError, default=10):
    m = retry_re.search(str(err))
    return int(m.group(1)) / 1000 + 0.5 if m else default

# ---------- Main loop -----------------------
for idx, row in df.iterrows():
    if not row.get("hasSolution", False):
        continue                              # no official solution yet

    if pd.notna(row["answer"]):
        continue                              # already done earlier run

    sol_text = str(row.get("solutionText", "")).strip()
    img_path = None
    if row.get("solutionHasImages", False):
        name = row["name"]
        for ext in ("png", "jpg", "jpeg", "PNG", "JPG"):
            p = pathlib.Path(f"data/puzzles/solution_images/{name}/0_0.{ext}")
            if p.exists():
                img_path = p
                break

    messages = build_prompt(sol_text, img_path)

    # ---------- call with auto-retry ----------
    while True:
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=50,
            )
            answer = resp.choices[0].message.content.strip()
            df.at[idx, "answer"] = answer
            ts = dt.now().strftime("%H:%M:%S")
            print(f"[{ts}] ✔ id={row['id']} → {answer}")
            break                              # success
        except RateLimitError as e:
            wait = get_retry_seconds(e)
            print(f"↳ 429 hit; sleeping {wait:.2f}s")
            time.sleep(wait)
        except Exception as e:
            ts = dt.now().strftime("%H:%M:%S")
            print(f"[{ts}] ✘ id={row['id']}  ({e})")
            df.at[idx, "answer"] = f"ERROR: {e}"
            break                              # give up on this row

    # -------- incremental save ---------------
    df.to_csv(CSV_OUT, index=False)
    time.sleep(FIXED_PAUSE)                    # baseline pause

print("\nAll done!  Answers written to", CSV_OUT)
