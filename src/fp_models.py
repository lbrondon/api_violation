from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple


PairKey = Tuple[str, str]
ContextKey = Tuple[str, str, str, PairKey]
LiteralKey = Tuple[str, bool]


@dataclass(frozen=True)
class ParsedPC:
    raw: str
    normalized: str
    supported: bool
    syntax_kind: str
    literals: frozenset[LiteralKey]
    canonical: str


@dataclass(frozen=True)
class CoverageWitness:
    witness_id: str
    side: str
    branch_pc_1: str
    branch_pc_2: str
    covered_pc: str
    base_pc: str
    coverage_kind: str


@dataclass(frozen=True)
class RowDecision:
    row_id: int
    fp_status: str
    fp_reason: str
    fp_rule: str
    decision_stage: str
    fp_rule_priority: int
    evidence_type: str
    witness: CoverageWitness | None = None


@dataclass(frozen=True)
class ContextAnalysis:
    context_key: ContextKey
    pair_key: PairKey
    rows: Tuple[Mapping[str, str], ...]
    left_pcs: frozenset[str]
    right_pcs: frozenset[str]
    parsed_left: Mapping[str, ParsedPC]
    parsed_right: Mapping[str, ParsedPC]
    yes_row_ids_by_pair: Mapping[Tuple[str, str], Tuple[int, ...]]
    matched_pcs: frozenset[str]
    only_left_pcs: frozenset[str]
    only_right_pcs: frozenset[str]
