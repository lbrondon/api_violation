from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pandas as pd

from reporting.datasets import LoadedDatasets


@dataclass(frozen=True)
class MetricBundle:
    overall: pd.DataFrame
    stage_counts: pd.DataFrame
    pair_summary: pd.DataFrame
    non_violation_pairs: pd.DataFrame
    system_summary: pd.DataFrame
    variability_summary: pd.DataFrame
    fp_summary: pd.DataFrame
    fp_contexts: pd.DataFrame
    pattern_scatter: pd.DataFrame


def _stage_frame(name: str, df: pd.DataFrame) -> Dict[str, object]:
    yes_count = int(df["IsViolation"].sum())
    no_count = int((~df["IsViolation"]).sum())
    return {
        "Stage": name,
        "Rows": int(len(df)),
        "YES": yes_count,
        "NO": no_count,
        "YES_Rate": (yes_count / len(df)) if len(df) else 0.0,
    }


def build_metrics(data: LoadedDatasets) -> MetricBundle:
    stage_counts = pd.DataFrame(
        [
            _stage_frame("raw", data.raw),
            _stage_frame("dedup", data.dedup),
            _stage_frame("analyzed", data.analyzed),
            _stage_frame("filtered", data.filtered),
        ]
    )

    fp_counts = data.analyzed["FPStatus"].astype(str).value_counts()
    overall = pd.DataFrame(
        [
            {
                "systems": int(data.filtered["Project"].nunique()),
                "files": int(data.filtered[["Project", "File"]].drop_duplicates().shape[0]),
                "distinct_patterns": int(data.filtered["Pattern"].nunique()),
                "raw_rows": int(len(data.raw)),
                "dedup_rows": int(len(data.dedup)),
                "filtered_rows": int(len(data.filtered)),
                "raw_violations": int(data.raw["IsViolation"].sum()),
                "dedup_violations": int(data.dedup["IsViolation"].sum()),
                "filtered_violations": int(data.filtered["IsViolation"].sum()),
                "confirmed_false_positives": int(fp_counts.get("ConfirmedFalsePositive", 0)),
                "candidate_violations": int(fp_counts.get("CandidateViolation", 0)),
                "no_action_rows": int(fp_counts.get("NoAction", 0)),
            }
        ]
    )

    pair_summary = (
        data.filtered.groupby("Pattern")
        .agg(
            total_rows=("Pattern", "size"),
            yes_rows=("IsViolation", "sum"),
            projects=("Project", "nunique"),
            files=("File", "nunique"),
        )
        .reset_index()
    )
    pair_summary["no_rows"] = pair_summary["total_rows"] - pair_summary["yes_rows"]
    pair_summary["yes_rate"] = pair_summary["yes_rows"] / pair_summary["total_rows"]
    pair_summary = pair_summary.sort_values(
        ["yes_rows", "yes_rate", "total_rows", "Pattern"], ascending=[False, False, False, True]
    )

    non_violation_pairs = pair_summary.sort_values(
        ["no_rows", "total_rows", "Pattern"], ascending=[False, False, True]
    )

    system_summary = (
        data.filtered.groupby("Project")
        .agg(
            total_rows=("Pattern", "size"),
            yes_rows=("IsViolation", "sum"),
            distinct_patterns=("Pattern", "nunique"),
            files=("File", "nunique"),
        )
        .reset_index()
    )
    system_summary["no_rows"] = system_summary["total_rows"] - system_summary["yes_rows"]
    system_summary["yes_rate"] = system_summary["yes_rows"] / system_summary["total_rows"]
    system_summary = system_summary.sort_values(
        ["yes_rows", "yes_rate", "total_rows", "Project"], ascending=[False, False, False, True]
    )

    variability_summary = (
        data.filtered.groupby(["VarClass", "Violation"])
        .size()
        .reset_index(name="count")
        .sort_values(["VarClass", "Violation"], ascending=[True, True])
    )

    fp_summary = (
        data.analyzed.groupby("FPStatus")
        .size()
        .reset_index(name="count")
        .sort_values(["count", "FPStatus"], ascending=[False, True])
    )

    fp_contexts = (
        data.analyzed[data.analyzed["FPStatus"] == "ConfirmedFalsePositive"]
        .groupby(["Project", "File", "Caller", "PairKey"])
        .size()
        .reset_index(name="confirmed_false_positives")
        .sort_values(
            ["confirmed_false_positives", "Project", "File", "Caller", "PairKey"],
            ascending=[False, True, True, True, True],
        )
    )

    pattern_scatter = pair_summary.copy()
    pattern_scatter["label"] = pattern_scatter["Pattern"]

    return MetricBundle(
        overall=overall,
        stage_counts=stage_counts,
        pair_summary=pair_summary,
        non_violation_pairs=non_violation_pairs,
        system_summary=system_summary,
        variability_summary=variability_summary,
        fp_summary=fp_summary,
        fp_contexts=fp_contexts,
        pattern_scatter=pattern_scatter,
    )

