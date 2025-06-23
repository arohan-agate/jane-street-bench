#!/usr/bin/env python
# evaluate_curr_month.py
# --------------------------------------------
# deps: openai, anthropic, google-generativeai, pandas, pillow, python-dotenv
#
# Reads models from models.txt, skips any already in curr_month_solutions.json,
# sends the current month's puzzle (row 0 of puzzles.csv) to each new model with two
# different temperatures as “attempts”, asks for very brief reasoning + final answer,
# and writes the merged outputs to results/curr_month_solutions.json
# --------------------------------------------

import os
import base64
import io
import json
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv, find_dotenv
from PIL import Image

# ---------- CONFIG -------------------------------------------------------
BASE_DIR       = Path(__file__).resolve().parent.parent
MODELS_FILE    = BASE_DIR / "models.txt"
CSV_PATH       = BASE_DIR / "data" / "puzzles" / "puzzles.csv"
RESULTS_DIR    = BASE_DIR / "results"
OUT_PATH       = RESULTS_DIR / "curr_month_solutions.json"
IMG_MAX_PX     = 600
JPEG_Q         = 70

# We will send two attempts at different temperatures
ATTEMPTS = [
    {"attempt": 1, "temperature": 0.25},
    {"attempt": 2, "temperature": 0.30},
]

MAX_TOKENS = 600  # For models that require max_tokens / max_output_tokens

# Load API keys from .env
load_dotenv(find_dotenv())

# ---------- HELPERS ------------------------------------------------------
def jpeg_b64(path: Path) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((IMG_MAX_PX, IMG_MAX_PX))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_Q)
        return base64.b64encode(buf.getvalue()).decode()

def classify_provider(model_name: str) -> str:
    ml = model_name.lower()
    if ml.startswith(("gpt-","o4-","o3-")):
        return "openai"
    if ml.startswith("claude-"):
        return "anthropic"
    if ml.startswith("gemini-"):
        return "gemini"
    raise ValueError(f"Cannot infer provider for model '{model_name}'")

def build_msgs_openai(text, name, has_image):
    img_part = None
    if has_image:
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            p = BASE_DIR/"data"/"puzzles"/"puzzle_images"/name/f"0_0.{ext}"
            if p.exists():
                img_part = {
                    "type":"image_url",
                    "image_url":{"url":f"data:image/jpeg;base64,{jpeg_b64(p)}"}
                }
                break
    system = {"role":"system","content":
        "You are an expert Jane Street puzzle solver. Provide a very brief reasoning (2–3 sentences) and then the final answer."}
    user = [{"type":"text","text":text}]
    if img_part: user.append(img_part)
    return [system, {"role":"user","content":user}]

def build_msgs_anthropic(text, name, has_image):
    img_part = None
    if has_image:
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            p = BASE_DIR/"data"/"puzzles"/"puzzle_images"/name/f"0_0.{ext}"
            if p.exists():
                img_part = {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":jpeg_b64(p)}}
                break
    system = "You are an expert Jane Street puzzle solver. Provide a very brief reasoning (2–3 sentences) and then the final answer."
    parts = [{"type":"text","text":text}]
    if img_part: parts.append(img_part)
    return system, parts

def build_msgs_gemini(text, name, has_image):
    pil_img = None
    if has_image:
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            p = BASE_DIR/"data"/"puzzles"/"puzzle_images"/name/f"0_0.{ext}"
            if p.exists():
                pil_img = Image.open(p)
                break
    prompt = ("You are an expert Jane Street puzzle solver. Provide a very brief reasoning (2–3 sentences) and then the final answer.\n\n" + text)
    return [prompt, pil_img] if pil_img else [prompt]

# ---------- MAIN ---------------------------------------------------------
def main():
    # 1) Load existing results (if any) to skip already‐done
    if OUT_PATH.exists():
        final_output = json.loads(OUT_PATH.read_text())
    else:
        final_output = {}

    # 2) Read models.txt
    if not MODELS_FILE.exists():
        print(f"[ERROR] {MODELS_FILE} not found."); return
    with open(MODELS_FILE) as mf:
        all_models = [m.strip() for m in mf if m.strip()]

    # 3) Load current puzzle (row 0)
    df = pd.read_csv(CSV_PATH)
    if df.empty:
        print("[ERROR] puzzles.csv is empty."); return
    row = df.iloc[0]
    text = str(row["puzzleText"]).strip()
    name = row["name"]
    has_image = bool(row.get("hasImage", False))

    # 4) Evaluate new models
    for model_name in all_models:
        if model_name in final_output:
            print(f"[SKIP] {model_name}: already evaluated.")
            continue
        try:
            provider = classify_provider(model_name)
        except ValueError as e:
            print(f"[SKIP] {model_name}: {e}")
            continue

        print(f"\n→ Querying {provider.upper()} model '{model_name}' …")
        answers = []
        for att in ATTEMPTS:
            entry = {"attempt": att["attempt"], "temperature": att["temperature"], "answer": None, "usage": {}, "error": None}
            try:
                if provider == "openai":
                    from openai import OpenAI
                    client = OpenAI()
                    msgs = build_msgs_openai(text, name, has_image)
                    kwargs = {"model":model_name, "messages":msgs}
                    if not model_name.startswith(("o4-","o3-")):
                        kwargs.update({"temperature":att["temperature"], "max_tokens":MAX_TOKENS})
                    resp = client.chat.completions.create(**kwargs)
                    entry["answer"] = resp.choices[0].message.content.strip()
                    entry["usage"] = {"prompt_tokens":resp.usage.prompt_tokens,
                                      "completion_tokens":resp.usage.completion_tokens,
                                      "total_tokens":resp.usage.total_tokens}

                elif provider == "anthropic":
                    import anthropic
                    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                    system, parts = build_msgs_anthropic(text, name, has_image)
                    resp = client.messages.create(model=model_name, system=system,
                                                  messages=[{"role":"user","content":parts}],
                                                  temperature=att["temperature"], max_tokens=MAX_TOKENS)
                    entry["answer"] = resp.content[0].text.strip()
                    entry["usage"] = {"input_tokens":resp.usage.input_tokens,
                                      "output_tokens":resp.usage.output_tokens,
                                      "total_tokens":resp.usage.input_tokens+resp.usage.output_tokens}

                else:  # gemini
                    import google.generativeai as genai
                    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                    client = genai.GenerativeModel(f"models/{model_name}")
                    contents = build_msgs_gemini(text, name, has_image)
                    cfg = genai.types.GenerationConfig(temperature=att["temperature"], max_output_tokens=MAX_TOKENS)
                    resp = client.generate_content(contents=contents, generation_config=cfg)
                    entry["answer"] = getattr(resp, "text", "").strip() or "[ERROR]"
                    meta = getattr(resp, "usage_metadata", None)
                    if meta:
                        entry["usage"] = {"prompt_token_count":meta.prompt_token_count,
                                          "candidates_token_count":meta.candidates_token_count,
                                          "total_token_count":meta.total_token_count}
            except Exception as e:
                entry["error"] = str(e)
            answers.append(entry)

        final_output[model_name] = {"model":model_name, "answers":answers}

    # 5) Write merged results
    RESULTS_DIR.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(final_output, indent=2))
    print(f"\nWrote merged results to {OUT_PATH}")

if __name__ == "__main__":
    main()
