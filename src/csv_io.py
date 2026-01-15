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
    for _, r in df.iterrows():
        patterns.append(
            PatternRow(
                antecedents=str(r["antecedents"]).strip(),
                consequents=str(r["consequents"]).strip(),
                support=float(r["support"]),
                confidence=float(r["confidence"]),
                lift=float(r["lift"]),
            )
        )
    return patterns


def stream_pc_csv(path: str, chunksize: int = 200_000) -> Iterable[pd.DataFrame]:
    """
    Stream-read a large CSV in chunks to avoid loading everything into memory.
    """
    yield from pd.read_csv(path, chunksize=chunksize)
