#!/usr/bin/env python
# check_accuracy.py
# --------------------------------------------
# deps: pandas
#
# For each model listed in models.txt, this script loads results_{MODEL}.json,
# compares each puzzle’s two attempts against the ground‐truth answer in puzzles.csv
# (shifting JSON key “0” → CSV ID 1), and writes correct_solutions_regex_{MODEL}.json
# containing only those puzzles judged correct. A console summary is printed per model.
#
# Usage:
#   1. Put your list of model names (one per line) in ${PROJECT_ROOT}/models.txt.
#   2. Make sure each results_{MODEL}.json already exists under results/.
#   3. Run:
#        python check_accuracy.py
# --------------------------------------------

import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

# ── CONFIG ────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).resolve().parent.parent
MODELS_FILE  = BASE_DIR / "models.txt"
RESULTS_DIR  = BASE_DIR / "results"
DATA_CSV     = BASE_DIR / "data" / "puzzles" / "puzzles.csv"

_num_re   = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:\.\d+)?")
_frac_re  = re.compile(r"\d+/\d+")
_caps_re  = re.compile(r"\b[A-Z]{2,}\b")
_pi_re    = re.compile(r"[πpi]+", re.IGNORECASE)

def grab_token(s: str) -> str:
    s = s.strip()
    for regex in (_frac_re, _num_re, _caps_re):
        m = regex.search(s)
        if m:
            return m.group()
    return s

def normalize(s: str) -> set[str]:
    s = unicodedata.normalize("NFKC", s).strip()
    s = re.sub(r"\\\(|\\\)|\$\$|\$|\\\[|\\\]", "", s).strip()

    if _pi_re.fullmatch(s):
        return {"π", str(3.141592653589793)[:9]}

    token = grab_token(s).lower()
    if _frac_re.fullmatch(token):
        n, d = map(int, token.split("/"))
        val = n / d
        return {token, str(val)}

    raw = token.replace(",", "")
    if _num_re.fullmatch(raw):
        try:
            f = float(raw)
        except ValueError:
            return {raw}
        int_str = str(int(f)) if f.is_integer() else raw.lstrip("0") or "0"
        float_str = str(f).rstrip("0").rstrip(".")
        return {int_str, float_str}

    clean = re.sub(r"[^\w]", "", token)
    return {clean}

def answers_match(model_ans: str, truth: str) -> bool:
    set1 = normalize(model_ans)
    set2 = normalize(truth)
    return not set1.isdisjoint(set2)

def process_model(model_name: str, gt_df: pd.DataFrame):
    results_path = RESULTS_DIR / f"results_{model_name}.json"
    if not results_path.exists():
        print(f"[SKIP] results_{model_name}.json not found in {RESULTS_DIR}", file=sys.stderr)
        return

    with open(results_path, "r") as f:
        try:
            results = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse {results_path}: {e}", file=sys.stderr)
            return

    total = 0
    first_correct = 0
    best_correct  = 0
    correct_first = []
    correct_best  = []
    output = {}

    for pid_str, rec in results.items():
        try:
            pid_int = int(pid_str)
        except ValueError:
            continue

        if pid_int not in gt_df.index:
            continue

        truth = str(gt_df.at[pid_int, "answer"]).strip()
        if truth == "" or pd.isna(gt_df.at[pid_int, "answer"]):
            continue

        total += 1
        name = rec.get("name", gt_df.at[pid_int, "name"])
        answers = rec.get("answers", [])

        ans0 = answers[0].get("answer", "").strip() if len(answers) >= 1 else ""
        ans1 = answers[1].get("answer", "").strip() if len(answers) >= 2 else ""

        first_ok = answers_match(ans0, truth)
        best_ok  = first_ok or answers_match(ans1, truth)

        if first_ok:
            first_correct += 1
            correct_first.append((pid_int, name))
        if best_ok:
            best_correct += 1
            correct_best.append((pid_int, name))
            chosen_ans = ans0 if first_ok else ans1
            entry = {
                "name":         name,
                "ground_truth": truth,
                "model_answer": chosen_ans,
            }
            if "numSolvers" in gt_df.columns:
                ns = gt_df.at[pid_int, "numSolvers"]
                if pd.notna(ns):
                    entry["numSolvers"] = int(ns)
            output[pid_str] = entry

    out_path = RESULTS_DIR / f"correct_solutions_regex_{model_name}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as outf:
        json.dump(output, outf, indent=2)

    print(f"\nMODEL = {model_name}")
    print(f"Puzzles with ground‐truth answers: {total}")
    if total > 0:
        print(f" • First‐attempt accuracy: {first_correct}/{total} = {first_correct/total:.2%}")
        print(f" • Best‐of‐two accuracy: {best_correct}/{total} = {best_correct/total:.2%}")
    else:
        print(" (No puzzles had a ground-truth answer.)")

    print("\nCORRECT ON FIRST ATTEMPT:")
    if correct_first:
        for pid, nm in correct_first:
            print(f"  {pid:>3}  {nm}")
    else:
        print("  (none)")

    print("\nCORRECT AFTER TWO ATTEMPTS (includes first):")
    if correct_best:
        for pid, nm in correct_best:
            print(f"  {pid:>3}  {nm}")
    else:
        print("  (none)")

    print(f"\nWrote {out_path.name} with {len(output)} correct entries.")

def main():
    if not MODELS_FILE.exists():
        print(f"[ERROR] models.txt not found at {MODELS_FILE}", file=sys.stderr)
        sys.exit(1)

    # Load ground truth CSV, index by puzzle ID (1..N)
    gt_df = pd.read_csv(DATA_CSV).set_index("id")

    # Read model list
    with open(MODELS_FILE, "r") as mf:
        models = [line.strip() for line in mf if line.strip()]

    for model_name in models:
        process_model(model_name, gt_df)

if __name__ == "__main__":
    main()
