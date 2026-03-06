from __future__ import annotations

import argparse
import os

from dedup_unordered import UnorderedViolationDeduplicator


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Deduplicate unordered-string detector output CSV using canonical unordered keys."
    )
    ap.add_argument("--input", required=True, help="Path to unordered output CSV.")
    ap.add_argument("--output", required=True, help="Path to deduplicated output CSV.")
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    if not os.path.exists(args.input):
        raise FileNotFoundError(f"Input file not found: {args.input}")

    dedup = UnorderedViolationDeduplicator()
    stats = dedup.deduplicate_file(args.input, args.output)

    print(f"[dedup] input rows:   {stats.input_rows}")
    print(f"[dedup] output rows:  {stats.output_rows}")
    print(f"[dedup] dropped rows: {stats.dropped_rows}")
    print(f"[dedup] reduction:    {stats.reduction_ratio:.2%}")
    print(f"[dedup] wrote:        {args.output}")


if __name__ == "__main__":
    main()

