from __future__ import annotations

import argparse
import os
from pathlib import Path

from csv_io import read_patterns_csv
from dedup_unordered import UnorderedViolationDeduplicator
from detector import (
    build_pc_index,
    print_index_stats,
    run_sat_detection,
    run_short_circuit_detection,
    run_string_mismatch_detection,
)
from unordered_detector import UnorderedViolationDetector

# Resolve paths relative to the repository root (one level above /src)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_PC_CSV_CANDIDATES = [
    os.path.join(BASE_DIR, "data", "57_cs_projects_with_pc.csv"),
    os.path.join(BASE_DIR, "data", "57_cs_projects__with_pc.csv"),
]
DEFAULT_PATTERNS = os.path.join(BASE_DIR, "data", "patterns_unordered.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def resolve_pc_csv_path(cli_value: str) -> str:
    if cli_value:
        return cli_value
    for candidate in DEFAULT_PC_CSV_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    # Keep the first path in the error message for backward compatibility.
    return DEFAULT_PC_CSV_CANDIDATES[0]


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Runner for API-usage violation detection in configurable C systems. "
            "Default mode uses the unordered string-comparison detector "
            "(current baseline in use)."
        )
    )
    ap.add_argument(
        "--mode",
        choices=["unordered-string", "short-circuit", "summary-string", "sat"],
        default="unordered-string",
        help=(
            "Detection mode. "
            "'unordered-string' is the current baseline (catalog-faithful, PC string comparison). "
            "'sat' is available for future comparison experiments."
        ),
    )
    ap.add_argument(
        "--pc-csv",
        default="",
        help=(
            "Path to CSV with Project, File, Caller, Callee, PC. "
            "If omitted, tries data/cs_projects__with_pc.csv then data/5_cs_projects__with_pc.csv."
        ),
    )
    ap.add_argument(
        "--patterns",
        default=DEFAULT_PATTERNS,
        help="Path to patterns_unordered.csv (default: data/patterns_unordered.csv).",
    )
    ap.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Output directory for generated CSVs (default: output/).",
    )
    ap.add_argument(
        "--output-file",
        default="",
        help=(
            "Output CSV path used by --mode unordered-string. "
            "If omitted, writes to <output-dir>/violations_unordered_<pc_csv_stem>.csv."
        ),
    )
    ap.add_argument(
        "--chunksize",
        type=int,
        default=200_000,
        help="CSV streaming chunk size (default: 200000).",
    )
    ap.add_argument(
        "--print-index-stats",
        action="store_true",
        help="Print index statistics before running summary-string/short-circuit/SAT modes.",
    )
    ap.add_argument(
        "--dedup-unordered-output",
        action="store_true",
        help=(
            "After --mode unordered-string, write a deduplicated CSV using unordered "
            "canonical keys for API/PC pairs."
        ),
    )
    ap.add_argument(
        "--dedup-output-file",
        default="",
        help=(
            "Optional output path for deduplicated unordered CSV. "
            "Default: <unordered_output_stem>_dedup.csv."
        ),
    )
    return ap


def run_unordered_string_mode(
    pc_csv_path: str,
    patterns_path: str,
    output_dir: str,
    output_file: str,
    chunksize: int,
    dedup_output: bool,
    dedup_output_file: str,
) -> None:
    patterns = UnorderedViolationDetector.load_patterns(patterns_path)
    detector = UnorderedViolationDetector(patterns=patterns)

    pc_map = detector.build_pc_index(pc_csv_path, chunksize=chunksize)
    rows = detector.evaluate(pc_map)

    if not output_file:
        stem = Path(pc_csv_path).stem
        output_file = os.path.join(output_dir, f"violations_unordered_{stem}.csv")
    n = detector.write_csv(output_file, rows)
    print(f"[unordered-string] Wrote {n} rows (YES + NO) to: {output_file}")

    if dedup_output:
        if not dedup_output_file:
            dedup_output_file = os.path.splitext(output_file)[0] + "_dedup.csv"
        dedup = UnorderedViolationDeduplicator()
        stats = dedup.deduplicate_file(output_file, dedup_output_file)
        print(
            "[unordered-string][dedup] "
            f"in={stats.input_rows}, out={stats.output_rows}, "
            f"dropped={stats.dropped_rows}, reduction={stats.reduction_ratio:.2%} -> {dedup_output_file}"
        )


def run_summary_mode(mode: str, pc_csv_path: str, patterns_path: str, output_dir: str, chunksize: int, print_stats: bool) -> None:
    patterns = read_patterns_csv(patterns_path)
    print(f"Loaded patterns: {len(patterns)} rows")
    if patterns:
        p0 = patterns[0]
        print(
            f"Sample pattern[0]: {p0.antecedents} -> {p0.consequents} "
            f"(support={p0.support}, confidence={p0.confidence}, lift={p0.lift})"
        )

    index = build_pc_index(pc_csv_path, chunksize=chunksize)
    if print_stats:
        print_index_stats(index, top_k=10)

    if mode == "short-circuit":
        run_short_circuit_detection(patterns, index, output_dir)
    elif mode == "summary-string":
        run_string_mismatch_detection(patterns, index, output_dir)
    elif mode == "sat":
        run_sat_detection(patterns, index, output_dir)
    else:
        raise ValueError(f"Unsupported summary mode: {mode}")


def main() -> None:
    args = build_arg_parser().parse_args()
    pc_csv_path = resolve_pc_csv_path(args.pc_csv)

    print(f"=== api_violation | mode={args.mode} ===")
    print(f"PC input:       {pc_csv_path}")
    print(f"Patterns input: {args.patterns}")
    print(f"Output dir:     {args.output_dir}")

    if not os.path.exists(args.patterns):
        raise FileNotFoundError(f"Missing patterns file: {args.patterns}")
    if not os.path.exists(pc_csv_path):
        raise FileNotFoundError(f"Missing PC CSV file: {pc_csv_path}")

    if args.mode == "unordered-string":
        run_unordered_string_mode(
            pc_csv_path=pc_csv_path,
            patterns_path=args.patterns,
            output_dir=args.output_dir,
            output_file=args.output_file,
            chunksize=args.chunksize,
            dedup_output=args.dedup_unordered_output,
            dedup_output_file=args.dedup_output_file,
        )
        return

    try:
        run_summary_mode(
            mode=args.mode,
            pc_csv_path=pc_csv_path,
            patterns_path=args.patterns,
            output_dir=args.output_dir,
            chunksize=args.chunksize,
            print_stats=args.print_index_stats,
        )
    except ImportError:
        if args.mode == "sat":
            print(
                "[sat] SAT mode is available for future comparison experiments, "
                "but initialization failed (dependency/parser issue). "
                "Use --mode unordered-string or --mode summary-string for now."
            )
            raise
        raise


if __name__ == "__main__":
    main()
