#!/usr/bin/env python
# check_accuracy.py
# --------------------------------------------
# deps: pandas

import json
import pathlib
import re
import unicodedata
from pathlib import Path
import pandas as pd

# ---------- CONFIG -------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent

MODEL = "gemini-2.0-flash-exp"  
RESULTS_JSON = BASE / "results" / f"results_{MODEL}.json"
GT_CSV       = BASE / "data"    / "puzzles" / "puzzles.csv"
OUT_JSON     = BASE / "results" / f"correct_solutions_{MODEL}.json"

# ---------- HELPERS ------------------------------------------------------
num_re  = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?")
frac_re = re.compile(r"\d+/\d+")

def grab_token(s: str) -> str:
    for regex in (frac_re, num_re):
        m = regex.search(s)
        if m:
            return m.group()
    return s.strip()

def canon(s: str) -> set[str]:
    s = grab_token(unicodedata.normalize("NFKC", s).strip().lower())
    if frac_re.fullmatch(s):
        n, d = map(int, s.split("/"))
        return {s, str(n/d)}
    if num_re.fullmatch(s.replace(" ", "")):
        n = s.replace(",", "")
        return {str(float(n)).rstrip("0").rstrip("."), n.lstrip("0")}
    return {re.sub(r"[^\w]", "", s)}

def is_correct(model_ans: str, truth: str) -> bool:
    return not canon(model_ans).isdisjoint(canon(truth))

# ---------- LOAD DATA ----------------------------------------------------
res = json.loads(pathlib.Path(RESULTS_JSON).read_text())
gt  = pd.read_csv(GT_CSV).set_index("id")

output = {}

# ---------- EVALUATE -----------------------------------------------------
for pid, rec in res.items():
    idx = int(pid)
    if idx not in gt.index:
        continue

    truth = str(gt.at[idx, "answer"]).strip()
    if truth == "" or pd.isna(gt.at[idx, "answer"]):
        continue

    # model attempts
    answers = rec.get("answers", [])
    ans0 = answers[0]["answer"] if len(answers) >= 1 else ""
    ans1 = answers[1]["answer"] if len(answers) >= 2 else ""

    first_ok = is_correct(ans0, truth)
    best_ok  = first_ok or is_correct(ans1, truth)

    if not best_ok:
        continue

    # pick the correct attempt's answer
    model_answer = ans0 if first_ok else ans1

    # record fields
    entry = {
        "name":          rec.get("name", gt.at[idx, "name"]),
        "ground_truth":  truth,
        "model_answer":  model_answer,
    }
    # include numSolvers if available
    if "numSolvers" in gt.columns and not pd.isna(gt.at[idx, "numSolvers"]):
        entry["numSolvers"] = int(gt.at[idx, "numSolvers"])

    output[pid] = entry

# ---------- SAVE --------------------------------------------------------
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.write_text(json.dumps(output, indent=2))
