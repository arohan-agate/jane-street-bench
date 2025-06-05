#!/usr/bin/env python
# eval_model.py
# --------------------------------------------
# deps: openai, anthropic, google-generativeai, pandas, pillow, python-dotenv
import os
import sys
import base64
from dotenv import load_dotenv
from pathlib import Path
import pandas as pd
from PIL import Image

# --- Choose provider: set to "openai", "anthropic", or "gemini" ---
PROVIDER = "gemini"

# ---------- AUTH ---------------------------------------------------------
load_dotenv()

# Initialize client & model based on provider
if PROVIDER == "openai":
    from openai import OpenAI
    client = OpenAI()
    MODEL = "o4-mini" 
elif PROVIDER == "anthropic":
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY in .env")
    client = anthropic.Anthropic(api_key=key)
    MODEL = "claude-3-haiku-20240307"  # cheapest Claude variant
elif PROVIDER == "gemini":
    import google.generativeai as genai
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")
    genai.configure(api_key=key)
    MODEL = "gemini-2.0-flash-exp"  # Latest Gemini 2.0 Flash model
    client = genai.GenerativeModel(MODEL)
else:
    raise ValueError(f"Unknown provider '{PROVIDER}'")

# ---------- PATHS & DATA ------------------------------------------------
BASE = Path(__file__).resolve().parent.parent
DF_PATH = BASE / "data" / "puzzles" / "puzzles.csv"
df = pd.read_csv(DF_PATH)
record = df.iloc[0]
text = record['puzzleText']
name = record['name']

# ---------- OPTIONAL IMAGE ------------------------------------------------
img_part = None
pil_image = None  # For Gemini
if record.get('hasImage', False):
    for ext in ('png', 'jpg', 'jpeg', 'PNG', 'JPG'):
        img_path = BASE / 'data' / 'puzzles' / 'puzzle_images' / name / f"0_0.{ext}"
        if img_path.exists():
            with open(img_path, 'rb') as img_file:
                img_data = img_file.read()
            b64 = base64.b64encode(img_data).decode()
            
            # Determine media type
            media_type = "image/jpeg" if ext.lower() in ['jpg', 'jpeg'] else f"image/{ext.lower()}"
            
            # For OpenAI and Anthropic
            img_part = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            }
            
            # For Gemini - load as PIL Image
            if PROVIDER == "gemini":
                pil_image = Image.open(img_path)
            
            break

# ---------- BUILD MESSAGES -----------------------------------------------
system_msg = (
    'You are a puzzle solver. You will be given a puzzle and/or an accompanying image. '
    'Provide an answer to the puzzle and your step-by-step reasoning.'
)

# ---------- CALL MODEL --------------------------------------------------
if PROVIDER == "openai":
    user_content = [{'type': 'text', 'text': text}]
    if img_part:
        # Convert Anthropic format to OpenAI format
        openai_img = {
            'type': 'image_url',
            'image_url': {'url': f"data:{img_part['source']['media_type']};base64,{img_part['source']['data']}"}
        }
        user_content.append(openai_img)
    
    messages = [
        {'role': 'system', 'content': system_msg},
        {'role': 'user', 'content': user_content}
    ]
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.25,
        max_tokens=1200,
    )
    output = response.choices[0].message.content.strip()

elif PROVIDER == "anthropic":
    # Build user content for Anthropic
    user_content = [{"type": "text", "text": text}]
    if img_part:
        user_content.append(img_part)
    
    # Use Anthropic messages API
    response = client.messages.create(
        model=MODEL,
        system=system_msg,
        messages=[
            {"role": "user", "content": user_content}
        ],
        temperature=0.25,
        max_tokens=1200,
    )
    output = response.content[0].text.strip()

elif PROVIDER == "gemini":
    # Build content for Gemini
    content_parts = [system_msg + "\n\n" + text]
    if pil_image:
        content_parts.append(pil_image)
    
    # Use Gemini generate_content
    response = client.generate_content(
        content_parts,
        generation_config=genai.types.GenerationConfig(
            temperature=0.25,
            max_output_tokens=1200,
        )
    )
    output = response.text.strip()

# ---------- OUTPUT ------------------------------------------------------
print(f"=== {PROVIDER.upper()} OUTPUT ({MODEL}) ===")
print(output)