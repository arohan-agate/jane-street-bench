#!/usr/bin/env python
# evaluate_results.py
# --------------------------------------------
# deps: pandas

import json, pathlib, re, unicodedata
import pandas as pd
from collections import defaultdict

RESULTS_JSON = "results_gpt-4o-mini.json"
GT_CSV       = "data/puzzles/puzzles.csv"      # must contain an 'answer' col

# ---------- 1. Load data --------------------
res = json.loads(pathlib.Path(RESULTS_JSON).read_text())
gt  = pd.read_csv(GT_CSV).set_index("id")

# ---------- 2. Helpers ----------------------
num_re   = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?")
frac_re  = re.compile(r"\d+/\d+")
caps_re  = re.compile(r"\b[A-Z]{3,}\b")

def grab_token(s: str) -> str:
    for regex in (frac_re, num_re, caps_re):
        if (m := regex.search(s)):
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

# ---------- 3. Evaluation loop ---------------
stats   = defaultdict(int)
correct_first = []          # (id, name)
correct_best  = []          # (id, name)

for pid, rec in res.items():
    pid_int   = int(pid)
    if pid_int not in gt.index:           # safety
        continue

    truth = gt.at[pid_int, "answer"]
    if pd.isna(truth) or truth == "":
        continue                          # skip if no ground-truth answer yet

    truth      = str(truth)
    attempts   = [a.get("answer", "") for a in rec.get("answers", [])]
    while len(attempts) < 2:              # pad
        attempts.append("")

    first_ok = is_correct(attempts[0], truth)
    best_ok  = first_ok or is_correct(attempts[1], truth)

    stats["total"]         += 1
    stats["first_correct"] += first_ok
    stats["best_correct"]  += best_ok

    if first_ok:
        correct_first.append((pid_int, rec["name"]))
    if best_ok:
        correct_best.append((pid_int, rec["name"]))

    print(f"{pid:>3}  {rec['name'][:28]:28}  "
          f"A1={'✔' if first_ok else '✘'}  "
          f"Bo2={'✔' if best_ok else '✘'}  "
          f"truth={truth}  answers={attempts}")

# ---------- 4. Summary ----------------------
if stats["total"]:
    print("\nSUMMARY")
    print(f"Puzzles with ground truth      : {stats['total']}")
    print(f"Accuracy (first attempt)       : "
          f"{stats['first_correct']/stats['total']:.2%}")
    print(f"Accuracy (best of two attempts): "
          f"{stats['best_correct']/stats['total']:.2%}")

    # ----- lists of correct puzzles ----------
    print("\nCORRECT ON FIRST ATTEMPT:")
    if correct_first:
        for pid, name in correct_first:
            print(f"  {pid:>3}  {name}")
    else:
        print("  (none)")

    print("\nCORRECT AFTER TWO ATTEMPTS (includes first-attempt successes):")
    if correct_best:
        for pid, name in correct_best:
            print(f"  {pid:>3}  {name}")
    else:
        print("  (none)")
else:
    print("No puzzles had a ground-truth answer to evaluate against.")
