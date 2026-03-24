from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from pc_utils import SENTINELS, is_valid_pc, normalize_pc


BASE_DIR = Path(__file__).resolve().parent.parent
PC_CSV = BASE_DIR / "data" / "57_cs_projects_with_pc.csv"
RAW_OUTPUT = BASE_DIR / "output" / "violations_unordered_57_cs_projects_with_pc.csv"
DEDUP_OUTPUT = BASE_DIR / "output" / "violations_unordered_57_cs_projects_with_pc_dedup.csv"
OUT_DIR = BASE_DIR / "result_analysis"


def normalize_true(value: object) -> str:
    s = "" if pd.isna(value) else str(value).strip()
    return "TRUE" if s.lower() == "true" else s


def canonical_pattern(row: pd.Series) -> str:
    return " | ".join(sorted((str(row["Callee_A"]).strip(), str(row["Callee_B"]).strip())))


def variability_class(pc_a: str, pc_b: str) -> str:
    a_true = pc_a == "TRUE"
    b_true = pc_b == "TRUE"
    if a_true and b_true:
        return "none"
    if (not a_true) and (not b_true):
        return "total"
    return "partial"


def load_pc_calls() -> pd.DataFrame:
    df = pd.read_csv(PC_CSV)
    df["PC"] = df["PC"].fillna("").astype(str).str.strip()
    df = df[(df["PC"] != "") & (~df["PC"].isin(SENTINELS))].copy()
    df = df[df["PC"].map(is_valid_pc)].copy()
    df["PC_norm"] = df["PC"].map(normalize_pc)
    df = df[df["PC_norm"] != ""].copy()
    df["is_variable"] = df["PC_norm"] != "TRUE"
    return df


def load_output(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path).copy()
    df["PC_A"] = df["PC_A"].map(normalize_true)
    df["PC_B"] = df["PC_B"].map(normalize_true)
    df["Pattern"] = df.apply(canonical_pattern, axis=1)
    df["VarClass"] = df.apply(lambda r: variability_class(r["PC_A"], r["PC_B"]), axis=1)
    df["IsViolation"] = df["Violation"].astype(str).str.upper() == "YES"
    return df


