from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple


RowDict = Dict[str, str]
RequiredCols = Tuple[str, ...]


@dataclass(frozen=True)
class DedupStats:
    input_rows: int
    output_rows: int
    dropped_rows: int

    @property
    def reduction_ratio(self) -> float:
        if self.input_rows == 0:
            return 0.0
        return self.dropped_rows / self.input_rows


class UnorderedViolationCanonicalizer:
    """
    Build a canonical key for unordered-string detector rows.

    Two rows are treated as duplicates when they represent the same:
    - location context: (Project, File, Caller)
    - unordered API pair: {Callee_A, Callee_B}
    - unordered PC pair: {PC_A, PC_B}
    - Violation label
    """

    REQUIRED_COLUMNS: RequiredCols = (
        "Project",
        "File",
        "Caller",
        "Callee_A",
        "Callee_B",
        "PC_A",
        "PC_B",
        "Violation",
    )

    @staticmethod
    def _ordered_pair(a: str, b: str) -> Tuple[str, str]:
        return (a, b) if a <= b else (b, a)

    def canonical_key(self, row: Mapping[str, str]) -> Tuple[Tuple[str, str, str], Tuple[str, str], Tuple[str, str], str]:
        group = (
            str(row["Project"]),
            str(row["File"]),
            str(row["Caller"]),
        )
        apis = self._ordered_pair(str(row["Callee_A"]), str(row["Callee_B"]))
        pcs = self._ordered_pair(str(row["PC_A"]), str(row["PC_B"]))
        violation = str(row["Violation"]).strip()
        return (group, apis, pcs, violation)


class UnorderedViolationDeduplicator:
    """
    Streaming deduplicator for unordered-string output CSV.

    Keep strategy: first row seen for each canonical key.
    """

    def __init__(self, canonicalizer: UnorderedViolationCanonicalizer | None = None) -> None:
        self.canonicalizer = canonicalizer or UnorderedViolationCanonicalizer()

    def deduplicate_rows(self, rows: Iterable[RowDict]) -> Tuple[List[RowDict], DedupStats]:
        seen = set()
        kept: List[RowDict] = []
        in_count = 0

        for row in rows:
            in_count += 1
            key = self.canonicalizer.canonical_key(row)
            if key in seen:
                continue
            seen.add(key)
            kept.append(row)

        out_count = len(kept)
        return kept, DedupStats(
            input_rows=in_count,
            output_rows=out_count,
            dropped_rows=in_count - out_count,
        )

    def deduplicate_file(self, input_path: str, output_path: str) -> DedupStats:
        with open(input_path, "r", newline="", encoding="utf-8") as f_in:
            reader = csv.DictReader(f_in)
            if reader.fieldnames is None:
                raise ValueError(f"[dedup] Empty or invalid CSV: {input_path}")

            missing = set(self.canonicalizer.REQUIRED_COLUMNS) - set(reader.fieldnames)
            if missing:
                raise ValueError(f"[dedup] Missing required columns: {sorted(missing)}")

            rows, stats = self.deduplicate_rows(reader)  # type: ignore[arg-type]

        with open(output_path, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return stats

