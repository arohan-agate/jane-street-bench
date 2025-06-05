#!/usr/bin/env python
# extract_correct_llm.py
# --------------------------------------------
# For each model listed in models.txt, this script reads:
# • correct_solutions_{MODEL}.json (contains all solutions with "correct" flag)
# Filters entries based on correct flag and writes to:
# • full_correct_{MODEL}.json (correct: 1)
# • partial_correct_{MODEL}.json (correct: 0.5)
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
        print(f"[WARNING] File not found: {path}")
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"[ERROR] Cannot parse {path}: {e}", file=sys.stderr)
        return {}

def extract_solutions(model_name: str):
    """Extract correct and partial correct solutions for a given model."""
    input_path = RESULTS_DIR / f"correct_solutions_{model_name}.json"
    correct_output_path = RESULTS_DIR / f"full_correct_{model_name}.json"
    partial_output_path = RESULTS_DIR / f"partial_correct_{model_name}.json"
    
    # Load the input file
    all_solutions = load_json(input_path)
    
    if not all_solutions:
        print(f"No data found for model {model_name}")
        return
    
    # Filter solutions by correct flag
    correct_solutions = {}
    partial_solutions = {}
    
    for puzzle_id, record in all_solutions.items():
        correct_flag = record.get("correct")
        if correct_flag == 1:
            correct_solutions[puzzle_id] = record
        elif correct_flag == 0.5:
            partial_solutions[puzzle_id] = record
    
    # Write correct solutions (correct: 1)
    if correct_solutions:
        correct_output_path.parent.mkdir(parents=True, exist_ok=True)
        sorted_correct = {
            pid: correct_solutions[pid]
            for pid in sorted(correct_solutions.keys(), key=lambda x: int(x))
        }
        correct_output_path.write_text(json.dumps(sorted_correct, indent=2))
        print(f"Extracted {len(correct_solutions)} fully correct solutions for {model_name} -> {correct_output_path.name}")
    else:
        print(f"No fully correct solutions found for model {model_name}")
    
    # Write partial correct solutions (correct: 0.5)
    if partial_solutions:
        partial_output_path.parent.mkdir(parents=True, exist_ok=True)
        sorted_partial = {
            pid: partial_solutions[pid]
            for pid in sorted(partial_solutions.keys(), key=lambda x: int(x))
        }
        partial_output_path.write_text(json.dumps(sorted_partial, indent=2))
        print(f"Extracted {len(partial_solutions)} partially correct solutions for {model_name} -> {partial_output_path.name}")
    else:
        print(f"No partially correct solutions found for model {model_name}")

def main():
    if not MODELS_FILE.exists():
        print(f"[ERROR] models.txt not found at {MODELS_FILE}", file=sys.stderr)
        sys.exit(1)
    
    # Read model names from models.txt (skip blank lines)
    with open(MODELS_FILE, "r") as mf:
        models = [line.strip() for line in mf if line.strip()]
    
    print(f"Processing {len(models)} models...")
    
    for model_name in models:
        extract_solutions(model_name)

if __name__ == "__main__":
    main()