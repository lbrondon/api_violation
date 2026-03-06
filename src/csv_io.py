from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import pandas as pd


@dataclass(frozen=True)
class PatternRow:
    antecedents: str
    consequents: str
    support: float
    confidence: float
    lift: float


def read_patterns_csv(path: str) -> list[PatternRow]:
    """
    Read patterns_unordered.csv.

    Required columns:
      antecedents, consequents, support, confidence, lift
    """
    df = pd.read_csv(path)

    required = {"antecedents", "consequents", "support", "confidence", "lift"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"[patterns] Missing columns: {sorted(missing)}")

    patterns: list[PatternRow] = []
    seen_pairs: set[tuple[str, str]] = set()
    for _, r in df.iterrows():
        a = str(r["antecedents"]).strip()
        b = str(r["consequents"]).strip()
        if not a or not b:
            continue

        support = float(r["support"])
        confidence = float(r["confidence"])
        lift = float(r["lift"])

        key = (a, b)
        if key not in seen_pairs:
            patterns.append(
                PatternRow(
                    antecedents=a,
                    consequents=b,
                    support=support,
                    confidence=confidence,
                    lift=lift,
                )
            )
            seen_pairs.add(key)

        # Treat catalog as unordered: also include reverse direction once.
        rev = (b, a)
        if a != b and rev not in seen_pairs:
            patterns.append(
                PatternRow(
                    antecedents=b,
                    consequents=a,
                    support=support,
                    confidence=confidence,
                    lift=lift,
                )
            )
            seen_pairs.add(rev)
    return patterns


def stream_pc_csv(path: str, chunksize: int = 200_000) -> Iterable[pd.DataFrame]:
    """
    Stream-read a large CSV in chunks to avoid loading everything into memory.
    """
    yield from pd.read_csv(path, chunksize=chunksize)
