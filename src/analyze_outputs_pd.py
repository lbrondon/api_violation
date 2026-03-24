#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Set

import pandas as pd
import textwrap

from identify_false_positives import MatchFirstFalsePositiveAnalyzer


USAGE_EXAMPLES = r"""
Key idea
- PC_A and PC_B should reflect the *raw PC strings* from the original dataset (cs_projects__with_pc.csv).
- Practically, we retrieve them from the evidence file (violations_evidence_string.csv), which stores the raw PC per call edge.

Examples

1) Show FIRST 20 violations (vertical) and include raw PC_A / PC_B values:
   python3 src/analyze_outputs_pd.py \
     --file output/violations_summary_string.csv \
     --evidence output/violations_evidence_string.csv \
     --show-violations 20 \
     --format vertical --display-width 120 \
     --show-pc-values --pc-join " || " \
     --select Project File Caller Antecedent Consequent PC_A_agg PC_B_agg Violation ViolationType

2) Show violations for a specific pair (socket -> close) including raw PC values:
   python3 src/analyze_outputs_pd.py \
     --file output/violations_summary_string.csv \
     --evidence output/violations_evidence_string.csv \
     --where Antecedent=socket --where Consequent=close \
     --show-violations 50 \
     --format vertical --display-width 120 \
     --show-pc-values --pc-join " || " \
     --select Project File Caller Antecedent Consequent PC_A_agg PC_B_agg Violation ViolationType AnalysisStatus PcErrorKinds

3) Counts:
   python3 src/analyze_outputs_pd.py --file output/violations_summary_string.csv --counts Violation ViolationType Method

3) Inspect unordered test output (violations + non-violations already include PC_A/PC_B):
   python3 src/analyze_outputs_pd.py \
     --file output/violations_only_unordered_test.csv \
     --show-violations 50 \
     --format vertical --display-width 120 \
     --select Project File Caller Callee_A Callee_B PC_A PC_B Violation

4) Show ONLY non-violations (Violation=NO) from unordered test output:
   python3 src/analyze_outputs_pd.py \
     --file output/violations_only_unordered_test.csv \
     --show-violation NO \
     --show 50 \
     --format vertical --display-width 120 \
     --select Project File Caller Callee_A Callee_B PC_A PC_B Violation

5) Inspect confirmed false positives from Match-First Filtering:
   python3 src/analyze_outputs_pd.py \
     --file output/violations_unordered_57_cs_projects_with_pc_fp_analysis.csv \
     --show-fp-status ConfirmedFalsePositive \
     --show 20 \
     --format vertical --display-width 140 \
     --select Project File Caller Callee_A Callee_B PC_A PC_B FPStatus FPReason MatchedPCs

6) Show contexts with the largest number of confirmed false positives:
   python3 src/analyze_outputs_pd.py \
     --file output/violations_unordered_57_cs_projects_with_pc_fp_analysis.csv \
     --top-fp-contexts --fp-top-k 20

7) Pattern stats also work for unordered detector outputs:
   python3 src/analyze_outputs_pd.py \
     --file output/violations_unordered_57_cs_projects_with_pc_fp_analysis.csv \
     --pattern-stats --pattern-top-k 20 --pattern-sort yes_count

8) Remove confirmed false positives from a deduplicated unordered output before printing:
   python3 src/analyze_outputs_pd.py \
     --file output/violations_unordered_57_cs_projects_with_pc_dedup.csv \
     --remove-confirmed-fp \
     --show-violations 82 \
     --format vertical --display-width 120 \
     --select Project File Caller Callee_A Callee_B PC_A PC_B Violation

"""


def fast_row_count(path: str) -> int:
    """Fast line count excluding header (no pandas)."""
    with open(path, "rb") as f:
        n = sum(1 for _ in f)
    return max(0, n - 1)


