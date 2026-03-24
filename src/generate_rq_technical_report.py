from __future__ import annotations

import argparse
from pathlib import Path

from reporting.rq_report import generate_rq_technical_report


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PC = BASE_DIR / "data" / "57_cs_projects_with_pc.csv"
DEFAULT_RAW = BASE_DIR / "output" / "violations_unordered_57_cs_projects_with_pc.csv"
DEFAULT_DEDUP = BASE_DIR / "output" / "violations_unordered_57_cs_projects_with_pc_dedup.csv"
DEFAULT_OUT = BASE_DIR / "reports" / "rq_technical_report"


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Generate a Portuguese technical report driven by research questions "
            "about usage patterns, variability, and violations in configurable C/C++ systems."
        )
    )
    ap.add_argument("--pc-csv", default=str(DEFAULT_PC), help="Call CSV with Project, File, Caller, Callee, and PC.")
    ap.add_argument("--raw", default=str(DEFAULT_RAW), help="Raw output from the unordered-string detector.")
    ap.add_argument("--dedup", default=str(DEFAULT_DEDUP), help="Deduplicated output from the unordered-string detector.")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT), help="Output directory for the report package.")
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    pc_csv = Path(args.pc_csv)
    raw = Path(args.raw)
    dedup = Path(args.dedup)
    out_dir = Path(args.out_dir)

    if not pc_csv.exists():
        raise FileNotFoundError(f"PC CSV not found: {pc_csv}")
    if not raw.exists():
        raise FileNotFoundError(f"Raw detector output not found: {raw}")
    if not dedup.exists():
        raise FileNotFoundError(f"Deduplicated detector output not found: {dedup}")

    paths = generate_rq_technical_report(
        pc_csv_path=pc_csv,
        raw_path=raw,
        dedup_path=dedup,
        out_dir=out_dir,
    )

    print(f"[rq-report] markdown: {paths.markdown_path}")
    print(f"[rq-report] pdf:      {paths.pdf_path}")
    print(f"[rq-report] figures:  {paths.figures_dir}")
    print(f"[rq-report] tables:   {paths.tables_dir}")
    print(f"[rq-report] filtered: {paths.filtered_path}")
    print(f"[rq-report] analyzed: {paths.analyzed_path}")


if __name__ == "__main__":
    main()
