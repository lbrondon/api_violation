from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from fp_models import ContextAnalysis, ContextKey, CoverageWitness, PairKey, ParsedPC, RowDecision
from fp_rules import ComplementaryCoverageRule, MatchFirstRule, PresenceConditionParser


RequiredColumns = Tuple[str, ...]


@dataclass(frozen=True)
class AnalysisStats:
    input_rows: int
    yes_rows: int
    confirmed_false_positives: int
    candidate_violations: int
    no_action_rows: int
    analyzed_contexts: int
    contexts_with_matches: int
    contexts_with_complementary_coverage: int
    coverage_witnesses: int


class MatchFirstFalsePositiveAnalyzer:
    """
    Post-process unordered detector rows with auditable false-positive rules.

    Rule order:
    1. Match-First exact textual matches already supported by the repository.
    2. Complementary branch coverage for syntactic patterns such as X and !(X).

    The detector baseline is preserved:
    - unordered API pairs
    - Cartesian product over PCs
    - string-based violation baseline
    """

    REQUIRED_COLUMNS: RequiredColumns = (
        "Project",
        "File",
        "Caller",
        "Callee_A",
        "Callee_B",
        "PC_A",
        "PC_B",
        "Violation",
    )

    def __init__(self) -> None:
        self.pc_parser = PresenceConditionParser()
        self.rules = tuple(sorted((MatchFirstRule(), ComplementaryCoverageRule()), key=lambda rule: rule.priority))

    @staticmethod
    def _ordered_pair(a: str, b: str) -> PairKey:
        return (a, b) if a <= b else (b, a)

    def _context_key(self, row: Mapping[str, str]) -> ContextKey:
        pair = self._ordered_pair(str(row["Callee_A"]), str(row["Callee_B"]))
        return (
            str(row["Project"]),
            str(row["File"]),
            str(row["Caller"]),
            pair,
        )

    def _canonical_pc_pair(self, row: Mapping[str, str]) -> Tuple[PairKey, Tuple[str, str]]:
        api_a = str(row["Callee_A"])
        api_b = str(row["Callee_B"])
        pc_a = str(row["PC_A"])
        pc_b = str(row["PC_B"])
        pair = self._ordered_pair(api_a, api_b)
        if (api_a, api_b) == pair:
            return pair, (pc_a, pc_b)
        return pair, (pc_b, pc_a)

    def _prepare_rows(self, rows: Sequence[Mapping[str, str]]) -> List[Dict[str, str]]:
        prepared_rows: List[Dict[str, str]] = []
        for row_id, row in enumerate(rows, start=1):
            pair, (pc_left, pc_right) = self._canonical_pc_pair(row)
            context = self._context_key(row)
            prepared = dict(row)
            prepared["RowId"] = str(row_id)
            prepared["PairKey"] = f"{pair[0]}|{pair[1]}"
            prepared["ContextKey"] = (
                f"{context[0]}|{context[1]}|{context[2]}|{pair[0]}|{pair[1]}"
            )
            prepared["CanonicalCallee_Left"] = pair[0]
            prepared["CanonicalCallee_Right"] = pair[1]
            prepared["CanonicalPC_Left"] = pc_left
            prepared["CanonicalPC_Right"] = pc_right
            prepared_rows.append(prepared)
        return prepared_rows

    def _build_contexts(
        self, rows: Sequence[Mapping[str, str]]
    ) -> Dict[ContextKey, ContextAnalysis]:
        rows_by_context: Dict[ContextKey, List[Mapping[str, str]]] = defaultdict(list)
        left_pcs: Dict[ContextKey, set[str]] = defaultdict(set)
        right_pcs: Dict[ContextKey, set[str]] = defaultdict(set)
        yes_pairs: Dict[ContextKey, Dict[Tuple[str, str], List[int]]] = defaultdict(lambda: defaultdict(list))

        for row in rows:
            context = self._context_key(row)
            pair, (pc_left, pc_right) = self._canonical_pc_pair(row)
            rows_by_context[context].append(row)
            left_pcs[context].add(pc_left)
            right_pcs[context].add(pc_right)
            if str(row["Violation"]).strip().upper() == "YES":
                yes_pairs[context][(pc_left, pc_right)].append(int(row["RowId"]))

        contexts: Dict[ContextKey, ContextAnalysis] = {}
        for context, context_rows in rows_by_context.items():
            left_set = frozenset(sorted(left_pcs[context]))
            right_set = frozenset(sorted(right_pcs[context]))
            parsed_left = {pc: self.pc_parser.parse(pc) for pc in left_set}
            parsed_right = {pc: self.pc_parser.parse(pc) for pc in right_set}
            matched = frozenset(sorted(left_set & right_set))
            only_left = frozenset(sorted(left_set - matched))
            only_right = frozenset(sorted(right_set - matched))

            contexts[context] = ContextAnalysis(
                context_key=context,
                pair_key=context[3],
                rows=tuple(context_rows),
                left_pcs=left_set,
                right_pcs=right_set,
                parsed_left=parsed_left,
                parsed_right=parsed_right,
                yes_row_ids_by_pair={
                    pair_key: tuple(row_ids)
                    for pair_key, row_ids in yes_pairs[context].items()
                },
                matched_pcs=matched,
                only_left_pcs=only_left,
                only_right_pcs=only_right,
            )
        return contexts

    def _default_decision(self, row: Mapping[str, str]) -> RowDecision:
        row_id = int(row["RowId"])
        if str(row["Violation"]).strip().upper() == "YES":
            return RowDecision(
                row_id=row_id,
                fp_status="CandidateViolation",
                fp_reason="unmatched_pc_remains",
                fp_rule="none",
                decision_stage="none",
                fp_rule_priority=999,
                evidence_type="none",
                witness=None,
            )
        return RowDecision(
            row_id=row_id,
            fp_status="NoAction",
            fp_reason="",
            fp_rule="none",
            decision_stage="none",
            fp_rule_priority=999,
            evidence_type="none",
            witness=None,
        )

    def _analyze_context(
        self, context: ContextAnalysis
    ) -> Tuple[List[Dict[str, str]], List[CoverageWitness], Dict[str, object]]:
        decisions: Dict[int, RowDecision] = {}
        for rule in self.rules:
            for row_id, decision in rule.apply(context).items():
                decisions.setdefault(row_id, decision)

        witnesses_by_id: Dict[str, CoverageWitness] = {}
        analyzed_rows: List[Dict[str, str]] = []
        for row in context.rows:
            row_id = int(row["RowId"])
            decision = decisions.get(row_id, self._default_decision(row))
            if decision.witness is not None:
                witnesses_by_id.setdefault(decision.witness.witness_id, decision.witness)

            parsed_left = context.parsed_left[str(row["CanonicalPC_Left"])]
            parsed_right = context.parsed_right[str(row["CanonicalPC_Right"])]
            analyzed = dict(row)
            analyzed.update(
                {
                    "LeftPCCount": str(len(context.left_pcs)),
                    "RightPCCount": str(len(context.right_pcs)),
                    "MatchedPCsCount": str(len(context.matched_pcs)),
                    "MatchedPCs": " || ".join(sorted(context.matched_pcs)),
                    "OnlyLeftCount": str(len(context.only_left_pcs)),
                    "OnlyLeftPCs": " || ".join(sorted(context.only_left_pcs)),
                    "OnlyRightCount": str(len(context.only_right_pcs)),
                    "OnlyRightPCs": " || ".join(sorted(context.only_right_pcs)),
                    "CanonicalPC_Left_Supported": "YES" if parsed_left.supported else "NO",
                    "CanonicalPC_Left_Syntax": parsed_left.syntax_kind,
                    "CanonicalPC_Left_CanonicalForm": parsed_left.canonical,
                    "CanonicalPC_Right_Supported": "YES" if parsed_right.supported else "NO",
                    "CanonicalPC_Right_Syntax": parsed_right.syntax_kind,
                    "CanonicalPC_Right_CanonicalForm": parsed_right.canonical,
                    "FPStatus": decision.fp_status,
                    "FPReason": decision.fp_reason,
                    "FPRule": decision.fp_rule,
                    "FPRulePriority": str(decision.fp_rule_priority),
                    "DecisionStage": decision.decision_stage,
                    "EvidenceType": decision.evidence_type,
                    "CoverageWitnessId": decision.witness.witness_id if decision.witness else "",
                    "CoverageSide": decision.witness.side if decision.witness else "",
                    "CoverageBasePC": decision.witness.base_pc if decision.witness else "",
                    "CoverageBranchPC1": decision.witness.branch_pc_1 if decision.witness else "",
                    "CoverageBranchPC2": decision.witness.branch_pc_2 if decision.witness else "",
                    "CoverageCoveredPC": decision.witness.covered_pc if decision.witness else "",
                    "CoverageKind": decision.witness.coverage_kind if decision.witness else "",
                }
            )
            analyzed_rows.append(analyzed)

        yes_rows_before = sum(1 for row in context.rows if str(row["Violation"]).strip().upper() == "YES")
        confirmed_false_positives = sum(1 for row in analyzed_rows if row["FPStatus"] == "ConfirmedFalsePositive")
        candidate_violations_after = sum(1 for row in analyzed_rows if row["FPStatus"] == "CandidateViolation")
        context_summary = {
            "ContextKey": analyzed_rows[0]["ContextKey"],
            "Project": context.context_key[0],
            "File": context.context_key[1],
            "Caller": context.context_key[2],
            "PairKey": analyzed_rows[0]["PairKey"],
            "CanonicalCallee_Left": context.pair_key[0],
            "CanonicalCallee_Right": context.pair_key[1],
            "LeftPCCount": str(len(context.left_pcs)),
            "RightPCCount": str(len(context.right_pcs)),
            "MatchedPCsCount": str(len(context.matched_pcs)),
            "MatchedPCs": " || ".join(sorted(context.matched_pcs)),
            "OnlyLeftCount": str(len(context.only_left_pcs)),
            "OnlyLeftPCs": " || ".join(sorted(context.only_left_pcs)),
            "OnlyRightCount": str(len(context.only_right_pcs)),
            "OnlyRightPCs": " || ".join(sorted(context.only_right_pcs)),
            "YesRowsBefore": str(yes_rows_before),
            "ConfirmedFalsePositives": str(confirmed_false_positives),
            "CandidateViolationsAfter": str(candidate_violations_after),
            "CoverageWitnessCount": str(len(witnesses_by_id)),
            "CoverageBases": " || ".join(sorted({w.base_pc for w in witnesses_by_id.values()})),
            "CoverageSides": " || ".join(sorted({w.side for w in witnesses_by_id.values()})),
        }

        return analyzed_rows, sorted(witnesses_by_id.values(), key=lambda witness: witness.witness_id), context_summary

    def analyze_rows(
        self, rows: Sequence[Mapping[str, str]]
    ) -> Tuple[List[Dict[str, str]], AnalysisStats, List[Dict[str, str]], List[Dict[str, str]]]:
        prepared_rows = self._prepare_rows(rows)
        context_index = self._build_contexts(prepared_rows)

        analyzed_rows: List[Dict[str, str]] = []
        context_rows: List[Dict[str, str]] = []
        coverage_rows: List[Dict[str, str]] = []

        contexts_with_coverage = 0
        for context_key in sorted(context_index.keys()):
            context = context_index[context_key]
            rows_out, witnesses, context_summary = self._analyze_context(context)
            analyzed_rows.extend(rows_out)
            context_rows.append(context_summary)
            if witnesses:
                contexts_with_coverage += 1
            for witness in witnesses:
                affected_row_ids = sorted(
                    row["RowId"]
                    for row in rows_out
                    if row["CoverageWitnessId"] == witness.witness_id
                )
                coverage_rows.append(
                    {
                        "CoverageWitnessId": witness.witness_id,
                        "ContextKey": context_summary["ContextKey"],
                        "Project": context.context_key[0],
                        "File": context.context_key[1],
                        "Caller": context.context_key[2],
                        "PairKey": context_summary["PairKey"],
                        "CoverageSide": witness.side,
                        "BasePC": witness.base_pc,
                        "BranchPC1": witness.branch_pc_1,
                        "BranchPC2": witness.branch_pc_2,
                        "CoveredPC": witness.covered_pc,
                        "CoverageKind": witness.coverage_kind,
                        "AffectedRowCount": str(len(affected_row_ids)),
                        "AffectedRowIds": " || ".join(affected_row_ids),
                    }
                )

        yes_rows = sum(1 for row in analyzed_rows if str(row["Violation"]).strip().upper() == "YES")
        confirmed_false_positives = sum(1 for row in analyzed_rows if row["FPStatus"] == "ConfirmedFalsePositive")
        candidate_violations = sum(1 for row in analyzed_rows if row["FPStatus"] == "CandidateViolation")
        no_action_rows = sum(1 for row in analyzed_rows if row["FPStatus"] == "NoAction")
        stats = AnalysisStats(
            input_rows=len(analyzed_rows),
            yes_rows=yes_rows,
            confirmed_false_positives=confirmed_false_positives,
            candidate_violations=candidate_violations,
            no_action_rows=no_action_rows,
            analyzed_contexts=len(context_index),
            contexts_with_matches=sum(
                1 for context in context_index.values() if len(context.matched_pcs) > 0
            ),
            contexts_with_complementary_coverage=contexts_with_coverage,
            coverage_witnesses=len(coverage_rows),
        )
        return analyzed_rows, stats, context_rows, coverage_rows

    @staticmethod
    def _write_csv(path: str, rows: Sequence[Mapping[str, str]], fieldnames: Sequence[str]) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _default_output_path(base_output_path: str, suffix: str) -> str:
        stem, ext = os.path.splitext(base_output_path)
        return f"{stem}_{suffix}{ext or '.csv'}"

    def analyze_file(
        self,
        input_path: str,
        output_path: str,
        filtered_output_path: str = "",
        violations_output_path: str = "",
        filtered_violations_output_path: str = "",
        context_summary_output_path: str = "",
        coverage_output_path: str = "",
    ) -> AnalysisStats:
        with open(input_path, "r", newline="", encoding="utf-8") as f_in:
            reader = csv.DictReader(f_in)
            if reader.fieldnames is None:
                raise ValueError(f"[fp] Empty or invalid CSV: {input_path}")

            missing = set(self.REQUIRED_COLUMNS) - set(reader.fieldnames)
            if missing:
                raise ValueError(f"[fp] Missing required columns: {sorted(missing)}")

            rows = list(reader)

        analyzed_rows, stats, context_rows, coverage_rows = self.analyze_rows(rows)

        if not filtered_output_path:
            filtered_output_path = self._default_output_path(output_path, "filtered_all")
        if not violations_output_path:
            violations_output_path = self._default_output_path(output_path, "violations_all")
        if not filtered_violations_output_path:
            filtered_violations_output_path = self._default_output_path(output_path, "violations_filtered")
        if not context_summary_output_path:
            context_summary_output_path = self._default_output_path(output_path, "context_summary")
        if not coverage_output_path:
            coverage_output_path = self._default_output_path(output_path, "coverage_evidence")

        input_fieldnames = list(reader.fieldnames)
        analysis_fieldnames = input_fieldnames + [
            "RowId",
            "ContextKey",
            "PairKey",
            "CanonicalCallee_Left",
            "CanonicalCallee_Right",
            "CanonicalPC_Left",
            "CanonicalPC_Right",
            "LeftPCCount",
            "RightPCCount",
            "MatchedPCsCount",
            "MatchedPCs",
            "OnlyLeftCount",
            "OnlyLeftPCs",
            "OnlyRightCount",
            "OnlyRightPCs",
            "CanonicalPC_Left_Supported",
            "CanonicalPC_Left_Syntax",
            "CanonicalPC_Left_CanonicalForm",
            "CanonicalPC_Right_Supported",
            "CanonicalPC_Right_Syntax",
            "CanonicalPC_Right_CanonicalForm",
            "FPStatus",
            "FPReason",
            "FPRule",
            "FPRulePriority",
            "DecisionStage",
            "EvidenceType",
            "CoverageWitnessId",
            "CoverageSide",
            "CoverageBasePC",
            "CoverageBranchPC1",
            "CoverageBranchPC2",
            "CoverageCoveredPC",
            "CoverageKind",
        ]

        self._write_csv(output_path, analyzed_rows, analysis_fieldnames)

        filtered_rows = [
            row for row in analyzed_rows if row["FPStatus"] != "ConfirmedFalsePositive"
        ]
        self._write_csv(filtered_output_path, filtered_rows, analysis_fieldnames)

        all_violation_rows = [
            row for row in analyzed_rows if str(row["Violation"]).strip().upper() == "YES"
        ]
        self._write_csv(violations_output_path, all_violation_rows, analysis_fieldnames)

        filtered_violation_rows = [
            row
            for row in analyzed_rows
            if str(row["Violation"]).strip().upper() == "YES"
            and row["FPStatus"] != "ConfirmedFalsePositive"
        ]
        self._write_csv(filtered_violations_output_path, filtered_violation_rows, analysis_fieldnames)

        context_fieldnames = [
            "ContextKey",
            "Project",
            "File",
            "Caller",
            "PairKey",
            "CanonicalCallee_Left",
            "CanonicalCallee_Right",
            "LeftPCCount",
            "RightPCCount",
            "MatchedPCsCount",
            "MatchedPCs",
            "OnlyLeftCount",
            "OnlyLeftPCs",
            "OnlyRightCount",
            "OnlyRightPCs",
            "YesRowsBefore",
            "ConfirmedFalsePositives",
            "CandidateViolationsAfter",
            "CoverageWitnessCount",
            "CoverageBases",
            "CoverageSides",
        ]
        self._write_csv(context_summary_output_path, context_rows, context_fieldnames)

        coverage_fieldnames = [
            "CoverageWitnessId",
            "ContextKey",
            "Project",
            "File",
            "Caller",
            "PairKey",
            "CoverageSide",
            "BasePC",
            "BranchPC1",
            "BranchPC2",
            "CoveredPC",
            "CoverageKind",
            "AffectedRowCount",
            "AffectedRowIds",
        ]
        self._write_csv(coverage_output_path, coverage_rows, coverage_fieldnames)

        return stats


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Identify false positives in unordered detector output using layered "
            "post-processing rules and emit notebook-friendly CSVs."
        )
    )
    ap.add_argument(
        "--input",
        required=True,
        help="Path to the deduplicated unordered detector CSV.",
    )
    ap.add_argument(
        "--output",
        required=True,
        help="Path to the main analyzed CSV with one row per detector result.",
    )
    ap.add_argument(
        "--filtered-output",
        default="",
        help=(
            "Optional CSV with all rows except ConfirmedFalsePositive. "
            "Default: derived automatically from --output."
        ),
    )
    ap.add_argument(
        "--violations-output",
        default="",
        help=(
            "Optional CSV with only violation rows before removing false positives. "
            "Default: derived automatically from --output."
        ),
    )
    ap.add_argument(
        "--filtered-violations-output",
        default="",
        help=(
            "Optional CSV with only violation rows after removing false positives. "
            "Default: derived automatically from --output."
        ),
    )
    ap.add_argument(
        "--context-summary-output",
        default="",
        help=(
            "Optional CSV with one row per (Project, File, Caller, unordered API pair). "
            "Default: derived automatically from --output."
        ),
    )
    ap.add_argument(
        "--coverage-output",
        default="",
        help=(
            "Optional CSV with one row per complementary coverage witness. "
            "Default: derived automatically from --output."
        ),
    )
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    if not os.path.exists(args.input):
        raise FileNotFoundError(f"Input file not found: {args.input}")

    analyzer = MatchFirstFalsePositiveAnalyzer()
    filtered_output = args.filtered_output or analyzer._default_output_path(args.output, "filtered_all")
    violations_output = args.violations_output or analyzer._default_output_path(args.output, "violations_all")
    filtered_violations_output = (
        args.filtered_violations_output
        or analyzer._default_output_path(args.output, "violations_filtered")
    )
    context_summary_output = (
        args.context_summary_output
        or analyzer._default_output_path(args.output, "context_summary")
    )
    coverage_output = args.coverage_output or analyzer._default_output_path(args.output, "coverage_evidence")
    stats = analyzer.analyze_file(
        input_path=args.input,
        output_path=args.output,
        filtered_output_path=filtered_output,
        violations_output_path=violations_output,
        filtered_violations_output_path=filtered_violations_output,
        context_summary_output_path=context_summary_output,
        coverage_output_path=coverage_output,
    )

    print(f"[fp] input rows:                        {stats.input_rows}")
    print(f"[fp] analyzed contexts:                 {stats.analyzed_contexts}")
    print(f"[fp] contexts with textual matches:     {stats.contexts_with_matches}")
    print(f"[fp] contexts with branch coverage:     {stats.contexts_with_complementary_coverage}")
    print(f"[fp] complementary coverage witnesses:  {stats.coverage_witnesses}")
    print(f"[fp] YES rows:                          {stats.yes_rows}")
    print(f"[fp] confirmed false positives:         {stats.confirmed_false_positives}")
    print(f"[fp] candidate violations:              {stats.candidate_violations}")
    print(f"[fp] no-action rows:                    {stats.no_action_rows}")
    print(f"[fp] wrote analyzed output:             {args.output}")
    print(f"[fp] wrote filtered all rows:           {filtered_output}")
    print(f"[fp] wrote all violations:              {violations_output}")
    print(f"[fp] wrote filtered violations:         {filtered_violations_output}")
    print(f"[fp] wrote context summary:             {context_summary_output}")
    print(f"[fp] wrote coverage evidence:           {coverage_output}")


if __name__ == "__main__":
    main()
