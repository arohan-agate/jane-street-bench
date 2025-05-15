#!/usr/bin/env python
# eval_reasoning.py
# -------------------------------------------------
# Requires: openai, pandas, pillow, python-dotenv
# Run:      python eval_reasoning.py
# -------------------------------------------------

import base64, io, json, pathlib
from datetime import datetime as dt

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

PUZZLE_ID   = 61
CSV_PATH    = "data/puzzles/puzzles.csv"
MODEL       = "o3-mini"                        # OpenAI advanced reasoning model
OUT_JSON    = "results_o3-mini_single_cross.json"
IMG_MAX_PX  = 600
IMG_QUALITY = 70

# 1) Auth -----------------------------------------------------------------
load_dotenv()
client = OpenAI()

# 2) Load puzzle ----------------------------------------------------------
df = pd.read_csv(CSV_PATH).set_index("id")
if PUZZLE_ID not in df.index:
    raise ValueError(f"Puzzle id {PUZZLE_ID} not found in {CSV_PATH}")

row  = df.loc[PUZZLE_ID]
text = str(row["puzzleText"]).strip()
name = row["name"]

# 3) Optional image -------------------------------------------------------
def jpeg_b64(path: pathlib.Path) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((IMG_MAX_PX, IMG_MAX_PX))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=IMG_QUALITY)
        return base64.b64encode(buf.getvalue()).decode()

img_part = None
if row.get("hasImage", False):
    for ext in ("png", "jpg", "jpeg", "PNG", "JPG"):
        p = pathlib.Path(f"data/puzzles/puzzle_images/{name}/0_0.{ext}")
        if p.exists():
            img_part = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64(p)}"}
            }
            break

# 4) Build prompt ---------------------------------------------------------
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

# 5) Call model -----------------------------------------------------------
response = client.chat.completions.create(
    model="o3-mini",
    messages=messages,
    # temperature=0.25,
    # o3-mini parameter names
    max_completion_tokens=250,   # instead of max_tokens
    # max_prompt_tokens=8000,     # optional safety cap
)


answer_text = response.choices[0].message.content.strip()
usage       = response.usage

print("\n=== o3-mini OUTPUT ===\n")
print(answer_text)
print("\nToken usage:", usage)

# 6) Save -----------------------------------------------------------------
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
pathlib.Path(OUT_JSON).write_text(json.dumps(record, indent=2))
print(f"\nResult saved to {OUT_JSON}")
