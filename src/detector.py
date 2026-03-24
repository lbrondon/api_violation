from __future__ import annotations

import os
import csv

from dataclasses import dataclass
from typing import Dict, Set, Tuple, List
from collections import defaultdict

import pandas as pd

from pc_utils import SENTINELS, normalize_pc, or_aggregate, is_valid_pc
from csv_io import PatternRow


GroupKey = Tuple[str, str, str]  # (Project, File, Caller)


@dataclass
class PCIndex:
    # pc_map[group][callee] -> set(PC)
    pc_map: Dict[GroupKey, Dict[str, Set[str]]]
    # pc_errors[group] -> set(sentinel strings)
    pc_errors: Dict[GroupKey, Set[str]]


def build_pc_index(pc_csv_path: str, chunksize: int = 200_000) -> PCIndex:
    """
    Milestone 1:
    Build an index:
      (Project, File, Caller) -> Callee -> {PCs}

    Rules:
    - "TRUE" is stored as a normal PC meaning unconditional occurrence.
    - SENTINELS are excluded from logical processing but recorded in pc_errors.
    """
    pc_map: Dict[GroupKey, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    pc_errors: Dict[GroupKey, Set[str]] = defaultdict(set)

    for chunk in pd.read_csv(pc_csv_path, chunksize=chunksize):
        required = {"Project", "File", "Caller", "Callee", "PC"}
        missing = required - set(chunk.columns)
        if missing:
            raise ValueError(f"[pc_csv] Missing columns: {sorted(missing)}")

        # Iterating rows is slower than vectorized ops, but safe and simple for M1.
        for _, r in chunk.iterrows():
            g: GroupKey = (str(r["Project"]), str(r["File"]), str(r["Caller"]))
            callee = str(r["Callee"]).strip()
            pc_raw = "" if pd.isna(r["PC"]) else str(r["PC"]).strip()

            if pc_raw in SENTINELS:
                pc_errors[g].add(pc_raw)
                continue

            if pc_raw == "":
                continue


            if not is_valid_pc(pc_raw):
                pc_errors[g].add("PC_INVALID")
                continue
            pc_norm = normalize_pc(pc_raw)
            if not pc_norm:
                # Ignore empty PC strings (we can revisit later)
                continue

            pc_map[g][callee].add(pc_norm)

    return PCIndex(pc_map=dict(pc_map), pc_errors=dict(pc_errors))


def print_index_stats(index: PCIndex, top_k: int = 10) -> None:
    """
    Print basic statistics so we can validate the indexing step.
    """
    groups_from_map = set(index.pc_map.keys())
    groups_from_err = set(index.pc_errors.keys())
    groups_all = groups_from_map | groups_from_err

    num_groups = len(groups_all)
    num_groups_with_errors = sum(
        1 for g in groups_all if g in index.pc_errors and len(index.pc_errors[g]) > 0
    )

    entries = 0  # sum over |PCs| for each (group, callee)
    distinct_callees_total = 0
    for g, cmap in index.pc_map.items():
        distinct_callees_total += len(cmap)
        for pcs in cmap.values():
            entries += len(pcs)

    print("=== PC Index Stats (Milestone 1) ===")
    print(f"Groups total: {num_groups}")
    print(f"Groups with sentinel PC errors: {num_groups_with_errors}")
    print(f"Distinct callees across all groups (sum over groups): {distinct_callees_total}")
    print(f"(group, callee, pc) entries: {entries}")

    # Top callees by the number of groups in which they appear
    callee_to_groups = defaultdict(set)  # callee -> set(groups)
    for g, cmap in index.pc_map.items():
        for callee in cmap.keys():
            callee_to_groups[callee].add(g)

    top = sorted(callee_to_groups.items(), key=lambda kv: len(kv[1]), reverse=True)[:top_k]
    print(f"\nTop {top_k} callees by #groups:")
    for callee, gs in top:
        print(f"  {callee}: {len(gs)} groups")

def run_short_circuit_detection(
    patterns: List[PatternRow],
    index: PCIndex,
    output_dir: str,
) -> None:
    """
    Milestone 2:
    Generate violations_summary.csv and violations_evidence.csv using only short-circuit rules.
    No SAT is used here.
    """
    os.makedirs(output_dir, exist_ok=True)

    summary_path = os.path.join(output_dir, "violations_summary.csv")
    evidence_path = os.path.join(output_dir, "violations_evidence.csv")

    # Union of groups: those with valid PCs and/or sentinel errors
    groups_all = set(index.pc_map.keys()) | set(index.pc_errors.keys())

    with open(summary_path, "w", newline="", encoding="utf-8") as fs, \
         open(evidence_path, "w", newline="", encoding="utf-8") as fe:

        summary_writer = csv.DictWriter(
            fs,
            fieldnames=[
                "Project", "File", "Caller",
                "Antecedent", "Consequent",
                "Support", "Confidence", "Lift",
                "Violation", "ViolationType", "Method",
                "PC_A_agg", "PC_B_agg", "NumA_PCs", "NumB_PCs",
                "AnalysisStatus", "PcErrorKinds",
            ],
        )
        summary_writer.writeheader()

        evidence_writer = csv.DictWriter(
            fe,
            fieldnames=[
                "Project", "File", "Caller",
                "Antecedent", "Consequent",
                "Callee", "Role", "PC", "PcStatus",
                "AnalysisStatus", "PcErrorKinds",
            ],
        )
        evidence_writer.writeheader()

        for g in groups_all:
            project, file_, caller = g
            errors = index.pc_errors.get(g, set())
            has_errors = len(errors) > 0
            error_kinds = "|".join(sorted(errors)) if has_errors else ""

            analysis_status = "HAS_PC_ERRORS" if has_errors else "OK"

            # Local map: callee -> set(PCs)
            cmap = index.pc_map.get(g, {})

            for p in patterns:
                A = p.antecedents
                B = p.consequents

                PCs_A = cmap.get(A, set())
                PCs_B = cmap.get(B, set())

                PC_A_agg = or_aggregate(set(PCs_A))
                PC_B_agg = or_aggregate(set(PCs_B))

                a_present = (PC_A_agg != "FALSE")
                b_present = (PC_B_agg != "FALSE")

                # Short-circuit unordered logic
                if not a_present and not b_present:
                    violation = "NO"
                    vtype = "None"
                elif a_present and not b_present:
                    violation = "YES"
                    vtype = "MissingConsequent"
                elif b_present and not a_present:
                    violation = "YES"
                    vtype = "OrphanConsequent"
                else:
                    # both present: we cannot decide mismatch without SAT
                    violation = "NO"
                    vtype = "None"

                method = "SHORT_CIRCUIT"

                summary_writer.writerow({
                    "Project": project,
                    "File": file_,
                    "Caller": caller,
                    "Antecedent": A,
                    "Consequent": B,
                    "Support": p.support,
                    "Confidence": p.confidence,
                    "Lift": p.lift,
                    "Violation": violation,
                    "ViolationType": vtype,
                    "Method": method,
                    "PC_A_agg": PC_A_agg,
                    "PC_B_agg": PC_B_agg,
                    "NumA_PCs": len(PCs_A),
                    "NumB_PCs": len(PCs_B),
                    "AnalysisStatus": analysis_status,
                    "PcErrorKinds": error_kinds,
                })

                # Evidence: only for YES or groups with PC errors
                if violation == "YES" or has_errors:
                    # A-side evidence
                    if PCs_A:
                        for pc in sorted(PCs_A):
                            evidence_writer.writerow({
                                "Project": project,
                                "File": file_,
                                "Caller": caller,
                                "Antecedent": A,
                                "Consequent": B,
                                "Callee": A,
                                "Role": "Antecedent",
                                "PC": pc,
                                "PcStatus": "OK",
                                "AnalysisStatus": analysis_status,
                                "PcErrorKinds": error_kinds,
                            })
                    # B-side evidence
                    if PCs_B:
                        for pc in sorted(PCs_B):
                            evidence_writer.writerow({
                                "Project": project,
                                "File": file_,
                                "Caller": caller,
                                "Antecedent": A,
                                "Consequent": B,
                                "Callee": B,
                                "Role": "Consequent",
                                "PC": pc,
                                "PcStatus": "OK",
                                "AnalysisStatus": analysis_status,
                                "PcErrorKinds": error_kinds,
                            })

                    # Sentinel evidence (if any)
                    if has_errors:
                        for err in sorted(errors):
                            evidence_writer.writerow({
                                "Project": project,
                                "File": file_,
                                "Caller": caller,
                                "Antecedent": A,
                                "Consequent": B,
                                "Callee": "",
                                "Role": "Sentinel",
                                "PC": err,
                                "PcStatus": "SENTINEL_IGNORED",
                                "AnalysisStatus": analysis_status,
                                "PcErrorKinds": error_kinds,
                            })

    print(f"[M2] Wrote summary:  {summary_path}")
    print(f"[M2] Wrote evidence: {evidence_path}")


def run_string_mismatch_detection(
    patterns: List[PatternRow],
    index: PCIndex,
    output_dir: str,
) -> None:
    """
    Milestone 3 (STRING):
    Generate violations_summary_string.csv and violations_evidence_string.csv using a strong rule:
      Violation = YES whenever PCs_A != PCs_B (when both sides exist in the group).

    Notes:
    - Sentinel PC rows and invalid PCs are excluded from set comparisons but recorded in PcErrorKinds.
    - This is a preliminary baseline (string-based), not a semantic equivalence check.
    """
    os.makedirs(output_dir, exist_ok=True)

    summary_path = os.path.join(output_dir, "violations_summary_string.csv")
    evidence_path = os.path.join(output_dir, "violations_evidence_string.csv")

    groups_all = set(index.pc_map.keys()) | set(index.pc_errors.keys())

    with open(summary_path, "w", newline="", encoding="utf-8") as fs, \
         open(evidence_path, "w", newline="", encoding="utf-8") as fe:

        summary_writer = csv.DictWriter(
            fs,
            fieldnames=[
                "Project", "File", "Caller",
                "Antecedent", "Consequent",
                "Support", "Confidence", "Lift",
                "Violation", "ViolationType", "Method",
                "PC_A_agg", "PC_B_agg", "NumA_PCs", "NumB_PCs",
                "AnalysisStatus", "PcErrorKinds",
            ],
        )
        summary_writer.writeheader()

        evidence_writer = csv.DictWriter(
            fe,
            fieldnames=[
                "Project", "File", "Caller",
                "Antecedent", "Consequent",
                "Callee", "Role", "PC", "PcStatus",
                "AnalysisStatus", "PcErrorKinds",
            ],
        )
        evidence_writer.writeheader()

        for g in groups_all:
            project, file_, caller = g
            errors = index.pc_errors.get(g, set())
            has_errors = len(errors) > 0
            error_kinds = "|".join(sorted(errors)) if has_errors else ""
            analysis_status = "HAS_PC_ERRORS" if has_errors else "OK"

            cmap = index.pc_map.get(g, {})

            for p in patterns:
                A = p.antecedents
                B = p.consequents

                PCs_A = set(cmap.get(A, set()))
                PCs_B = set(cmap.get(B, set()))

                PC_A_agg = or_aggregate(PCs_A)
                PC_B_agg = or_aggregate(PCs_B)

                a_present = (PC_A_agg != "FALSE")
                b_present = (PC_B_agg != "FALSE")

                method = "STRING_SET_COMPARE"

                if not a_present and not b_present:
                    violation, vtype = "NO", "None"
                elif a_present and not b_present:
                    violation, vtype = "YES", "MissingConsequent"
                elif b_present and not a_present:
                    violation, vtype = "YES", "OrphanConsequent"
                else:
                    # Both present -> strong mismatch rule
                    if PCs_A != PCs_B:
                        violation, vtype = "YES", "PcSetMismatch"
                    else:
                        violation, vtype = "NO", "None"

                summary_writer.writerow({
                    "Project": project,
                    "File": file_,
                    "Caller": caller,
                    "Antecedent": A,
                    "Consequent": B,
                    "Support": p.support,
                    "Confidence": p.confidence,
                    "Lift": p.lift,
                    "Violation": violation,
                    "ViolationType": vtype,
                    "Method": method,
                    "PC_A_agg": PC_A_agg,
                    "PC_B_agg": PC_B_agg,
                    "NumA_PCs": len(PCs_A),
                    "NumB_PCs": len(PCs_B),
                    "AnalysisStatus": analysis_status,
                    "PcErrorKinds": error_kinds,
                })

                # Evidence only when YES or group has errors
                if violation == "YES" or has_errors:
                    for pc in sorted(PCs_A):
                        evidence_writer.writerow({
                            "Project": project,
                            "File": file_,
                            "Caller": caller,
                            "Antecedent": A,
                            "Consequent": B,
                            "Callee": A,
                            "Role": "Antecedent",
                            "PC": pc,
                            "PcStatus": "OK",
                            "AnalysisStatus": analysis_status,
                            "PcErrorKinds": error_kinds,
                        })
                    for pc in sorted(PCs_B):
                        evidence_writer.writerow({
                            "Project": project,
                            "File": file_,
                            "Caller": caller,
                            "Antecedent": A,
                            "Consequent": B,
                            "Callee": B,
                            "Role": "Consequent",
                            "PC": pc,
                            "PcStatus": "OK",
                            "AnalysisStatus": analysis_status,
                            "PcErrorKinds": error_kinds,
                        })
                    if has_errors:
                        for err in sorted(errors):
                            evidence_writer.writerow({
                                "Project": project,
                                "File": file_,
                                "Caller": caller,
                                "Antecedent": A,
                                "Consequent": B,
                                "Callee": "",
                                "Role": "Sentinel",
                                "PC": err,
                                "PcStatus": "IGNORED",
                                "AnalysisStatus": analysis_status,
                                "PcErrorKinds": error_kinds,
                            })

    print(f"[M3-STRING] Wrote summary:  {summary_path}")
    print(f"[M3-STRING] Wrote evidence: {evidence_path}")


def run_sat_detection(
    patterns: List[PatternRow],
    index: PCIndex,
    output_dir: str,
) -> None:
    """
    Milestone 3:
    Generate violations_summary_sat.csv and violations_evidence_sat.csv using SAT for
    cases where both A and B are present.

    Rules:
    - Keep short-circuit outcomes for absent cases.
    - When both present, compute:
        sat1 = SAT(PC_A_agg && !PC_B_agg)
        sat2 = SAT(PC_B_agg && !PC_A_agg)
      and classify violation type accordingly.
    """
    from sat_engine import SatEngine

    os.makedirs(output_dir, exist_ok=True)

    summary_path = os.path.join(output_dir, "violations_summary_sat.csv")
    evidence_path = os.path.join(output_dir, "violations_evidence_sat.csv")

    groups_all = set(index.pc_map.keys()) | set(index.pc_errors.keys())

    sat = SatEngine()

    with open(summary_path, "w", newline="", encoding="utf-8") as fs, \
         open(evidence_path, "w", newline="", encoding="utf-8") as fe:

        summary_writer = csv.DictWriter(
            fs,
            fieldnames=[
                "Project", "File", "Caller",
                "Antecedent", "Consequent",
                "Support", "Confidence", "Lift",
                "Violation", "ViolationType", "Method",
                "PC_A_agg", "PC_B_agg", "NumA_PCs", "NumB_PCs",
                "AnalysisStatus", "PcErrorKinds",
            ],
        )
        summary_writer.writeheader()

        evidence_writer = csv.DictWriter(
            fe,
            fieldnames=[
                "Project", "File", "Caller",
                "Antecedent", "Consequent",
                "Callee", "Role", "PC", "PcStatus",
                "AnalysisStatus", "PcErrorKinds",
            ],
        )
        evidence_writer.writeheader()

        for g in groups_all:
            project, file_, caller = g
            errors = index.pc_errors.get(g, set())
            has_errors = len(errors) > 0
            error_kinds = "|".join(sorted(errors)) if has_errors else ""
            analysis_status = "HAS_PC_ERRORS" if has_errors else "OK"

            cmap = index.pc_map.get(g, {})

            for p in patterns:
                A = p.antecedents
                B = p.consequents

                PCs_A = cmap.get(A, set())
                PCs_B = cmap.get(B, set())

                PC_A_agg = or_aggregate(set(PCs_A))
                PC_B_agg = or_aggregate(set(PCs_B))

                a_present = (PC_A_agg != "FALSE")
                b_present = (PC_B_agg != "FALSE")

                method = "SHORT_CIRCUIT"
                violation = "NO"
                vtype = "None"

                # --- short-circuit for absent cases ---
                if not a_present and not b_present:
                    violation, vtype, method = "NO", "None", "SHORT_CIRCUIT"
                elif a_present and not b_present:
                    violation, vtype, method = "YES", "MissingConsequent", "SHORT_CIRCUIT"
                elif b_present and not a_present:
                    violation, vtype, method = "YES", "OrphanConsequent", "SHORT_CIRCUIT"
                else:
                    # Both present -> use SAT
                    method = "SAT"
                    sat1 = sat.sat_and_not(PC_A_agg, PC_B_agg)
                    sat2 = sat.sat_and_not(PC_B_agg, PC_A_agg)

                    if sat1 and sat2:
                        violation, vtype = "YES", "Both"
                    elif sat1:
                        violation, vtype = "YES", "MissingConsequent"
                    elif sat2:
                        violation, vtype = "YES", "OrphanConsequent"
                    else:
                        violation, vtype = "NO", "None"

                summary_writer.writerow({
                    "Project": project,
                    "File": file_,
                    "Caller": caller,
                    "Antecedent": A,
                    "Consequent": B,
                    "Support": p.support,
                    "Confidence": p.confidence,
                    "Lift": p.lift,
                    "Violation": violation,
                    "ViolationType": vtype,
                    "Method": method,
                    "PC_A_agg": PC_A_agg,
                    "PC_B_agg": PC_B_agg,
                    "NumA_PCs": len(PCs_A),
                    "NumB_PCs": len(PCs_B),
                    "AnalysisStatus": analysis_status,
                    "PcErrorKinds": error_kinds,
                })

                # Evidence: only for YES or groups with PC errors
                if violation == "YES" or has_errors:
                    if PCs_A:
                        for pc in sorted(PCs_A):
                            evidence_writer.writerow({
                                "Project": project,
                                "File": file_,
                                "Caller": caller,
                                "Antecedent": A,
                                "Consequent": B,
                                "Callee": A,
                                "Role": "Antecedent",
                                "PC": pc,
                                "PcStatus": "OK",
                                "AnalysisStatus": analysis_status,
                                "PcErrorKinds": error_kinds,
                            })
                    if PCs_B:
                        for pc in sorted(PCs_B):
                            evidence_writer.writerow({
                                "Project": project,
                                "File": file_,
                                "Caller": caller,
                                "Antecedent": A,
                                "Consequent": B,
                                "Callee": B,
                                "Role": "Consequent",
                                "PC": pc,
                                "PcStatus": "OK",
                                "AnalysisStatus": analysis_status,
                                "PcErrorKinds": error_kinds,
                            })
                    if has_errors:
                        for err in sorted(errors):
                            evidence_writer.writerow({
                                "Project": project,
                                "File": file_,
                                "Caller": caller,
                                "Antecedent": A,
                                "Consequent": B,
                                "Callee": "",
                                "Role": "Sentinel",
                                "PC": err,
                                "PcStatus": "SENTINEL_IGNORED",
                                "AnalysisStatus": analysis_status,
                                "PcErrorKinds": error_kinds,
                            })

    print(f"[M3] Wrote summary:  {summary_path}")
    print(f"[M3] Wrote evidence: {evidence_path}")
