#!/usr/bin/env python
# merge_correct_solutions.py
# --------------------------------------------
# deps: pandas
#
# For each model listed in models.txt, this script reads:
# • correct_solutions_llm_{MODEL}.json (LLM‐based checker, each record has a "correct" flag)
# • correct_solutions_regex_{MODEL}.json (regex‐based checker)
# It takes the union of all puzzle IDs marked correct by either method, and
# writes out a merged JSON correct_{MODEL}.json containing only those entries.
# Incorrect entries (e.g. "correct": 0 in the LLM file) are dropped.
# --------------------------------------------
import json
import sys
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_FILE = BASE_DIR / "models.txt"
RESULTS_DIR = BASE_DIR / "results"

def load_json(path: Path) -> dict:
    """Load a JSON file or return {} if missing or invalid."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"[ERROR] Cannot parse {path}: {e}", file=sys.stderr)
        return {}

def main():
    if not MODELS_FILE.exists():
        print(f"[ERROR] models.txt not found at {MODELS_FILE}", file=sys.stderr)
        sys.exit(1)
    
    # Read model names from models.txt (skip blank lines)
    with open(MODELS_FILE, "r") as mf:
        models = [line.strip() for line in mf if line.strip()]
    
    for model_name in models:
        # Paths of LLM-based and regex-based correct-solutions files
        llm_path = RESULTS_DIR / f"correct_solutions_llm_{model_name}.json"
        regex_path = RESULTS_DIR / f"correct_solutions_regex_{model_name}.json"
        merged_path = RESULTS_DIR / f"correct_{model_name}.json"
        
        llm_data = load_json(llm_path)
        regex_data = load_json(regex_path)
        
        merged = {}
        
        # 1) Add all entries from regex file (all are correct by definition)
        for pid, record in regex_data.items():
            merged[pid] = record
        
        # 2) Add entries from LLM file (they're already filtered to correct == 1)
        for pid, record in llm_data.items():
            # LLM version takes priority (it might have additional info like numSolvers)
            merged[pid] = record
        
        if merged:
            merged_path.parent.mkdir(parents=True, exist_ok=True)
            # Sort by puzzle ID for consistent output
            sorted_merged = {pid: merged[pid] for pid in sorted(merged.keys(), key=lambda x: int(x))}
            merged_path.write_text(json.dumps(sorted_merged, indent=2))
            print(f"Wrote {merged_path.name} ({len(merged)} entries)")
        else:
            print(f"No correct entries for model {model_name}; skipping.")

if __name__ == "__main__":
    main()