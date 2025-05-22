#!/usr/bin/env python
# eval_reasoning.py
# -------------------------------------------------
# Requires: openai, pandas, pillow, python-dotenv
# Run:      python src/eval_reasoning.py
# -------------------------------------------------

import base64
import io
import json
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

# ---------- CONFIG -------------------------------------------------------
BASE        = Path(__file__).resolve().parent.parent
PUZZLE_ID   = 61
CSV_PATH    = BASE / "data" / "puzzles" / "puzzles.csv"
MODEL       = "o3-mini"                        # OpenAI advanced reasoning model
OUT_JSON    = BASE / "results" / "results_o3-mini_single_cross.json"
IMG_MAX_PX  = 600
IMG_QUALITY = 70

# ---------- AUTH -----------------------------------------------------------------
load_dotenv()
client = OpenAI()

# ---------- LOAD puzzle ----------------------------------------------------------
df = pd.read_csv(CSV_PATH).set_index("id")
if PUZZLE_ID not in df.index:
    raise ValueError(f"Puzzle id {PUZZLE_ID} not found in {CSV_PATH}")

row  = df.loc[PUZZLE_ID]
text = str(row["puzzleText"]).strip()
name = row["name"]

# ---------- Optional image -------------------------------------------------------

def jpeg_b64(path: Path) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((IMG_MAX_PX, IMG_MAX_PX))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=IMG_QUALITY)
        return base64.b64encode(buf.getvalue()).decode()

img_part = None
if row.get("hasImage", False):
    for ext in ("png", "jpg", "jpeg", "PNG", "JPG"):
        p = BASE / "data" / "puzzles" / "puzzle_images" / name / f"0_0.{ext}"
        if p.exists():
            img_part = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64(p)}"}
            }
            break

# ---------- Build prompt ---------------------------------------------------------
system_msg = {
    "role": "system",
    "content": (
        "You are an expert puzzle solver. "
        "Provide the final answer followed by a clear, step-by-step reasoning path. "
        "Label the sections 'Answer:' and 'Reasoning:' respectively."
    ),
}

user_parts = [{"type": "text", "text": text}]
if img_part:
    user_parts.append(img_part)

user_msg = {"role": "user", "content": user_parts}
messages = [system_msg, user_msg]

# ---------- Call model -----------------------------------------------------------
response = client.chat.completions.create(
    model=MODEL,
    messages=messages,
    # temperature=0.25,
    max_completion_tokens=250,   # instead of max_tokens
)

answer_text = response.choices[0].message.content.strip()
usage       = response.usage

print("\n=== o3-mini OUTPUT ===\n")
print(answer_text)
print("\nToken usage:", usage)

# ---------- Save -----------------------------------------------------------------
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
record = {
    "timestamp": dt.utcnow().isoformat(),
    "puzzle_id": PUZZLE_ID,
    "name"     : name,
    "model"    : MODEL,
    "answer"   : answer_text,
    "usage"    : {
        "prompt_tokens"    : usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens"     : usage.total_tokens,
    },
}
OUT_JSON.write_text(json.dumps(record, indent=2))
print(f"\nResult saved to {OUT_JSON}")
