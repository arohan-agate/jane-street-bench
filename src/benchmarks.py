#!/usr/bin/env python
# benchmarks.py – regenerate remaining answers, skip existing, zero 429s
# --------------------------------------------------
# deps: openai, anthropic, google-generativeai, pandas, pillow, python-dotenv
# --------------------------------------------------

import os
import base64, io, json, pathlib, re, time, collections
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv, find_dotenv
from PIL import Image

# ---------- CONFIG -------------------------------------------------------
BASE           = Path(__file__).resolve().parent.parent
CSV_PATH       = BASE / "data" / "puzzles" / "puzzles.csv"
IMG_MAX_PX     = 600
JPEG_Q         = 70
RETRY_CUSHION  = 0.3

PROVIDER       = "anthropic"  # "openai" or "anthropic" or "gemini"

load_dotenv()

if PROVIDER == "openai":
    from openai import OpenAI, RateLimitError
    client = OpenAI()
    MODEL           = "gpt-4o-mini"
    ATTEMPTS        = [0.25, 0.30]
    OUT_PATH        = BASE / "results" / "results_gpt-4o-mini.json"
    TPM_LIMIT       = 200_000
    COMPLETION_MAX  = 200
elif PROVIDER == "anthropic":
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY in .env")
    client = anthropic.Anthropic(api_key=key)
    MODEL           = "claude-3-haiku-20240307"
    ATTEMPTS        = [0.25, 0.30]
    OUT_PATH        = BASE / "results" / "results_claude-3-haiku.json"
    RPM_LIMIT       = 1000
elif PROVIDER == "gemini":
    import google.generativeai as genai
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")
    genai.configure(api_key=key)
    MODEL_NAME           = "gemini-2.0-flash-exp"
    MODEL = f"models/{MODEL_NAME}"
    client = genai.GenerativeModel(MODEL)
    ATTEMPTS        = [0.25, 0.30]
    OUT_PATH        = BASE / "results" / "results_gemini-2.0-flash-exp.json"
    RPM_LIMIT       = 1000
else:
    raise ValueError(f"Unknown provider '{PROVIDER}'")

df = pd.read_csv(CSV_PATH)

# Rate-limit trackers
if PROVIDER == "openai":
    bucket = collections.deque()
    retry_re = re.compile(r"in (\d+)ms")
elif PROVIDER in ("anthropic","gemini"):
    request_bucket = collections.deque()
    retry_re = re.compile(r"in (\d+)ms")

# ---------- HELPERS -----------------------------------------------------

def jpeg_b64(p: pathlib.Path) -> str:
    with Image.open(p) as im:
        im = im.convert("RGB")
        im.thumbnail((IMG_MAX_PX, IMG_MAX_PX))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_Q)
        return base64.b64encode(buf.getvalue()).decode()

# Build unified messages or prompts
def build_msgs(rec):
    text = rec["puzzleText"]
    name = rec["name"]
    img_part = None
    pil_img = None
    if rec.get("hasImage", False):
        for ext in ("png","jpg","jpeg","PNG","JPG"):
            path = BASE / "data" / "puzzles" / "puzzle_images" / name / f"0_0.{ext}"
            if path.exists():
                b64 = jpeg_b64(path)
                if PROVIDER == "openai":
                    img_part = {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}
                elif PROVIDER == "anthropic":
                    img_part = {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}}
                else:  # gemini
                    pil_img = Image.open(path)
                break
    system_txt = "You are an expert Jane Street puzzle solver. Return ONLY the final numeric or textual answer — no explanation."
    if PROVIDER == "openai":
        system = {"role":"system","content":system_txt}
        user = [{"type":"text","text":text}]
        if img_part: user.append(img_part)
        return [system, {"role":"user","content":user}]
    elif PROVIDER == "anthropic":
        parts = [{"type":"text","text":text}]
        if img_part: parts.append(img_part)
        return system_txt, parts
    else:  # gemini
        prompt = system_txt + "\n\n" + text
        if pil_img:
            return [prompt, pil_img]
        return [prompt]

# Token estimation for openai
def rough_tokens(msgs):
    chars = 0
    for m in msgs:
        c = m.get("content", "") if isinstance(m, dict) else m
        if isinstance(c, list):
            for p in c:
                chars += len(p.get("text", "") or p.get("image_url", {}).get("url", ""))
        else:
            if isinstance(c, str): chars += len(c)
    return chars//4 + 1

# Throttle functions
def wait_quota_openai(need):
    now = time.time()
    while bucket and now - bucket[0][0] > 60: bucket.popleft()
    used = sum(t for _,t in bucket)
    if used + need > TPM_LIMIT:
        time.sleep(60 - (now - bucket[0][0]) + 0.2)

def wait_quota_requests():
    now = time.time()
    while request_bucket and now - request_bucket[0] > 60: request_bucket.popleft()
    if len(request_bucket) >= RPM_LIMIT:
        time.sleep(60 - (now - request_bucket[0]) + 0.2)

