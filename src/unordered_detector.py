from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import csv
import os

import pandas as pd

from pc_utils import SENTINELS, is_valid_pc, normalize_pc

GroupKey = Tuple[str, str, str]  # (Project, File, Caller)


@dataclass(frozen=True)
class Pattern:
    """Catalog pattern row (A,B) exactly as provided by patterns_unordered_test.csv."""
    callee_a: str
    callee_b: str


@dataclass(frozen=True)
class EvaluationRow:
    """
    Output row (violations + non-violations), faithful to the catalog direction only.

    Columns (fixed):
      Project, File, Caller, Callee_A, Callee_B, PC_A, PC_B, Violation

    Semantics:
    - PC_A and PC_B are SINGLE presence-condition strings from the input pc CSV (normalized).
    - One row is emitted for each (pc_a, pc_b) in PCs(A) x PCs(B).
    - Violation rule (simple/strong):
        Violation = YES iff PC_A != PC_B, else NO.
    - We DO NOT generate reversed pairs unless they exist in the catalog input.
    - We ONLY report rows when BOTH A and B exist in the caller group.
    """
    project: str
    file: str
    caller: str
    callee_a: str
    callee_b: str
    pc_a: str
    pc_b: str
    violation: str  # "YES" or "NO"


class UnorderedViolationDetector:
    """
    Catalog-faithful detector for unordered patterns (TEST).

    For each group = (Project, File, Caller) and each catalog pair (A,B):
      - If BOTH A and B occur in the group:
          For every (pc_a, pc_b) in PCs(A) x PCs(B):
              Output Violation=YES if pc_a != pc_b else NO.
      - Otherwise: output nothing (per your rule "report only when both exist").

    PC handling:
      - PC must be non-empty (TRUE allowed).
      - Sentinel PCs are ignored for logic (SENTINELS).
      - Invalid PCs are ignored (is_valid_pc).
      - PCs are normalized with normalize_pc for stable string comparison.
    """

    def __init__(self, patterns: List[Pattern]) -> None:
        self.patterns = patterns

    @staticmethod
    def load_patterns(patterns_csv_path: str) -> List[Pattern]:
        df = pd.read_csv(patterns_csv_path)
        required = {"antecedents", "consequents"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"[patterns] Missing columns: {sorted(missing)}")

        out: List[Pattern] = []
        for _, r in df.iterrows():
            a = str(r["antecedents"]).strip()
            b = str(r["consequents"]).strip()
            if not a or not b:
                continue
            out.append(Pattern(callee_a=a, callee_b=b))
        return out

    @staticmethod
    def build_pc_index(pc_csv_path: str, chunksize: int = 200_000) -> Dict[GroupKey, Dict[str, Set[str]]]:
        """Builds: pc_map[group][callee] -> set(PC)."""
        required_cols = {"Project", "File", "Caller", "Callee", "PC"}
        pc_map: Dict[GroupKey, Dict[str, Set[str]]] = {}

        for chunk in pd.read_csv(pc_csv_path, chunksize=chunksize):
            missing = required_cols - set(chunk.columns)
            if missing:
                raise ValueError(f"[pc_csv] Missing columns: {sorted(missing)}")

            for _, r in chunk.iterrows():
                project = str(r["Project"])
                file_ = str(r["File"])
                caller = str(r["Caller"])
                callee = str(r["Callee"]).strip()
                pc_raw = "" if pd.isna(r["PC"]) else str(r["PC"]).strip()

                if pc_raw == "":
                    continue
                if pc_raw in SENTINELS:
                    continue
                if not is_valid_pc(pc_raw):
                    continue

                pc_norm = normalize_pc(pc_raw)
                if pc_norm == "":
                    continue

                g: GroupKey = (project, file_, caller)
                pc_map.setdefault(g, {}).setdefault(callee, set()).add(pc_norm)

        return pc_map

    def evaluate(self, pc_map: Dict[GroupKey, Dict[str, Set[str]]]) -> List[EvaluationRow]:
        """
        Returns rows for both violations and non-violations (YES/NO).
        """
        rows: List[EvaluationRow] = []

        for (project, file_, caller), cmap in pc_map.items():
            for pat in self.patterns:
                A = pat.callee_a
                B = pat.callee_b

                pcs_a = cmap.get(A)
                pcs_b = cmap.get(B)
                if not pcs_a or not pcs_b:
                    continue  # only report when both exist

                for pc_a in sorted(pcs_a):
                    for pc_b in sorted(pcs_b):
                        rows.append(
                            EvaluationRow(
                                project=project,
                                file=file_,
                                caller=caller,
                                callee_a=A,
                                callee_b=B,
                                pc_a=pc_a,
                                pc_b=pc_b,
                                violation="YES" if pc_a != pc_b else "NO",
                            )
                        )

        return rows

    @staticmethod
    def write_csv(out_path: str, rows: List[EvaluationRow]) -> int:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        fieldnames = ["Project", "File", "Caller", "Callee_A", "Callee_B", "PC_A", "PC_B", "Violation"]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow({
                    "Project": r.project,
                    "File": r.file,
                    "Caller": r.caller,
                    "Callee_A": r.callee_a,
                    "Callee_B": r.callee_b,
                    "PC_A": r.pc_a,
                    "PC_B": r.pc_b,
                    "Violation": r.violation,
                })
        return len(rows)