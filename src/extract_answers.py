#!/usr/bin/env python
# extract_answers.py
# --------------------------------------------
# deps: openai, pandas, pillow, python-dotenv

import base64
import io
import json
import re
import time
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from PIL import Image

# ------------- CONFIG -----------------------
BASE        = Path(__file__).resolve().parent.parent
CSV_IN      = BASE / "data" / "puzzles" / "puzzles.csv"
CSV_OUT     = BASE / "data" / "puzzles" / "puzzles_with_answers.csv"
MODEL       = "gpt-4o-mini"
FIXED_PAUSE = 3.0               # seconds between calls
JPEG_PX     = 600
JPEG_Q      = 70                # jpeg quality
# --------------------------------------------

load_dotenv()
client = OpenAI()

# helper to encode images
def jpeg_b64(path: Path, max_px=JPEG_PX, q=JPEG_Q) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=q)
        return base64.b64encode(buf.getvalue()).decode()

# build messages for solution extraction
def build_prompt(sol_text: str, img_path: Path | None):
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

# Load CSV and prepare column
df = pd.read_csv(CSV_IN)
if "answer" not in df.columns:
    df["answer"] = pd.NA

# regex for retry delay extraction
retry_re = re.compile(r"in (\d+)ms")

def get_retry_seconds(err: RateLimitError, default=10) -> float:
    m = retry_re.search(str(err))
    return (int(m.group(1)) / 1000 + 0.5) if m else default

# Ensure output directory exists
CSV_OUT.parent.mkdir(parents=True, exist_ok=True)

# Iterate puzzles
for idx, row in df.iterrows():
    # skip if no solution available
    if not row.get("hasSolution", False):
        continue
    # skip if already filled
    if pd.notna(row["answer"]):
        continue

    sol_text = str(row.get("solutionText", "")).strip()
    img_path = None
    if row.get("solutionHasImages", False):
        name = row["name"]
        for ext in ("png", "jpg", "jpeg", "PNG", "JPG"):
            p = BASE / "data" / "puzzles" / "solution_images" / name / f"0_0.{ext}"
            if p.exists():
                img_path = p
                break

    messages = build_prompt(sol_text, img_path)

    # call until success or non-retriable error
    while True:
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=50,
            )
            ans = resp.choices[0].message.content.strip()
            df.at[idx, "answer"] = ans
            print(f"[{dt.now().strftime('%H:%M:%S')}] ✔ id={row['id']} → {ans}")
            break
        except RateLimitError as e:
            wait = get_retry_seconds(e)
            print(f"↳ 429 hit; sleeping {wait:.2f}s")
            time.sleep(wait)
        except Exception as e:
            print(f"[{dt.now().strftime('%H:%M:%S')}] ✘ id={row['id']}  ({e})")
            df.at[idx, "answer"] = f"ERROR: {e}"
            break

    # incremental save and pause
    df.to_csv(CSV_OUT, index=False)
    time.sleep(FIXED_PAUSE)

print(f"\nAll done! Answers written to {CSV_OUT}")
