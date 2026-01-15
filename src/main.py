from __future__ import annotations

import os

from csv_io import read_patterns_csv
from detector import (
    build_pc_index,
    print_index_stats,
    run_short_circuit_detection,
    run_string_mismatch_detection,
)

# Resolve paths relative to the repository root (one level above /src)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_PC_CSV = os.path.join(BASE_DIR, "data", "cs_projects__with_pc.csv")
DEFAULT_PATTERNS = os.path.join(BASE_DIR, "data", "patterns_unordered.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def main() -> None:
    print("=== api_violation: Milestone 1 (Load + Index + Validate) ===")

    if not os.path.exists(DEFAULT_PATTERNS):
        raise FileNotFoundError(f"Missing patterns file: {DEFAULT_PATTERNS}")
    if not os.path.exists(DEFAULT_PC_CSV):
        raise FileNotFoundError(f"Missing PC CSV file: {DEFAULT_PC_CSV}")

    patterns = read_patterns_csv(DEFAULT_PATTERNS)
    print(f"Loaded patterns: {len(patterns)} rows")
    if patterns:
        p0 = patterns[0]
        print(
            f"Sample pattern[0]: {p0.antecedents} -> {p0.consequents} "
            f"(support={p0.support}, confidence={p0.confidence}, lift={p0.lift})"
        )

    index = build_pc_index(DEFAULT_PC_CSV, chunksize=200_000)
    print_index_stats(index, top_k=10)

    print("\nMilestone 1 OK: PC index built. Next milestone: summary/evidence outputs (short-circuit, no SAT yet).")

    run_short_circuit_detection(patterns, index, OUTPUT_DIR)
    print("\nMilestone 2 OK: summary/evidence generated (short-circuit only). Next milestone: STRING mismatch detection.")

    run_string_mismatch_detection(patterns, index, OUTPUT_DIR)
    print("\nMilestone 3 (STRING) OK: string-based summary/evidence generated.")


if __name__ == "__main__":
    main()