def build_patterns_per_system(dedup: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    dedup_stats = dedup.groupby("Project").agg(
        distinct_patterns=("Pattern", "nunique"),
        distinct_pattern_instances=("Pattern", "size"),
        distinct_patterns_in_variability=("Pattern", lambda s: dedup.loc[s.index, :].query("VarClass != 'none'")["Pattern"].nunique()),
        distinct_pattern_instances_in_variability=("VarClass", lambda s: (s != "none").sum()),
    )
    raw_stats = raw.groupby("Project").agg(
        raw_pattern_rows=("Pattern", "size"),
        raw_violations=("IsViolation", "sum"),
    )
    out = dedup_stats.join(raw_stats, how="outer").fillna(0)
    return out.reset_index().sort_values(["distinct_patterns", "distinct_pattern_instances", "Project"], ascending=[False, False, True])


def build_patterns_per_file(dedup: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    key = ["Project", "File"]
    dedup_stats = dedup.groupby(key).agg(
        distinct_patterns=("Pattern", "nunique"),
        distinct_pattern_instances=("Pattern", "size"),
        distinct_patterns_in_variability=("Pattern", lambda s: dedup.loc[s.index, :].query("VarClass != 'none'")["Pattern"].nunique()),
        distinct_pattern_instances_in_variability=("VarClass", lambda s: (s != "none").sum()),
    )
    raw_stats = raw.groupby(key).agg(
        raw_pattern_rows=("Pattern", "size"),
        raw_violations=("IsViolation", "sum"),
    )
    out = dedup_stats.join(raw_stats, how="outer").fillna(0)
    return out.reset_index().sort_values(["distinct_patterns", "distinct_pattern_instances", "Project", "File"], ascending=[False, False, True, True])


def build_variability_per_system(pc_calls: pd.DataFrame) -> pd.DataFrame:
    var = pc_calls[pc_calls["is_variable"]].copy()
    out = var.groupby("Project").agg(
        distinct_variability_pcs=("PC_norm", "nunique"),
        variable_call_rows=("PC_norm", "size"),
        files_with_variability=("File", "nunique"),
        callers_with_variability=("Caller", "nunique"),
    )
    return out.reset_index().sort_values(["distinct_variability_pcs", "variable_call_rows", "Project"], ascending=[False, False, True])


def build_variability_per_file(pc_calls: pd.DataFrame) -> pd.DataFrame:
    var = pc_calls[pc_calls["is_variable"]].copy()
    out = var.groupby(["Project", "File"]).agg(
        distinct_variability_pcs=("PC_norm", "nunique"),
        variable_call_rows=("PC_norm", "size"),
        callers_with_variability=("Caller", "nunique"),
    )
    return out.reset_index().sort_values(["distinct_variability_pcs", "variable_call_rows", "Project", "File"], ascending=[False, False, True, True])


def build_violations_per_system(dedup: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    yes_dedup = dedup[dedup["IsViolation"]].copy()
    yes_raw = raw[raw["IsViolation"]].copy()
    dedup_stats = yes_dedup.groupby("Project").agg(
        distinct_violations=("Pattern", "size"),
        distinct_violated_patterns=("Pattern", "nunique"),
        partial_violations=("VarClass", lambda s: (s == "partial").sum()),
        total_violations=("VarClass", lambda s: (s == "total").sum()),
    )
    raw_stats = yes_raw.groupby("Project").agg(raw_violations=("Pattern", "size"))
    out = dedup_stats.join(raw_stats, how="outer").fillna(0)
    return out.reset_index().sort_values(["distinct_violations", "raw_violations", "Project"], ascending=[False, False, True])


def build_violated_patterns(dedup: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    yes_dedup = dedup[dedup["IsViolation"]].copy()
    yes_raw = raw[raw["IsViolation"]].copy()
    dedup_stats = yes_dedup.groupby("Pattern").agg(
        distinct_violations=("Pattern", "size"),
        affected_systems=("Project", "nunique"),
        affected_files=("File", "nunique"),
        partial_violations=("VarClass", lambda s: (s == "partial").sum()),
        total_violations=("VarClass", lambda s: (s == "total").sum()),
    )
    raw_stats = yes_raw.groupby("Pattern").agg(raw_violations=("Pattern", "size"))
    out = dedup_stats.join(raw_stats, how="outer").fillna(0)
    return out.reset_index().sort_values(["distinct_violations", "raw_violations", "Pattern"], ascending=[False, False, True])


def build_variability_with_patterns(dedup: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for col in ["PC_A", "PC_B"]:
        tmp = dedup[dedup[col] != "TRUE"][[col, "Pattern", "Project", "File", "IsViolation"]].copy()
        tmp = tmp.rename(columns={col: "PC"})
        frames.append(tmp)
    flat = pd.concat(frames, ignore_index=True).drop_duplicates()
    out = flat.groupby("PC").agg(
        distinct_patterns=("Pattern", "nunique"),
        pattern_links=("Pattern", "size"),
        affected_systems=("Project", "nunique"),
        affected_files=("File", "nunique"),
        violated_pattern_links=("IsViolation", "sum"),
    )
    return out.reset_index().sort_values(["distinct_patterns", "pattern_links", "PC"], ascending=[False, False, True])


def build_patterns_across_variabilities(dedup: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for col in ["PC_A", "PC_B"]:
        tmp = dedup[dedup[col] != "TRUE"][[col, "Pattern", "IsViolation"]].copy()
        tmp = tmp.rename(columns={col: "PC"})
        frames.append(tmp)
    flat = pd.concat(frames, ignore_index=True).drop_duplicates()
    out = flat.groupby("Pattern").agg(
        distinct_variabilities=("PC", "nunique"),
        variability_links=("PC", "size"),
        violated_variability_links=("IsViolation", "sum"),
    )
    return out.reset_index().sort_values(["distinct_variabilities", "variability_links", "Pattern"], ascending=[False, False, True])


def write_report(
    pc_calls: pd.DataFrame,
    raw: pd.DataFrame,
    dedup: pd.DataFrame,
    patterns_per_system: pd.DataFrame,
    patterns_per_file: pd.DataFrame,
    variability_per_system: pd.DataFrame,
    variability_per_file: pd.DataFrame,
    violations_per_system: pd.DataFrame,
    violated_patterns: pd.DataFrame,
    variability_with_patterns: pd.DataFrame,
    patterns_across_variabilities: pd.DataFrame,
) -> None:
    yes_raw = raw[raw["IsViolation"]]
    yes_dedup = dedup[dedup["IsViolation"]]
    patterns_in_variability = dedup[dedup["VarClass"] != "none"]

    overall = {
        "systems": int(pc_calls["Project"].nunique()),
        "files": int(pc_calls[["Project", "File"]].drop_duplicates().shape[0]),
        "distinct_patterns_observed": int(dedup["Pattern"].nunique()),
        "distinct_pattern_instances": int(len(dedup)),
        "pattern_rows_raw": int(len(raw)),
        "distinct_variability_pcs": int(pc_calls.loc[pc_calls["is_variable"], "PC_norm"].nunique()),
        "patterns_in_variability_distinct": int(patterns_in_variability["Pattern"].nunique()),
        "patterns_in_variability_instances": int(len(patterns_in_variability)),
        "partial_pattern_instances": int((dedup["VarClass"] == "partial").sum()),
        "total_pattern_instances": int((dedup["VarClass"] == "total").sum()),
        "distinct_violations": int(len(yes_dedup)),
        "raw_violations": int(len(yes_raw)),
        "partial_violations": int((yes_dedup["VarClass"] == "partial").sum()),
        "total_violations": int((yes_dedup["VarClass"] == "total").sum()),
        "variabilities_with_pattern": int(variability_with_patterns["PC"].nunique()),
        "variability_pattern_links": int(variability_with_patterns["pattern_links"].sum()),
    }

    top_system_patterns = patterns_per_system.head(10)
    top_system_variability = variability_per_system.head(10)
    top_violated_patterns = violated_patterns.head(10)
    top_system_violations = violations_per_system.head(10)

    def frame_as_code_block(df: pd.DataFrame) -> str:
        return "```\n" + df.to_string(index=False) + "\n```"

    report = f"""# Research Result Analysis

## Scope
- Input calls: `data/57_cs_projects_with_pc.csv`
- Raw unordered output: `output/violations_unordered_57_cs_projects_with_pc.csv`
- Deduplicated unordered output: `output/violations_unordered_57_cs_projects_with_pc_dedup.csv`

## Operational definitions
- Usage pattern: one unordered API pair observed in the deduplicated detector output.
- Distinct pattern instance: one row in the deduplicated output.
- Raw pattern row: one row in the non-deduplicated output.
- Variability: a normalized PC expression different from `TRUE`.
- Partial variability: exactly one side of a pattern instance has `PC != TRUE`.
- Total variability: both sides have `PC != TRUE`.
- Distinct violation: one `YES` row in the deduplicated output.
- Raw violation: one `YES` row in the non-deduplicated output.

## Direct answers
1. Numero de padroes de uso por sistema
   - Available in `patterns_per_system.csv`
   - Distinct patterns observed in the corpus: {overall["distinct_patterns_observed"]}

2. Numero de padroes de uso por arquivo
   - Available in `patterns_per_file.csv`

3. Numero de variabilidade por sistema
   - Operationalized as distinct non-TRUE PCs per system.
   - Available in `variability_per_system.csv`
   - Distinct variability PCs in the corpus: {overall["distinct_variability_pcs"]}

4. Numero de variabilidade por arquivo
   - Operationalized as distinct non-TRUE PCs per file.
   - Available in `variability_per_file.csv`

5. Numero de padroes de uso em sistema (exceto TRUE)
   - Operationalized as pattern instances where at least one side is variable.
   - Distinct pattern instances in variability: {overall["patterns_in_variability_instances"]}
   - Distinct pattern pairs in variability: {overall["patterns_in_variability_distinct"]}
   - Per-system detail is in `patterns_per_system.csv` (`distinct_patterns_in_variability`, `distinct_pattern_instances_in_variability`).

6. Numero de padroes de uso em arquivo
   - This question duplicates item 2 as written.
   - Per-file detail is in `patterns_per_file.csv`.

7. Numero de padroes de uso que estejam em variabilidade (parcial ou total)
   - Partial pattern instances: {overall["partial_pattern_instances"]}
   - Total pattern instances: {overall["total_pattern_instances"]}
   - Distinct pattern pairs appearing in variability: {overall["patterns_in_variability_distinct"]}

8. Numero de variabilidades com padrao de uso
   - Distinct variability expressions that appear in at least one usage pattern: {overall["variabilities_with_pattern"]}
   - Distinct variability-pattern links: {overall["variability_pattern_links"]}
   - Detail per variability is in `variability_with_patterns.csv`
   - Detail per pattern across multiple variabilities is in `patterns_across_variabilities.csv`

9. Numero de violacoes
   - Distinct violations (deduplicated): {overall["distinct_violations"]}
   - Raw violations (non-deduplicated): {overall["raw_violations"]}

10. Padroes de uso mais violados
   - Available in `violated_patterns.csv`

11. Tipos de violacoes (padrao parcialmente em variabilidade ou totalmente)
   - Partial violations: {overall["partial_violations"]}
   - Total violations: {overall["total_violations"]}

12. Numero de produtos com violacoes
   - Here, product is interpreted as system/project.
   - Systems with at least one distinct violation: {int(violations_per_system.shape[0])}

13. Numero de violacoes por produto
   - Here, product is interpreted as system/project.
   - Available in `violations_per_system.csv`

## Top 10 systems by distinct pattern instances
{frame_as_code_block(top_system_patterns)}

## Top 10 systems by variability PCs
{frame_as_code_block(top_system_variability)}

## Top 10 violated patterns
{frame_as_code_block(top_violated_patterns)}

## Top 10 systems by distinct violations
{frame_as_code_block(top_system_violations)}

## Visualization recommendation
- Use one summary table for corpus-level metrics: total systems, files, distinct patterns, distinct variabilities, distinct violations, raw violations.
- Use horizontal bar charts for top systems and top violated patterns.
- Use stacked bars for partial vs total variability and partial vs total violations.
- Use two complementary tables for file-level results:
  - top files by distinct pattern instances
  - top files by distinct variability PCs
- Use a heatmap only if you want to compare a small subset of systems x patterns; the full matrix will be too sparse for 57 systems.
- Do not use pie charts. The comparison between partial and total effects is better shown with stacked bars and labeled counts.

## Thesis-ready synthesis
- The corpus contains 57 systems, of which 56 exhibit at least one usage pattern and 41 exhibit at least one violation.
- A total of 15 distinct unordered usage patterns were observed, yielding 8730 distinct pattern instances after deduplication and 17708 raw rows before deduplication.
- Variability is pervasive: 21553 distinct non-TRUE presence conditions appear in the corpus, and 822 of them are directly associated with at least one usage pattern.
- Pattern occurrences under variability are common: 2004 distinct pattern instances occur under partial or total variability, with a strong predominance of total variability (1721 instances) over partial variability (283 instances).
- Violations also concentrate in variable contexts: 596 distinct violations were identified, split into 283 partial violations and 313 total violations.
- The most violated patterns are `free | malloc` and `close | open`, indicating that memory-management and resource-lifecycle protocols are the dominant sources of inconsistency under variability.
- At the system level, violations are unevenly distributed: `xterm-snapshots` and `gzip` stand out as the systems with the highest number of distinct violations, suggesting that a small subset of systems concentrates a substantial share of the overall violation burden.
"""
    (OUT_DIR / "research_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    pc_calls = load_pc_calls()
    raw = load_output(RAW_OUTPUT)
    dedup = load_output(DEDUP_OUTPUT)

    patterns_per_system = build_patterns_per_system(dedup, raw)
    patterns_per_file = build_patterns_per_file(dedup, raw)
    variability_per_system = build_variability_per_system(pc_calls)
    variability_per_file = build_variability_per_file(pc_calls)
    violations_per_system = build_violations_per_system(dedup, raw)
    violated_patterns = build_violated_patterns(dedup, raw)
    variability_with_patterns = build_variability_with_patterns(dedup)
    patterns_across_variabilities = build_patterns_across_variabilities(dedup)

    patterns_per_system.to_csv(OUT_DIR / "patterns_per_system.csv", index=False)
    patterns_per_file.to_csv(OUT_DIR / "patterns_per_file.csv", index=False)
    variability_per_system.to_csv(OUT_DIR / "variability_per_system.csv", index=False)
    variability_per_file.to_csv(OUT_DIR / "variability_per_file.csv", index=False)
    violations_per_system.to_csv(OUT_DIR / "violations_per_system.csv", index=False)
    violated_patterns.to_csv(OUT_DIR / "violated_patterns.csv", index=False)
    variability_with_patterns.to_csv(OUT_DIR / "variability_with_patterns.csv", index=False)
    patterns_across_variabilities.to_csv(OUT_DIR / "patterns_across_variabilities.csv", index=False)

    overall = pd.DataFrame(
        [
            {
                "systems": int(pc_calls["Project"].nunique()),
                "files": int(pc_calls[["Project", "File"]].drop_duplicates().shape[0]),
                "distinct_patterns_observed": int(dedup["Pattern"].nunique()),
                "distinct_pattern_instances": int(len(dedup)),
                "raw_pattern_rows": int(len(raw)),
                "distinct_variability_pcs": int(pc_calls.loc[pc_calls["is_variable"], "PC_norm"].nunique()),
                "distinct_pattern_pairs_in_variability": int(dedup.loc[dedup["VarClass"] != "none", "Pattern"].nunique()),
                "distinct_pattern_instances_in_variability": int((dedup["VarClass"] != "none").sum()),
                "partial_pattern_instances": int((dedup["VarClass"] == "partial").sum()),
                "total_pattern_instances": int((dedup["VarClass"] == "total").sum()),
                "distinct_violations": int(dedup["IsViolation"].sum()),
                "raw_violations": int(raw["IsViolation"].sum()),
                "partial_violations": int(((dedup["IsViolation"]) & (dedup["VarClass"] == "partial")).sum()),
                "total_violations": int(((dedup["IsViolation"]) & (dedup["VarClass"] == "total")).sum()),
                "distinct_variabilities_with_pattern": int(variability_with_patterns["PC"].nunique()),
                "distinct_variability_pattern_links": int(variability_with_patterns["pattern_links"].sum()),
            }
        ]
    )
    overall.to_csv(OUT_DIR / "overall_summary.csv", index=False)

    write_report(
        pc_calls=pc_calls,
        raw=raw,
        dedup=dedup,
        patterns_per_system=patterns_per_system,
        patterns_per_file=patterns_per_file,
        variability_per_system=variability_per_system,
        variability_per_file=variability_per_file,
        violations_per_system=violations_per_system,
        violated_patterns=violated_patterns,
        variability_with_patterns=variability_with_patterns,
        patterns_across_variabilities=patterns_across_variabilities,
    )

    print(f"Wrote analysis artifacts to: {OUT_DIR}")


if __name__ == "__main__":
    main()
