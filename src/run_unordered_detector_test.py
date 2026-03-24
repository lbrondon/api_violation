from __future__ import annotations

import os

from unordered_detector import UnorderedViolationDetector


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_PC_CSV = os.path.join(BASE_DIR, "data", "5_cs_projects_with_pc.csv")
DEFAULT_PATTERNS = os.path.join(BASE_DIR, "data", "patterns_unordered.csv")

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "violations_unordered_5_cs_projects_with_pc.csv")


def main() -> None:
    print("=== Unordered Evaluation (5-project sample, YES/NO) ===")
    print(f"PC input:       {DEFAULT_PC_CSV}")
    print(f"Patterns input: {DEFAULT_PATTERNS}")
    print(f"Output file:    {OUTPUT_FILE}")

    patterns = UnorderedViolationDetector.load_patterns(DEFAULT_PATTERNS)
    detector = UnorderedViolationDetector(patterns=patterns)

    pc_map = detector.build_pc_index(DEFAULT_PC_CSV, chunksize=200_000)
    rows = detector.evaluate(pc_map)

    n = detector.write_csv(OUTPUT_FILE, rows)
    print(f"Wrote {n} rows (YES + NO) to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
