#!/usr/bin/env python
# evaluate_curr_month.py
# --------------------------------------------
# deps: openai, anthropic, google-generativeai, pandas, pillow, python-dotenv
#
# Reads models from models.txt, sends the current month's puzzle (row 0
# of puzzles.csv) to each model with two different temperatures as “attempts”,
# asks for very brief reasoning + final answer, and writes the outputs to
# results/curr_month_solutions.json
# --------------------------------------------

import os
import base64
import io
import json
import re
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
ATTEMPTS       = [
    {"attempt": 1, "temperature": 0.25},
    {"attempt": 2, "temperature": 0.30},
]

MAX_TOKENS     = 600  # For models that require max_tokens / max_output_tokens

# Load API keys from .env
load_dotenv(find_dotenv())

# ---------- HELPERS ------------------------------------------------------
def jpeg_b64(path: Path) -> str:
    """Load an image file, downsize it, and return a base64‐encoded JPEG string."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((IMG_MAX_PX, IMG_MAX_PX))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_Q)
        return base64.b64encode(buf.getvalue()).decode()

def classify_provider(model_name: str) -> str:
    """
    Simple heuristic to pick provider based on model_name prefix.
    Returns one of: "openai", "anthropic", or "gemini".
    """
    ml = model_name.lower()
    if ml.startswith("gpt-") or ml.startswith("o4-"):
        return "openai"
    if ml.startswith("claude-"):
        return "anthropic"
    if ml.startswith("gemini-"):
        return "gemini"
    raise ValueError(f"Cannot infer provider for model '{model_name}'")

def build_msgs_openai(puzzle_text: str, puzzle_name: str, has_image: bool):
    """
    Build an OpenAI‐compatible chat message list for the given puzzle.
    """
    img_part = None
    if has_image:
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            img_path = BASE_DIR / "data" / "puzzles" / "puzzle_images" / puzzle_name / f"0_0.{ext}"
            if img_path.exists():
                b64 = jpeg_b64(img_path)
                img_part = {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                }
                break

    system = {
        "role": "system",
        "content": (
            "You are an expert Jane Street puzzle solver. "
            "Provide a very brief reasoning (no more than 2–3 sentences) and then the final answer."
        )
    }
    user_parts = [{"type": "text", "text": puzzle_text}]
    if img_part:
        user_parts.append(img_part)

    return [system, {"role": "user", "content": user_parts}]

def build_msgs_anthropic(puzzle_text: str, puzzle_name: str, has_image: bool):
    """
    Build an Anthropic‐compatible (system_str, parts_list) for the given puzzle.
    """
    img_part = None
    if has_image:
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            img_path = BASE_DIR / "data" / "puzzles" / "puzzle_images" / puzzle_name / f"0_0.{ext}"
            if img_path.exists():
                b64 = jpeg_b64(img_path)
                img_part = {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
                }
                break

    system_txt = (
        "You are an expert Jane Street puzzle solver. "
        "Provide a very brief reasoning (no more than 2–3 sentences) and then the final answer."
    )
    parts = [{"type": "text", "text": puzzle_text}]
    if img_part:
        parts.append(img_part)

    return system_txt, parts

def build_msgs_gemini(puzzle_text: str, puzzle_name: str, has_image: bool):
    """
    Build a Gemini‐compatible prompt list: a list of strings and/or PIL.Image.
    """
    pil_img = None
    if has_image:
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            img_path = BASE_DIR / "data" / "puzzles" / "puzzle_images" / puzzle_name / f"0_0.{ext}"
            if img_path.exists():
                pil_img = Image.open(img_path)
                break

    prompt = (
        "You are an expert Jane Street puzzle solver. "
        "Provide a very brief reasoning (no more than 2–3 sentences) and then the final answer.\n\n"
        + puzzle_text
    )
    if pil_img:
        return [prompt, pil_img]
    return [prompt]

# ---------- MAIN ---------------------------------------------------------

def main():
    # 1) Read the models.txt
    if not MODELS_FILE.exists():
        print(f"[ERROR] {MODELS_FILE} not found.")
        return

    with open(MODELS_FILE, "r") as mf:
        all_models = [line.strip() for line in mf if line.strip()]

    # 2) Load the current month's puzzle (row 0)
    df = pd.read_csv(CSV_PATH)
    if df.shape[0] == 0:
        print("[ERROR] puzzles.csv is empty.")
        return

    row = df.iloc[0]
    puzzle_text = str(row["puzzleText"]).strip()
    puzzle_name = row["name"]
    has_image   = bool(row.get("hasImage", False))

    # 3) Prepare output dict
    final_output = {}

    # 4) For each model, send two attempts
    for model_name in all_models:
        provider = None
        try:
            provider = classify_provider(model_name)
        except ValueError as e:
            print(f"[SKIP] {model_name}: {e}")
            continue

        print(f"\n→ Querying {provider.upper()} model '{model_name}' …")

        # Prepare a list to hold two attempt‐dicts
        answers_list = []

        for attempt_info in ATTEMPTS:
            attempt_no  = attempt_info["attempt"]
            temp        = attempt_info["temperature"]

            entry = {
                "attempt": attempt_no,
                "temperature": temp,
                "answer": None,
                "usage": {},
                "error": None
            }

            try:
                if provider == "openai":
                    from openai import OpenAI, RateLimitError
                    client = OpenAI()
                    messages = build_msgs_openai(puzzle_text, puzzle_name, has_image)

                    if model_name.startswith("o4-"):
                        resp = client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                        )
                    else:
                        resp = client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            temperature=temp,
                            max_tokens=MAX_TOKENS
                        )

                    text_out = resp.choices[0].message.content.strip()
                    entry["answer"] = text_out
                    entry["usage"] = {
                        "prompt_tokens": resp.usage.prompt_tokens,
                        "completion_tokens": resp.usage.completion_tokens,
                        "total_tokens": resp.usage.total_tokens
                    }

                elif provider == "anthropic":
                    import anthropic
                    key = os.getenv("ANTHROPIC_API_KEY")
                    if not key:
                        raise RuntimeError("Missing ANTHROPIC_API_KEY in .env")
                    client = anthropic.Anthropic(api_key=key)

                    system_txt, parts = build_msgs_anthropic(puzzle_text, puzzle_name, has_image)
                    resp = client.messages.create(
                        model=model_name,
                        system=system_txt,
                        messages=[{"role": "user", "content": parts}],
                        temperature=temp,
                        max_tokens=MAX_TOKENS
                    )

                    text_out = resp.content[0].text.strip()
                    entry["answer"] = text_out
                    entry["usage"] = {
                        "input_tokens":  resp.usage.input_tokens,
                        "output_tokens": resp.usage.output_tokens,
                        "total_tokens":  (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
                    }

                elif provider == "gemini":
                    import google.generativeai as genai
                    key = os.getenv("GEMINI_API_KEY")
                    if not key:
                        raise RuntimeError("Missing GEMINI_API_KEY in .env")
                    genai.configure(api_key=key)
                    client = genai.GenerativeModel(f"models/{model_name}")

                    contents = build_msgs_gemini(puzzle_text, puzzle_name, has_image)
                    generation_config = genai.types.GenerationConfig(
                        temperature=temp,
                        max_output_tokens=MAX_TOKENS
                    )
                    resp = client.generate_content(
                        contents=contents,
                        generation_config=generation_config
                    )

                    try:
                        text_out = resp.text.strip()
                    except Exception:
                        text_out = "[ERROR: could not extract text]"

                    entry["answer"] = text_out

                    meta = getattr(resp, "usage_metadata", None)
                    if meta:
                        entry["usage"] = {
                            "prompt_token_count":     getattr(meta, "prompt_token_count", 0),
                            "candidates_token_count": getattr(meta, "candidates_token_count", 0),
                            "total_token_count":      getattr(meta, "total_token_count", 0)
                        }
                    else:
                        entry["usage"] = {}

                else:
                    entry["error"] = f"Unsupported provider '{provider}'"

            except Exception as e:
                entry["error"] = str(e)

            answers_list.append(entry)

        # Save both attempts for this model
        final_output[model_name] = {
            "model": model_name,
            "answers": answers_list
        }

    # 5) Write results to JSON
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(final_output, indent=2))
    print(f"\nWrote results to {OUT_PATH}")

if __name__ == "__main__":
    main()
