from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReportPaths:
    base_dir: Path
    figures_dir: Path
    tables_dir: Path
    markdown_path: Path
    pdf_path: Path
    fp_analysis_path: Path
    filtered_output_path: Path

    @classmethod
    def build(cls, base_dir: Path) -> "ReportPaths":
        return cls(
            base_dir=base_dir,
            figures_dir=base_dir / "figures",
            tables_dir=base_dir / "tables",
            markdown_path=base_dir / "technical_violation_report.md",
            pdf_path=base_dir / "technical_violation_report.pdf",
            fp_analysis_path=base_dir / "violations_fp_analysis.csv",
            filtered_output_path=base_dir / "violations_filtered.csv",
        )

