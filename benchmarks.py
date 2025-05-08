#!/usr/bin/env python
# benchmark_answers_only.py
# Save as:  python benchmark_answers_only.py
# ------------------------------------------
# deps: openai, pandas, pillow, python-dotenv

import base64, io, json, pathlib, time
from datetime import datetime as dt

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

MODEL          = "gpt-4o-mini"
ATTEMPTS       = [0.25, 0.30]
CSV_PATH       = "data/puzzles/puzzles.csv"
OUT_PATH       = pathlib.Path("results_gpt-4o-mini.json")
RATE_SLEEP_SEC = 1.5


load_dotenv()
client = OpenAI()
df = pd.read_csv(CSV_PATH)

# compress image to JPEG and base64 encode
def jpeg_b64(path, max_px=600, quality=70):
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode()

# build messages for the API call
def build_messages(record):
    text = record["puzzleText"]
    name = record["name"]

    img_part = None
    if record["hasImage"]:
        for ext in ("png", "jpg", "jpeg", "PNG", "JPG"):
            p = pathlib.Path(f"data/puzzles/puzzle_images/{name}/0_0.{ext}")
            if p.exists():
                b64 = jpeg_b64(p)
                img_part = {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                }
                break

    system_msg = {
        "role": "system",
        "content": (
            "You are an expert Jane Street puzzle solver. "
            "Given the puzzle (and possibly a diagram), output ONLY the final "
            "numeric or textual answer—no explanation, no steps, no extra words."
        ),
    }

    user_content = [{"type": "text", "text": text}]
    if img_part:
        user_content.append(img_part)

    user_msg = {"role": "user", "content": user_content}
    return [system_msg, user_msg]

# load existing results if available
if OUT_PATH.exists():
    results = json.loads(OUT_PATH.read_text())
else:
    results = {}

# iterate over puzzles and make API calls
for _, row in df.iterrows():
    pid = str(int(row["id"]))
    if pid in results and len(results[pid]["answers"]) == len(ATTEMPTS):
        continue

    messages = build_messages(row)
    answers_list = results.get(pid, {"name": row["name"], "answers": []})["answers"]

    for idx, temp in enumerate(ATTEMPTS, start=1):
        if any(a["attempt"] == idx for a in answers_list):
            continue

        print(f"{dt.now().time()}  Puzzle {pid}  attempt {idx}")

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=temp,
                max_tokens=200,
            )
            choice = resp.choices[0]
            answer_text = choice.message.content.strip()

            answers_list.append({
                "attempt": idx,
                "temperature": temp,
                "answer": answer_text,
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            })

        except Exception as e:
            answers_list.append({
                "attempt": idx,
                "temperature": temp,
                "error": str(e),
            })

        results[pid] = {"name": row["name"], "answers": answers_list}
        OUT_PATH.write_text(json.dumps(results, indent=2))

        time.sleep(RATE_SLEEP_SEC)

print("\nBenchmark complete. Results written to", OUT_PATH)
