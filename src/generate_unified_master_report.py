from __future__ import annotations

import argparse
from pathlib import Path

from reporting.unified_writer import generate_unified_master_report


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PC = BASE_DIR / "data" / "57_cs_projects_with_pc.csv"
DEFAULT_RAW = BASE_DIR / "output" / "violations_unordered_57_cs_projects_with_pc.csv"
DEFAULT_DEDUP = BASE_DIR / "output" / "violations_unordered_57_cs_projects_with_pc_dedup.csv"
DEFAULT_OUT = BASE_DIR / "reports" / "unified_master_report"


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Generate a unified report that consolidates the executive, doctoral, "
            "and research-question-driven report variants."
        )
    )
    ap.add_argument("--pc-csv", default=str(DEFAULT_PC), help="Base call CSV with PCs.")
    ap.add_argument("--raw", default=str(DEFAULT_RAW), help="Raw detector output.")
    ap.add_argument("--dedup", default=str(DEFAULT_DEDUP), help="Deduplicated detector output.")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT), help="Output directory for the unified report.")
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

    paths = generate_unified_master_report(
        pc_csv_path=pc_csv,
        raw_path=raw,
        dedup_path=dedup,
        out_dir=out_dir,
    )

    print(f"[unified-report] markdown: {paths.markdown_path}")
    print(f"[unified-report] pdf:      {paths.pdf_path}")
    print(f"[unified-report] tech figs: {paths.technical_figures_dir}")
    print(f"[unified-report] rq figs:   {paths.rq_figures_dir}")
    print(f"[unified-report] tech tbl:  {paths.technical_tables_dir}")
    print(f"[unified-report] rq tbl:    {paths.rq_tables_dir}")
    print(f"[unified-report] filtered:  {paths.filtered_output_path}")
    print(f"[unified-report] analyzed:  {paths.fp_analysis_path}")


if __name__ == "__main__":
    main()
