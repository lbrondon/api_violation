from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from identify_false_positives import MatchFirstFalsePositiveAnalyzer
from reporting.models import ReportPaths


@dataclass(frozen=True)
class LoadedDatasets:
    raw: pd.DataFrame
    dedup: pd.DataFrame
    analyzed: pd.DataFrame
    filtered: pd.DataFrame


def normalize_true(value: object) -> str:
    s = "" if pd.isna(value) else str(value).strip()
    return "TRUE" if s.lower() == "true" else s


def canonical_pattern(row: pd.Series) -> str:
    return " | ".join(sorted((str(row["Callee_A"]).strip(), str(row["Callee_B"]).strip())))


def variability_class(pc_a: str, pc_b: str) -> str:
    a_true = pc_a == "TRUE"
    b_true = pc_b == "TRUE"
    if a_true and b_true:
        return "none"
    if (not a_true) and (not b_true):
        return "total"
    return "partial"


def normalize_output(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["PC_A"] = out["PC_A"].map(normalize_true)
    out["PC_B"] = out["PC_B"].map(normalize_true)
    out["Pattern"] = out.apply(canonical_pattern, axis=1)
    out["VarClass"] = out.apply(lambda r: variability_class(r["PC_A"], r["PC_B"]), axis=1)
    out["IsViolation"] = out["Violation"].astype(str).str.upper() == "YES"
    if "FPStatus" not in out.columns:
        out["FPStatus"] = "NotAnalyzed"
    if "FPReason" not in out.columns:
        out["FPReason"] = ""
    return out


def ensure_fp_analysis(
    dedup_path: Path,
    analyzed_path: Path,
    filtered_path: Path,
) -> None:
    if analyzed_path.exists() and filtered_path.exists():
        return
    analyzer = MatchFirstFalsePositiveAnalyzer()
    analyzer.analyze_file(
        input_path=str(dedup_path),
        output_path=str(analyzed_path),
        filtered_output_path=str(filtered_path),
    )


def load_datasets(
    raw_path: Path,
    dedup_path: Path,
    report_paths: ReportPaths,
) -> LoadedDatasets:
    ensure_fp_analysis(
        dedup_path=dedup_path,
        analyzed_path=report_paths.fp_analysis_path,
        filtered_path=report_paths.filtered_output_path,
    )

    raw = normalize_output(pd.read_csv(raw_path))
    dedup = normalize_output(pd.read_csv(dedup_path))
    analyzed = normalize_output(pd.read_csv(report_paths.fp_analysis_path))
    filtered = normalize_output(pd.read_csv(report_paths.filtered_output_path))
    return LoadedDatasets(raw=raw, dedup=dedup, analyzed=analyzed, filtered=filtered)

