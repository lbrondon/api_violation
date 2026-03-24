from __future__ import annotations

import argparse
from pathlib import Path

from reporting.datasets import load_datasets
from reporting.metrics import build_metrics
from reporting.models import ReportPaths
from reporting.plots import generate_all_plots
from reporting.writer import write_metric_tables
from reporting.doctoral_writer import (
    DoctoralReportPaths,
    write_doctoral_markdown_report,
    write_doctoral_pdf_report,
)


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RAW = BASE_DIR / "output" / "violations_unordered_57_cs_projects_with_pc.csv"
DEFAULT_DEDUP = BASE_DIR / "output" / "violations_unordered_57_cs_projects_with_pc_dedup.csv"
DEFAULT_OUT_DIR = BASE_DIR / "reports" / "doctoral_violation_report"


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Generate a doctoral-level report with detailed computational, mathematical "
            "and statistical analysis for API-usage violations in configurable C/C++ systems."
        )
    )
    ap.add_argument("--raw", default=str(DEFAULT_RAW), help="Raw unordered detector CSV.")
    ap.add_argument("--dedup", default=str(DEFAULT_DEDUP), help="Deduplicated unordered detector CSV.")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for the doctoral report.")
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    raw_path = Path(args.raw)
    dedup_path = Path(args.dedup)
    out_dir = Path(args.out_dir)

    if not raw_path.exists():
        raise FileNotFoundError(f"Raw CSV not found: {raw_path}")
    if not dedup_path.exists():
        raise FileNotFoundError(f"Deduplicated CSV not found: {dedup_path}")

    report_paths = ReportPaths.build(out_dir)
    doctoral_paths = DoctoralReportPaths.build(out_dir)
    report_paths.base_dir.mkdir(parents=True, exist_ok=True)
    report_paths.figures_dir.mkdir(parents=True, exist_ok=True)
    report_paths.tables_dir.mkdir(parents=True, exist_ok=True)

    data = load_datasets(raw_path=raw_path, dedup_path=dedup_path, report_paths=report_paths)
    metrics = build_metrics(data)

    write_metric_tables(metrics, report_paths.tables_dir)
    generate_all_plots(metrics, report_paths.figures_dir)
    write_doctoral_markdown_report(metrics, doctoral_paths)
    write_doctoral_pdf_report(metrics, doctoral_paths)

    print(f"[doctoral-report] markdown: {doctoral_paths.markdown_path}")
    print(f"[doctoral-report] pdf:      {doctoral_paths.pdf_path}")
    print(f"[doctoral-report] figures:  {report_paths.figures_dir}")
    print(f"[doctoral-report] tables:   {report_paths.tables_dir}")
    print(f"[doctoral-report] fp csv:   {report_paths.fp_analysis_path}")
    print(f"[doctoral-report] filtered: {report_paths.filtered_output_path}")


if __name__ == "__main__":
    main()
