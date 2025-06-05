#!/usr/bin/env python
# judge_all_models.py
# --------------------------------------------
# deps: openai, pandas, python-dotenv

import json
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

# ---------- CONFIG -------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent
MODELS_FILE  = BASE / "models.txt"
CSV_PATH     = BASE / "data" / "puzzles" / "puzzles.csv"
RESULTS_DIR  = BASE / "results"
PAUSE_SEC    = 0.5                   # pause between LLM calls
JUDGE_MODEL  = "gpt-4o-mini"         # model to use for judgment

# ---------- AUTH ---------------------------------------------------------
load_dotenv()
client = OpenAI()

# ---------- LOAD LIST OF MODELS ------------------------------------------
with open(MODELS_FILE, "r") as f:
    model_names = [line.strip() for line in f if line.strip()]

# ---------- LOAD GROUND-TRUTH DATA --------------------------------------
df = pd.read_csv(CSV_PATH)

# ---------- HELPER: CALL JUDGE MODEL ------------------------------------
def judge_answer(ground_truth: str, model_answer: str) -> int:
    """
    Ask the JUDGE_MODEL whether model_answer matches ground_truth.
    Returns 1 if judged correct, 0 otherwise.
    """
    prompt = (
        f"Ground truth answer: {ground_truth}\n"
        f"Model answer: {model_answer}\n\n"
        "Question: Is the model answer correct (or extremely close for numeric values)?\n"
        "Reply with exactly '1' if correct, or '0' if incorrect."
    )
    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": "You are a judge that responds with 1 or 0."},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.0,
        max_tokens=1
    )
    verdict = resp.choices[0].message.content.strip()
    return 1 if verdict.startswith("1") else 0

# ---------- MAIN LOOP ----------------------------------------------------
for model_name in model_names:
    results_path = RESULTS_DIR / f"results_{model_name}.json"
    if not results_path.exists():
        print(f"Skipping {model_name}: no results file at {results_path}")
        continue

    print(f"\nProcessing model: {model_name}")
    results = json.loads(results_path.read_text())
    output = {}

    for pid_str, rec in results.items():
        pid_int = int(pid_str)
        # adjust index: JSON pid 0 → row index 1
        csv_idx = pid_int + 1
        if csv_idx < 0 or csv_idx >= len(df):
            continue

        row = df.iloc[csv_idx]
        truth = str(row["answer"]).strip()
        if truth == "" or pd.isna(row["answer"]):
            continue

        answers_list = rec.get("answers", [])
        ans0 = answers_list[0]["answer"] if len(answers_list) >= 1 else ""
        ans1 = answers_list[1]["answer"] if len(answers_list) >= 2 else ""
        model_answer = ans0.strip() or ans1.strip()
        if not model_answer:
            continue

        correct_flag = judge_answer(truth, model_answer)

        entry = {
            "name":         rec.get("name", row["name"]),
            "ground_truth": truth,
            "model_answer": model_answer,
            "correct":      correct_flag,
        }
        if "numSolvers" in df.columns and not pd.isna(row.get("numSolvers", None)):
            entry["numSolvers"] = int(row["numSolvers"])
        output[pid_str] = entry

        time.sleep(PAUSE_SEC)

    out_path = RESULTS_DIR / f"correct_solutions_{model_name}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Wrote {out_path.name} with {len(output)} entries")