def parse_where(where: List[str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for clause in where:
        if "=" not in clause:
            raise ValueError(f"Invalid --where '{clause}'. Expected KEY=VALUE.")
        k, v = clause.split("=", 1)
        out.append((k.strip(), v.strip()))
    return out


def apply_filters(df: pd.DataFrame, filters: List[Tuple[str, str]]) -> pd.DataFrame:
    for k, v in filters:
        if k not in df.columns:
            raise ValueError(f"Filter column '{k}' not found. Available: {list(df.columns)}")
        df = df[df[k].astype(str) == v]
    return df


def has_filter(filters: List[Tuple[str, str]], key: str) -> bool:
    return any(k == key for (k, _) in filters)


def clean_nan_strings(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = df[c].fillna("")
    return df


def resolve_pattern_columns(columns: Iterable[str]) -> Tuple[str, str]:
    cols = set(columns)
    if {"Antecedent", "Consequent"}.issubset(cols):
        return ("Antecedent", "Consequent")
    if {"Callee_A", "Callee_B"}.issubset(cols):
        return ("Callee_A", "Callee_B")
    raise ValueError(
        "Could not find pair columns. Expected either "
        "['Antecedent', 'Consequent'] or ['Callee_A', 'Callee_B']."
    )


def print_table(df: pd.DataFrame, display_width: int, max_colwidth: int) -> None:
    pd.set_option("display.width", display_width)
    pd.set_option("display.max_columns", 160)
    pd.set_option("display.max_colwidth", max_colwidth)
    print(df.to_string(index=False))


def print_vertical(df: pd.DataFrame, display_width: int) -> None:
    wrap_width = max(60, display_width)
    records = df.to_dict(orient="records")
    for i, row in enumerate(records, start=1):
        print("=" * wrap_width)
        print(f"Row {i}")
        print("-" * wrap_width)
        for k, v in row.items():
            s = "" if v is None else str(v)
            wrapped = textwrap.fill(s, width=wrap_width, subsequent_indent=" " * (len(k) + 2))
            print(f"{k}: {wrapped}")
        print()


def maybe_apply_false_positive_filter(
    chunk: pd.DataFrame,
    remove_confirmed_fp: bool,
) -> pd.DataFrame:
    """
    Optionally remove confirmed false positives.

    If FPStatus already exists, remove rows directly.
    Otherwise, if the chunk follows the unordered-detector schema,
    apply Match-First Filtering in-memory before removing rows.
    """
    if not remove_confirmed_fp or chunk.empty:
        return chunk

    if "FPStatus" in chunk.columns:
        return chunk[chunk["FPStatus"].astype(str) != "ConfirmedFalsePositive"].copy()

    required = {
        "Project",
        "File",
        "Caller",
        "Callee_A",
        "Callee_B",
        "PC_A",
        "PC_B",
        "Violation",
    }
    if not required.issubset(set(chunk.columns)):
        return chunk

    analyzer = MatchFirstFalsePositiveAnalyzer()
    analyzed_rows, _ = analyzer.analyze_rows(chunk.to_dict(orient="records"))
    analyzed_df = pd.DataFrame(analyzed_rows)
    return analyzed_df[analyzed_df["FPStatus"].astype(str) != "ConfirmedFalsePositive"].copy()


def build_evidence_pc_sets(
    evidence_path: str,
    targets: Set[Tuple[str, str, str, str, str]],
    pc_limit: int,
    chunksize: int,
) -> Dict[Tuple[str, str, str, str, str], Dict[str, List[str]]]:
    """
    Build a small index from evidence CSV only for the requested target keys.

    Key: (Project, File, Caller, Antecedent, Consequent)
    Value: {"PC_A": [...], "PC_B": [...]}
    """
    if not evidence_path:
        return {}

    if not os.path.exists(evidence_path):
        raise FileNotFoundError(f"Evidence file not found: {evidence_path}")

    required_cols = {"Project", "File", "Caller", "Antecedent", "Consequent", "Role", "PC"}

    seen_a: Dict[Tuple[str, str, str, str, str], Set[str]] = defaultdict(set)
    seen_b: Dict[Tuple[str, str, str, str, str], Set[str]] = defaultdict(set)

    for chunk in pd.read_csv(evidence_path, chunksize=chunksize):
        missing = required_cols - set(chunk.columns)
        if missing:
            raise ValueError(f"Evidence CSV missing columns: {sorted(missing)}")

        for _, r in chunk.iterrows():
            key = (
                str(r["Project"]),
                str(r["File"]),
                str(r["Caller"]),
                str(r["Antecedent"]),
                str(r["Consequent"]),
            )
            if key not in targets:
                continue

            role = str(r["Role"])
            pc = "" if pd.isna(r["PC"]) else str(r["PC"]).strip()
            if not pc:
                continue

            if role == "Antecedent":
                if len(seen_a[key]) < pc_limit:
                    seen_a[key].add(pc)
            elif role == "Consequent":
                if len(seen_b[key]) < pc_limit:
                    seen_b[key].add(pc)

    out: Dict[Tuple[str, str, str, str, str], Dict[str, List[str]]] = {}
    for key in targets:
        out[key] = {
            "PC_A": sorted(seen_a.get(key, set())),
            "PC_B": sorted(seen_b.get(key, set())),
        }
    return out


def pc_value_from_set(pcs: List[str], joiner: str) -> str:
    """
    Convert a list of raw PCs into a single printable value.
    - 0 PCs -> ""
    - 1 PC  -> that PC
    - >1 PCs -> join with the given joiner
    """
    if not pcs:
        return ""
    if len(pcs) == 1:
        return pcs[0]
    return joiner.join(pcs)


def print_header_summary(
    display_width: int,
    systems_count: int,
    yes_count: int,
    no_count: int,
) -> None:
    wrap_width = max(60, display_width)
    print("=" * wrap_width)
    print("Summary")
    print("-" * wrap_width)
    print(f"Analyzed systems: {systems_count}")
    print(f"Violations: {yes_count}")
    print(f"Non-violations: {no_count}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Analyze huge CSV outputs with pandas (chunked) and print results in the terminal.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=USAGE_EXAMPLES,
    )
    ap.add_argument("--file", required=True, help="Path to a CSV output file (summary/evidence/evaluation).")
    ap.add_argument("--chunksize", type=int, default=200_000, help="Pandas chunksize for streaming reads.")
    ap.add_argument("--info", action="store_true", help="Print header + total data row count.")
    ap.add_argument("--counts", nargs="*", default=[], help="Columns to value_count.")
    ap.add_argument("--where", action="append", default=[], help="Filter clause KEY=VALUE (repeatable).")

    ap.add_argument("--show", type=int, default=50, help="Max rows to show after filtering.")
    ap.add_argument("--show-violation", dest="show_violation", default="",
                    help="If set, filter rows by an explicit Violation value (for example: YES or NO).")
    ap.add_argument("--show-violations", type=int, default=0,
                    help="If >0, show only rows with Violation=YES (or --violation-value) and print up to this many rows.")
    ap.add_argument("--violation-value", default="YES", help="Value used by --show-violations.")
    ap.add_argument("--show-fp-status", default="",
                    help="If set, filter rows by an explicit FPStatus value (for example: ConfirmedFalsePositive).")
    ap.add_argument(
        "--remove-confirmed-fp",
        action="store_true",
        help=(
            "Remove rows classified as ConfirmedFalsePositive before display/export. "
            "If FPStatus is absent and the file matches the unordered detector schema, "
            "Match-First Filtering is applied in-memory."
        ),
    )

    ap.add_argument("--select", nargs="*", default=[], help="Columns to display.")
    ap.add_argument("-c-format", "--format", dest="format", choices=["table", "vertical"], default="table",
                    help="Terminal output format. '-c-format' is kept as a compatibility alias.")
    ap.add_argument("--display-width", type=int, default=200, help="Terminal display width.")
    ap.add_argument("--max-colwidth", type=int, default=60, help="Max column width in table output.")

    ap.add_argument("--export", default="", help="Export filtered rows to this CSV.")
    ap.add_argument("--export-max", type=int, default=10_000, help="Max rows to export.")

    # NEW: raw PC values from evidence
    ap.add_argument("--evidence", default="", help="Path to the evidence CSV (e.g., output/violations_evidence_string.csv).")
    ap.add_argument("--show-pc-values", action="store_true",
                    help="If set, adds PC_A and PC_B columns with raw PC values retrieved from evidence (original PC strings).")
    ap.add_argument("--pc-limit", type=int, default=50, help="Max unique PCs to collect per side from evidence.")
    ap.add_argument("--pc-join", default=" || ", help="Join string for multiple PCs on the same side.")

    # Aggregations
    ap.add_argument("--top-offenders", action="store_true",
                    help="Compute top (Project,File,Caller) by #Violation=='YES'.")
    ap.add_argument("--top-k", type=int, default=20, help="Top K offenders.")
    ap.add_argument("--top-fp-contexts", action="store_true",
                    help="Compute top (Project,File,Caller,PairKey/pair columns) by #FPStatus=='ConfirmedFalsePositive'.")
    ap.add_argument("--fp-top-k", type=int, default=20, help="Top K contexts for --top-fp-contexts.")

    ap.add_argument("--pattern-stats", action="store_true", help="Compute per-pattern stats.")
    ap.add_argument("--pattern-top-k", type=int, default=30, help="Top K patterns.")
    ap.add_argument("--pattern-sort", choices=["yes_count", "yes_rate", "total"], default="yes_count",
                    help="Sorting for --pattern-stats.")
    ap.add_argument("--show-summaries", action="store_true",
                    help="Print Violation/FPStatus summaries after showing rows.")

    args = ap.parse_args()

    if not os.path.exists(args.file):
        raise FileNotFoundError(f"File not found: {args.file}")

    if args.info:
        header = pd.read_csv(args.file, nrows=0).columns.tolist()
        nrows = fast_row_count(args.file)
        print("=== INFO ===")
        print("Header:", header)
        print("Data rows:", nrows)

    base_filters = parse_where(args.where) if args.where else []
    if getattr(args, "show_violation", ""):
        base_filters.append(("Violation", args.show_violation))
    if getattr(args, "show_fp_status", ""):
        base_filters.append(("FPStatus", args.show_fp_status))
    show_filters = list(base_filters)
    if args.show_violations and args.show_violations > 0:
        if not has_filter(show_filters, "Violation"):
            show_filters.append(("Violation", args.violation_value))

    counts_acc: Dict[str, Counter] = {col: Counter() for col in args.counts}
    violation_summary: Counter = Counter()
    fp_status_summary: Counter = Counter()
    systems_seen: Set[str] = set()
    offenders: Counter = Counter()
    fp_contexts: Counter = Counter()
    pattern_total: Counter = Counter()
    pattern_yes: Counter = Counter()
    pattern_no: Counter = Counter()

    shown = 0
    exported = 0
    if args.export and os.path.exists(args.export):
        os.remove(args.export)

    show_target = args.show_violations if args.show_violations and args.show_violations > 0 else args.show

    shown_rows: List[pd.DataFrame] = []

    for chunk in pd.read_csv(args.file, chunksize=args.chunksize):
        chunk = maybe_apply_false_positive_filter(chunk, args.remove_confirmed_fp)
        if chunk.empty:
            continue

        # Counts
        for col in args.counts:
            if col not in chunk.columns:
                raise ValueError(f"Column '{col}' not found for --counts.")
            vc = chunk[col].astype(str).value_counts(dropna=False)
            for k, v in vc.items():
                counts_acc[col][k] += int(v)

        # Top offenders
        if args.top_offenders:
            required = ["Project", "File", "Caller", "Violation"]
            for r in required:
                if r not in chunk.columns:
                    raise ValueError(f"--top-offenders requires columns {required}, missing '{r}'.")
            yes = chunk[chunk["Violation"].astype(str) == "YES"]
            if not yes.empty:
                grp = yes.groupby(["Project", "File", "Caller"]).size()
                for idx, cnt in grp.items():
                    offenders[idx] += int(cnt)

        if args.top_fp_contexts:
            required = ["Project", "File", "Caller", "FPStatus"]
            for r in required:
                if r not in chunk.columns:
                    raise ValueError(f"--top-fp-contexts requires columns {required}, missing '{r}'.")
            pair_cols = ("PairKey",) if "PairKey" in chunk.columns else resolve_pattern_columns(chunk.columns)
            fps = chunk[chunk["FPStatus"].astype(str) == "ConfirmedFalsePositive"]
            if not fps.empty:
                grp_cols = ["Project", "File", "Caller"] + list(pair_cols)
                grp = fps.groupby(grp_cols).size()
                for idx, cnt in grp.items():
                    fp_contexts[idx] += int(cnt)

        # Pattern stats
        if args.pattern_stats:
            pair_a, pair_b = resolve_pattern_columns(chunk.columns)
            required = [pair_a, pair_b, "Violation"]
            for r in required:
                if r not in chunk.columns:
                    raise ValueError(f"--pattern-stats requires columns {required}, missing '{r}'.")
            totals = chunk.groupby([pair_a, pair_b]).size()
            for key, cnt in totals.items():
                pattern_total[key] += int(cnt)

            yes = chunk[chunk["Violation"].astype(str) == "YES"]
            if not yes.empty:
                y = yes.groupby([pair_a, pair_b]).size()
                for key, cnt in y.items():
                    pattern_yes[key] += int(cnt)

            no = chunk[chunk["Violation"].astype(str) == "NO"]
            if not no.empty:
                n = no.groupby([pair_a, pair_b]).size()
                for key, cnt in n.items():
                    pattern_no[key] += int(cnt)

        filtered_show = apply_filters(chunk, show_filters) if show_filters else chunk
        filtered_export = apply_filters(chunk, base_filters) if base_filters else chunk


        # Violation summary (after --where/--show-violation)
        if "Project" in filtered_export.columns and not filtered_export.empty:
            systems_seen.update(filtered_export["Project"].astype(str).unique().tolist())
        if "Violation" in filtered_export.columns and not filtered_export.empty:
            violation_summary.update(filtered_export["Violation"].astype(str).tolist())
        if "FPStatus" in filtered_export.columns and not filtered_export.empty:
            fp_status_summary.update(filtered_export["FPStatus"].astype(str).tolist())
        # Export
        if args.export and exported < args.export_max and not filtered_export.empty:
            remaining = args.export_max - exported
            to_write = filtered_export if len(filtered_export) <= remaining else filtered_export.head(remaining)
            to_write.to_csv(args.export, mode="a", index=False, header=(exported == 0))
            exported += len(to_write)

        # Collect rows to show
        if show_target > 0 and shown < show_target and not filtered_show.empty:
            remaining = show_target - shown
            to_take = filtered_show if len(filtered_show) <= remaining else filtered_show.head(remaining)
            shown_rows.append(to_take)
            shown += len(to_take)

        if not args.counts and not args.top_offenders and not args.top_fp_contexts and not args.pattern_stats:
            done_show = (show_target <= 0) or (shown >= show_target)
            done_export = (not args.export) or (exported >= args.export_max)
            if done_show and done_export:
                break

    df_show = pd.concat(shown_rows, ignore_index=True) if shown_rows else pd.DataFrame()

    # Clean NaN (before augmentations)
    if not df_show.empty:
        df_show = clean_nan_strings(df_show, ["PcErrorKinds"])

    # Add raw PC values from evidence
    if args.show_pc_values:
        if df_show.empty:
            print("(No rows to display, so PC values cannot be shown.)")
        else:
            if not args.evidence:
                raise ValueError("--show-pc-values requires --evidence <path to evidence csv>.")
            required = {"Project", "File", "Caller", "Antecedent", "Consequent"}
            missing = required - set(df_show.columns)
            if missing:
                raise ValueError(
                    f"--show-pc-values requires these columns in --select: {sorted(required)}. "
                    f"Missing in current selection: {sorted(missing)}"
                )

            targets: Set[Tuple[str, str, str, str, str]] = set()
            for _, r in df_show.iterrows():
                targets.add((str(r["Project"]), str(r["File"]), str(r["Caller"]), str(r["Antecedent"]), str(r["Consequent"])))

            ev_sets = build_evidence_pc_sets(args.evidence, targets, pc_limit=args.pc_limit, chunksize=args.chunksize)

            pc_a_vals = []
            pc_b_vals = []
            for _, r in df_show.iterrows():
                key = (str(r["Project"]), str(r["File"]), str(r["Caller"]), str(r["Antecedent"]), str(r["Consequent"]))
                entry = ev_sets.get(key, {"PC_A": [], "PC_B": []})
                pc_a_vals.append(pc_value_from_set(entry["PC_A"], args.pc_join))
                pc_b_vals.append(pc_value_from_set(entry["PC_B"], args.pc_join))

            df_show = df_show.copy()
            df_show["PC_A"] = pc_a_vals
            df_show["PC_B"] = pc_b_vals

    # Apply select (after augmentations so you can select PC_A / PC_B)
    if not df_show.empty and args.select:
        missing = [c for c in args.select if c not in df_show.columns]
        if missing:
            raise ValueError(f"--select columns not found: {missing}")
        df_show = df_show[args.select]

    # Print shown rows
    if not df_show.empty and show_target > 0:
        print_header_summary(
            args.display_width,
            len(systems_seen),
            int(violation_summary.get("YES", 0)),
            int(violation_summary.get("NO", 0)),
        )
        if args.format == "vertical":
            print_vertical(df_show, args.display_width)
        else:
            print_table(df_show, args.display_width, args.max_colwidth)
    # Print violation summary (useful to validate detectors)
    if args.show_summaries and violation_summary:
        total = sum(violation_summary.values())
        print("\n=== Violation Summary (after filters) ===")
        for key in ["YES", "NO"]:
            if key in violation_summary:
                print(f"  {key}: {violation_summary[key]}")
        for key in sorted(k for k in violation_summary.keys() if k not in {"YES", "NO"}):
            print(f"  {key}: {violation_summary[key]}")
        print(f"  TOTAL: {total}")

    if args.show_summaries and fp_status_summary:
        total = sum(fp_status_summary.values())
        print("\n=== FPStatus Summary (after filters) ===")
        preferred_order = [
            "ConfirmedFalsePositive",
            "CandidateViolation",
            "NoAction",
        ]
        for key in preferred_order:
            if key in fp_status_summary:
                print(f"  {key}: {fp_status_summary[key]}")
        for key in sorted(k for k in fp_status_summary.keys() if k not in set(preferred_order)):
            print(f"  {key}: {fp_status_summary[key]}")
        print(f"  TOTAL: {total}")


    # Print counts
    for col in args.counts:
        print(f"\n=== VALUE COUNTS: {col} ===")
        for k, v in counts_acc[col].most_common():
            print(f"{k!r}: {v}")

    if args.top_offenders:
        print(f"\n=== TOP OFFENDERS (Violation=='YES') top {args.top_k} ===")
        for (proj, file_, caller), cnt in offenders.most_common(args.top_k):
            print(f"{cnt:6d}  {proj} | {file_} | {caller}")

    if args.top_fp_contexts:
        print(f"\n=== TOP FP CONTEXTS (FPStatus=='ConfirmedFalsePositive') top {args.fp_top_k} ===")
        for idx, cnt in fp_contexts.most_common(args.fp_top_k):
            print(f"{cnt:6d}  " + " | ".join(str(x) for x in idx))

    if args.pattern_stats:
        rows = []
        for (a, b), total in pattern_total.items():
            yes_cnt = pattern_yes.get((a, b), 0)
            no_cnt = pattern_no.get((a, b), 0)
            yes_rate = (yes_cnt / total) if total > 0 else 0.0
            rows.append((a, b, yes_cnt, no_cnt, total, yes_rate))

        if args.pattern_sort == "yes_rate":
            rows.sort(key=lambda t: (t[5], t[2], t[4]), reverse=True)
        elif args.pattern_sort == "total":
            rows.sort(key=lambda t: (t[4], t[2], t[5]), reverse=True)
        else:
            rows.sort(key=lambda t: (t[2], t[5], t[4]), reverse=True)

        k = args.pattern_top_k
        print(f"\n=== PATTERN STATS top {k} (sorted by {args.pattern_sort}) ===")
        pair_a, pair_b = resolve_pattern_columns(df_show.columns if not df_show.empty else pd.read_csv(args.file, nrows=0).columns)
        print(f"{pair_a} | {pair_b} | YES | NO | TOTAL | YES_RATE")
        for a, b, yes_cnt, no_cnt, total, yes_rate in rows[:k]:
            print(f"{a} | {b} | {yes_cnt} | {no_cnt} | {total} | {yes_rate:.4f}")

    if args.export:
        print(f"\nExported {exported} rows to: {args.export}")


if __name__ == "__main__":
    main()