# Safe call per provider
def safe_call_openai(**kw):
    from openai import RateLimitError
    while True:
        try: return client.chat.completions.create(**kw)
        except RateLimitError as e:
            m = retry_re.search(str(e)); wait = int(m.group(1))/1000 if m else 1.0
            time.sleep(wait + RETRY_CUSHION)


def safe_call_claude(system, parts, **kw):
    while True:
        try:
            return client.messages.create(model=MODEL, system=system, messages=[{"role":"user","content":parts}], **kw)
        except anthropic.RateLimitError as e:
            m = retry_re.search(str(e)); wait = int(m.group(1))/1000 if m else 60.0
            time.sleep(wait + RETRY_CUSHION)


def safe_call_gemini(contents, **kw):
    # client is already genai.GenerativeModel(MODEL) from the setup
    generation_config = genai.types.GenerationConfig(
        temperature=kw.get('temperature', 0.25), # Default if not provided
        max_output_tokens=kw.get('max_output_tokens', 200) # Default if not provided
    )
    while True:
        try:
            # The 'model' parameter is not needed here as 'client' is already a specific model instance
            return client.generate_content(contents=contents, generation_config=generation_config)
        except Exception as e: # More specific exceptions can be caught if known
            msg = str(e).lower()
            # Check for common rate limit / quota error messages
            if any(x in msg for x in ["rate limit", "quota", "429", "resource has been exhausted"]):
                print(f"Rate limit or quota error encountered: {e}. Waiting...")
                time.sleep(60 + RETRY_CUSHION)
                continue
            raise

# Check if attempt needed
def needs_rerun(ans, num): return not any(a.get("attempt")==num and a.get("answer","") for a in ans)

# Load or init results
if OUT_PATH.exists(): results = json.loads(OUT_PATH.read_text())
else: results = {}

# Main loop
for _, row in df.iterrows():
    pid = str(int(row["id"]))
    record = results.get(pid, {"name":row["name"],"answers":[]})
    answers = record["answers"]
    if not isinstance(row.get("puzzleText"), str): continue
    if not any(needs_rerun(answers,i) for i in range(1,len(ATTEMPTS)+1)): continue

    msgs = build_msgs(row)
    if PROVIDER == "openai":
        try: p_tok = rough_tokens(msgs)
        except: continue
    else:
        prompt = msgs

    for idx,temp in enumerate(ATTEMPTS, start=1):
        if not needs_rerun(answers, idx): continue

        if PROVIDER == "openai":
            wait_quota_openai(p_tok + COMPLETION_MAX)
            print(f"{dt.now().time()} Puzzle {pid} attempt {idx}")
            resp = safe_call_openai(model=MODEL, messages=msgs, temperature=temp, max_tokens=COMPLETION_MAX)
            bucket.append((time.time(), resp.usage.total_tokens))
            ans = resp.choices[0].message.content.strip()
            usage = (resp.usage.prompt_tokens, resp.usage.completion_tokens, resp.usage.total_tokens)

        elif PROVIDER == "anthropic":
            wait_quota_requests()
            print(f"{dt.now().time()} Puzzle {pid} attempt {idx} (Claude)")
            system_txt, parts = msgs
            resp = safe_call_claude(system_txt, parts, temperature=temp, max_tokens=200)
            request_bucket.append(time.time())
            ans = resp.content[0].text.strip()
            usage = (resp.usage.input_tokens, resp.usage.output_tokens, resp.usage.input_tokens+resp.usage.output_tokens)

        else:  # gemini
            wait_quota_requests()
            print(f"{dt.now().time()} Puzzle {pid} attempt {idx} (Gemini)")
            resp = safe_call_gemini(contents=msgs, temperature=temp, max_output_tokens=200)
            request_bucket.append(time.time())
            try:
                ans = resp.text.strip()
            except ValueError: # Handles cases where .text might fail (e.g. empty candidates due to safety)
                ans = "Error: Could not extract text from response."
                if resp.prompt_feedback.block_reason:
                    ans += f" Reason: {resp.prompt_feedback.block_reason}"
                print(f"Warning: Puzzle {pid} attempt {idx} (Gemini) - Could not get text from response. Full response: {resp}")

            meta = getattr(resp, 'usage_metadata', None)
            usage = (getattr(meta, 'prompt_token_count', 0),
                     getattr(meta, 'candidates_token_count', 0), # For Gemini, this is output tokens
                     getattr(meta, 'total_token_count', 0))

        entry = {"attempt":idx, "temperature":temp, "answer":ans,
                 "prompt_tokens":usage[0], "completion_tokens":usage[1], "total_tokens":usage[2]}
        answers = [a for a in answers if a.get("attempt")!=idx] + [entry]
        results[pid] = {"name":row["name"],"answers":answers}
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(results, indent=2))

print(f"\nBenchmark complete. Results written to {OUT_PATH}")
