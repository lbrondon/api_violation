from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from pc_utils import normalize_pc

from fp_models import ContextAnalysis, CoverageWitness, LiteralKey, ParsedPC, RowDecision


def _strip_outer_parens(expr: str) -> str:
    s = expr.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        wraps_entire_expr = True
        for idx, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(s) - 1:
                    wraps_entire_expr = False
                    break
        if not wraps_entire_expr:
            break
        s = s[1:-1].strip()
    return s


def _split_top_level(expr: str, operator: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    start = 0
    idx = 0
    while idx < len(expr):
        ch = expr[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expr.startswith(operator, idx):
            parts.append(expr[start:idx].strip())
            idx += len(operator)
            start = idx
            continue
        idx += 1
    parts.append(expr[start:].strip())
    return parts


def _has_top_level_operator(expr: str, operator: str) -> bool:
    depth = 0
    idx = 0
    while idx < len(expr):
        ch = expr[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expr.startswith(operator, idx):
            return True
        idx += 1
    return False


def _literal_sort_key(item: LiteralKey) -> Tuple[str, int]:
    atom, negated = item
    return (atom, 1 if negated else 0)


def _render_literals(literals: Iterable[LiteralKey]) -> str:
    items = sorted({item for item in literals if item[0] != "TRUE"}, key=_literal_sort_key)
    if not items:
        return "TRUE"
    rendered_terms: List[str] = []
    for atom, negated in items:
        if negated:
            rendered_terms.append(f"!({atom})")
        else:
            rendered_terms.append(atom)
    return " && ".join(rendered_terms)


class PresenceConditionParser:
    """
    Lightweight parser for a conservative PC subset.

    Supported syntax:
    - TRUE
    - atom
    - !(atom)
    - conjunctions of the above with top-level &&
    """

    def parse(self, raw_pc: str) -> ParsedPC:
        normalized = normalize_pc(raw_pc)
        if normalized == "":
            return ParsedPC(
                raw=raw_pc,
                normalized=normalized,
                supported=False,
                syntax_kind="EMPTY",
                literals=frozenset(),
                canonical="",
            )

        stripped = _strip_outer_parens(normalized)
        upper = stripped.upper()
        if upper == "TRUE":
            return ParsedPC(
                raw=raw_pc,
                normalized=normalized,
                supported=True,
                syntax_kind="TRUE",
                literals=frozenset(),
                canonical="TRUE",
            )
        if upper == "FALSE":
            return ParsedPC(
                raw=raw_pc,
                normalized=normalized,
                supported=False,
                syntax_kind="FALSE",
                literals=frozenset(),
                canonical="FALSE",
            )
        if _has_top_level_operator(stripped, "||"):
            return ParsedPC(
                raw=raw_pc,
                normalized=normalized,
                supported=False,
                syntax_kind="UNSUPPORTED_OR",
                literals=frozenset(),
                canonical=normalized,
            )

        literals: List[LiteralKey] = []
        for term in _split_top_level(stripped, "&&"):
            literal = self._parse_literal(term)
            if literal is None:
                return ParsedPC(
                    raw=raw_pc,
                    normalized=normalized,
                    supported=False,
                    syntax_kind="UNSUPPORTED_TERM",
                    literals=frozenset(),
                    canonical=normalized,
                )
            if literal[0] != "TRUE":
                literals.append(literal)

        canonical = _render_literals(literals)
        syntax_kind = "LITERAL" if len(literals) == 1 else "CONJUNCTION"
        return ParsedPC(
            raw=raw_pc,
            normalized=normalized,
            supported=True,
            syntax_kind=syntax_kind,
            literals=frozenset(literals),
            canonical=canonical,
        )

    def _parse_literal(self, term: str) -> LiteralKey | None:
        candidate = _strip_outer_parens(normalize_pc(term))
        if candidate == "":
            return None
        upper = candidate.upper()
        if upper == "TRUE":
            return ("TRUE", False)
        if upper == "FALSE":
            return None

        negated = False
        if candidate.startswith("!"):
            negated = True
            candidate = candidate[1:].strip()
            candidate = _strip_outer_parens(candidate)
            if candidate.startswith("!"):
                return None

        if candidate == "" or _has_top_level_operator(candidate, "&&") or _has_top_level_operator(candidate, "||"):
            return None
        return (normalize_pc(candidate), negated)


def build_base_pc(literals: Iterable[LiteralKey]) -> ParsedPC:
    literal_set = frozenset(l for l in literals if l[0] != "TRUE")
    canonical = _render_literals(literal_set)
    syntax_kind = "TRUE" if not literal_set else ("LITERAL" if len(literal_set) == 1 else "CONJUNCTION")
    return ParsedPC(
        raw=canonical,
        normalized=canonical,
        supported=True,
        syntax_kind=syntax_kind,
        literals=literal_set,
        canonical=canonical,
    )


def complementary_base(pc_one: ParsedPC, pc_two: ParsedPC) -> ParsedPC | None:
    if not pc_one.supported or not pc_two.supported:
        return None

    literals_one = {literal for literal in pc_one.literals if literal[0] != "TRUE"}
    literals_two = {literal for literal in pc_two.literals if literal[0] != "TRUE"}

    diff_one = literals_one - literals_two
    diff_two = literals_two - literals_one
    if len(diff_one) != 1 or len(diff_two) != 1:
        return None

    lit_one = next(iter(diff_one))
    lit_two = next(iter(diff_two))
    if lit_one[0] != lit_two[0] or lit_one[1] == lit_two[1]:
        return None

    common_literals = literals_one & literals_two
    return build_base_pc(common_literals)


class FalsePositiveRule(ABC):
    name: str
    priority: int

    @abstractmethod
    def apply(self, context: ContextAnalysis) -> Dict[int, RowDecision]:
        raise NotImplementedError


class MatchFirstRule(FalsePositiveRule):
    name = "match_first_exact_match"
    priority = 10

    def apply(self, context: ContextAnalysis) -> Dict[int, RowDecision]:
        decisions: Dict[int, RowDecision] = {}
        matched = context.matched_pcs
        if not matched:
            return decisions

        for row in context.rows:
            if str(row["Violation"]).strip().upper() != "YES":
                continue
            row_id = int(row["RowId"])
            pc_left = str(row["CanonicalPC_Left"])
            pc_right = str(row["CanonicalPC_Right"])
            if pc_left in matched and pc_right in matched:
                decisions[row_id] = RowDecision(
                    row_id=row_id,
                    fp_status="ConfirmedFalsePositive",
                    fp_reason="cross_product_between_already_matched_pcs",
                    fp_rule=self.name,
                    decision_stage="match_first",
                    fp_rule_priority=self.priority,
                    evidence_type="exact_match",
                    witness=None,
                )
        return decisions


class ComplementaryCoverageRule(FalsePositiveRule):
    name = "complementary_branch_coverage"
    priority = 20

    def apply(self, context: ContextAnalysis) -> Dict[int, RowDecision]:
        decisions: Dict[int, RowDecision] = {}
        witness_index = 0

        side_specs = (
            ("left", context.left_pcs, context.parsed_left, context.parsed_right, True),
            ("right", context.right_pcs, context.parsed_right, context.parsed_left, False),
        )

        for side_name, branch_pcs, branch_parsed, opposite_parsed, branch_is_left in side_specs:
            sorted_branches = sorted(branch_pcs)
            for idx, branch_pc_one in enumerate(sorted_branches):
                parsed_one = branch_parsed.get(branch_pc_one)
                if parsed_one is None or not parsed_one.supported:
                    continue
                for branch_pc_two in sorted_branches[idx + 1:]:
                    parsed_two = branch_parsed.get(branch_pc_two)
                    if parsed_two is None or not parsed_two.supported:
                        continue

                    base_pc = complementary_base(parsed_one, parsed_two)
                    if base_pc is None:
                        continue

                    opposite_matches = sorted(
                        opposite_pc
                        for opposite_pc, parsed_opposite in opposite_parsed.items()
                        if parsed_opposite.supported and parsed_opposite.literals == base_pc.literals
                    )
                    if not opposite_matches:
                        continue

                    for covered_pc in opposite_matches:
                        witness_index += 1
                        witness = CoverageWitness(
                            witness_id=(
                                f"{context.context_key[0]}|{context.context_key[1]}|{context.context_key[2]}|"
                                f"{context.pair_key[0]}|{context.pair_key[1]}|{side_name}|{witness_index}"
                            ),
                            side=side_name,
                            branch_pc_1=branch_pc_one,
                            branch_pc_2=branch_pc_two,
                            covered_pc=covered_pc,
                            base_pc=base_pc.canonical,
                            coverage_kind="two_branch_complement",
                        )

                        affected_pairs = (
                            ((branch_pc_one, covered_pc), (branch_pc_two, covered_pc))
                            if branch_is_left
                            else ((covered_pc, branch_pc_one), (covered_pc, branch_pc_two))
                        )
                        for pair_key in affected_pairs:
                            for row_id in context.yes_row_ids_by_pair.get(pair_key, ()):
                                decisions.setdefault(
                                    row_id,
                                    RowDecision(
                                        row_id=row_id,
                                        fp_status="ConfirmedFalsePositive",
                                        fp_reason="complementary_branch_coverage",
                                        fp_rule=self.name,
                                        decision_stage="complementary_coverage",
                                        fp_rule_priority=self.priority,
                                        evidence_type="branch_partition",
                                        witness=witness,
                                    ),
                                )

        return decisions
