from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


RequiredColumns = Tuple[str, ...]
PairKey = Tuple[str, str]
ContextKey = Tuple[str, str, str, PairKey]


@dataclass(frozen=True)
class AnalysisStats:
    input_rows: int
    yes_rows: int
    confirmed_false_positives: int
    candidate_violations: int
    no_action_rows: int
    analyzed_contexts: int
    contexts_with_matches: int


class MatchFirstFalsePositiveAnalyzer:
    """
    Identify false positives created by Cartesian cross-products among already matched PCs.

    The detector baseline is preserved:
    - unordered API pairs
    - string comparison on PCs
    - initial detection via Cartesian product

    This analyzer runs *after* detection and deduplication. For each
    (Project, File, Caller, unordered API pair), it:
    1. rebuilds the PC set for each API side
    2. computes exact textual matches between both sides
    3. marks YES rows as confirmed false positives when both PCs already belong to
       the exact-match set for that context
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

    def _build_match_index(
        self, rows: Sequence[Mapping[str, str]]
    ) -> Dict[ContextKey, Dict[str, object]]:
        contexts: Dict[ContextKey, Dict[str, object]] = {}
        pcs_by_context: Dict[ContextKey, Dict[str, set[str]]] = defaultdict(
            lambda: {"left": set(), "right": set()}
        )

        for row in rows:
            context = self._context_key(row)
            pair, (pc_left, pc_right) = self._canonical_pc_pair(row)
            pcs_by_context[context]["left"].add(pc_left)
            pcs_by_context[context]["right"].add(pc_right)
            contexts[context] = {"pair": pair}

        for context, side_sets in pcs_by_context.items():
            matched = set(side_sets["left"]) & set(side_sets["right"])
            only_left = set(side_sets["left"]) - matched
            only_right = set(side_sets["right"]) - matched
            contexts[context].update(
                {
                    "matched": matched,
                    "only_left": only_left,
                    "only_right": only_right,
                }
            )

        return contexts

    def analyze_rows(
        self, rows: Sequence[Mapping[str, str]]
    ) -> Tuple[List[Dict[str, str]], AnalysisStats]:
        context_index = self._build_match_index(rows)
        out_rows: List[Dict[str, str]] = []

        yes_rows = 0
        confirmed_false_positives = 0
        candidate_violations = 0
        no_action_rows = 0

        for row in rows:
            row_out = dict(row)
            context = self._context_key(row)
            pair, (pc_left, pc_right) = self._canonical_pc_pair(row)
            info = context_index[context]
            matched = info["matched"]
            only_left = info["only_left"]
            only_right = info["only_right"]

            violation = str(row["Violation"]).strip().upper()
            if violation == "YES":
                yes_rows += 1
                if pc_left in matched and pc_right in matched:
                    fp_status = "ConfirmedFalsePositive"
                    fp_reason = "cross_product_between_already_matched_pcs"
                    confirmed_false_positives += 1
                else:
                    fp_status = "CandidateViolation"
                    fp_reason = "unmatched_pc_remains"
                    candidate_violations += 1
            else:
                fp_status = "NoAction"
                fp_reason = ""
                no_action_rows += 1

            row_out.update(
                {
                    "PairKey": f"{pair[0]}|{pair[1]}",
                    "MatchedPCsCount": str(len(matched)),
                    "MatchedPCs": " || ".join(sorted(matched)),
                    "OnlyLeftCount": str(len(only_left)),
                    "OnlyLeftPCs": " || ".join(sorted(only_left)),
                    "OnlyRightCount": str(len(only_right)),
                    "OnlyRightPCs": " || ".join(sorted(only_right)),
                    "FPStatus": fp_status,
                    "FPReason": fp_reason,
                }
            )
            out_rows.append(row_out)

        stats = AnalysisStats(
            input_rows=len(rows),
            yes_rows=yes_rows,
            confirmed_false_positives=confirmed_false_positives,
            candidate_violations=candidate_violations,
            no_action_rows=no_action_rows,
            analyzed_contexts=len(context_index),
            contexts_with_matches=sum(
                1 for info in context_index.values() if len(info["matched"]) > 0
            ),
        )
        return out_rows, stats

    def analyze_file(
        self,
        input_path: str,
        output_path: str,
        filtered_output_path: str = "",
    ) -> AnalysisStats:
        with open(input_path, "r", newline="", encoding="utf-8") as f_in:
            reader = csv.DictReader(f_in)
            if reader.fieldnames is None:
                raise ValueError(f"[fp] Empty or invalid CSV: {input_path}")

            missing = set(self.REQUIRED_COLUMNS) - set(reader.fieldnames)
            if missing:
                raise ValueError(f"[fp] Missing required columns: {sorted(missing)}")

            rows = list(reader)

        analyzed_rows, stats = self.analyze_rows(rows)

        out_fieldnames = list(reader.fieldnames) + [
            "PairKey",
            "MatchedPCsCount",
            "MatchedPCs",
            "OnlyLeftCount",
            "OnlyLeftPCs",
            "OnlyRightCount",
            "OnlyRightPCs",
            "FPStatus",
            "FPReason",
        ]

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=out_fieldnames)
            writer.writeheader()
            writer.writerows(analyzed_rows)

        if filtered_output_path:
            filtered_rows = [
                row
                for row in analyzed_rows
                if row["FPStatus"] != "ConfirmedFalsePositive"
            ]
            os.makedirs(os.path.dirname(filtered_output_path) or ".", exist_ok=True)
            with open(filtered_output_path, "w", newline="", encoding="utf-8") as f_out:
                writer = csv.DictWriter(f_out, fieldnames=out_fieldnames)
                writer.writeheader()
                writer.writerows(filtered_rows)

        return stats


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Identify false positives in unordered detector output using the "
            "Match-First Filtering rule."
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
        help="Path to the analyzed CSV with FPStatus/FPReason columns.",
    )
    ap.add_argument(
        "--filtered-output",
        default="",
        help=(
            "Optional output CSV with ConfirmedFalsePositive rows removed. "
            "Recommended for downstream analysis after manual inspection."
        ),
    )
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    if not os.path.exists(args.input):
        raise FileNotFoundError(f"Input file not found: {args.input}")

    analyzer = MatchFirstFalsePositiveAnalyzer()
    stats = analyzer.analyze_file(
        input_path=args.input,
        output_path=args.output,
        filtered_output_path=args.filtered_output,
    )

    print(f"[fp] input rows:                   {stats.input_rows}")
    print(f"[fp] analyzed contexts:            {stats.analyzed_contexts}")
    print(f"[fp] contexts with matched PCs:    {stats.contexts_with_matches}")
    print(f"[fp] YES rows:                     {stats.yes_rows}")
    print(f"[fp] confirmed false positives:    {stats.confirmed_false_positives}")
    print(f"[fp] candidate violations:         {stats.candidate_violations}")
    print(f"[fp] no-action rows:               {stats.no_action_rows}")
    print(f"[fp] wrote analyzed output:        {args.output}")
    if args.filtered_output:
        print(f"[fp] wrote filtered output:        {args.filtered_output}")


if __name__ == "__main__":
    main()
