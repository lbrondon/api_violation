# api_violation

String-based detector for API usage pattern violations in configurable C systems, using `Presence Conditions (PC)`.

## Goal
Detect potential violations in API usage pairs (for example `fopen`/`fclose`) while considering compile-time variability from preprocessor conditions.

## Full technical documentation
For architecture, internal flow, algorithmic decisions, and data model:

- [docs/IDENTIFICADOR.md](docs/IDENTIFICADOR.md)

## Requirements

## Python
- `python3` (recommended 3.10+)

## Dependencies
Option A (APT):

```bash
sudo apt update
sudo apt install -y python3-pandas python3-tqdm
```

Option B (pip user):

```bash
python3 -m pip install --user pandas tqdm
```

Optional for exploratory analysis:

```bash
python3 -m pip install --user jupyterlab
```

## Input structure
Large data files are not versioned. Place them under `data/`.

## Call-with-PC file
- Typical path: `data/57_cs_projects_with_pc.csv`
- Required columns: `Project, File, Caller, Callee, PC`
- `PC` may contain:
  - textual boolean expression
  - `TRUE`
  - sentinels: `FILE_NOT_FOUND`, `CALLER_NOT_FOUND`, `CALL_NOT_FOUND`

## Pattern catalog
- Typical path: `data/patterns_unordered.csv`
- Required columns: `antecedents, consequents, support, confidence, lift`
- The system treats patterns as unordered:
  - if `(A,B)` exists, `(B,A)` is also analyzed

## Quick run
Using defaults:

```bash
python3 src/main.py
```

## Available modes

## `unordered-string` (current baseline)
Compares `PC_A` and `PC_B` as strings.

```bash
python3 src/main.py --mode unordered-string
```

## `summary-string`
Generates summary/evidence per group and pattern using PC set comparison.

```bash
python3 src/main.py --mode summary-string --print-index-stats
```

## `short-circuit`
Classifies cases based on A/B presence or absence (without SAT).

```bash
python3 src/main.py --mode short-circuit --print-index-stats
```

## `sat`
Uses SAT to distinguish `A && !B` and `B && !A` when both sides exist.

```bash
python3 src/main.py --mode sat --print-index-stats
```

## Key arguments
- `--pc-csv`: path to call CSV
- `--patterns`: path to pattern CSV
- `--output-dir`: output directory
- `--output-file`: specific output for `unordered-string`
- `--chunksize`: chunk size for streaming reads
- `--dedup-unordered-output`: generate deduplicated CSV after `unordered-string`
- `--dedup-output-file`: custom path for deduplicated output

## Full example (`unordered-string` + deduplication)
```bash
python3 src/main.py \
  --mode unordered-string \
  --pc-csv data/57_cs_projects_with_pc.csv \
  --patterns data/patterns_unordered.csv \
  --output-file output/violations_unordered_57_cs_projects_with_pc.csv \
  --dedup-unordered-output \
  --dedup-output-file output/violations_unordered_57_cs_projects_with_pc_dedup.csv
```

## Generated outputs
Depending on mode:

- `output/violations_unordered_<dataset>.csv`
- `output/violations_unordered_<dataset>_dedup.csv`
- `output/violations_summary.csv`
- `output/violations_evidence.csv`
- `output/violations_summary_string.csv`
- `output/violations_evidence_string.csv`
- `output/violations_summary_sat.csv`
- `output/violations_evidence_sat.csv`

## Deduplicate an existing output file
```bash
python3 src/deduplicate_unordered_output.py \
  --input output/violations_unordered_57_cs_projects_with_pc.csv \
  --output output/violations_unordered_57_cs_projects_with_pc_dedup.csv
```

## Identify false positives after deduplication
This repository now includes a layered post-processing step for false positives.

Rationale:
- keep the unordered detector unchanged
- keep PC comparison by string
- identify false positives created by Cartesian products in the same
  `(Project, File, Caller, unordered API pair)`

Implemented rules:
- `match_first_exact_match`
  - compute the exact textual intersection between the PCs of both sides
  - if a `YES` row compares two PCs already present in that exact-match set, mark it as
    `ConfirmedFalsePositive`
- `complementary_branch_coverage`
  - detect branch partitions such as `win32` and `!(win32)`
  - if both branches together cover the PC on the opposite side, mark the corresponding
    `YES` rows as `ConfirmedFalsePositive`

Run:

```bash
python3 src/identify_false_positives.py \
  --input output/violations_unordered_57_cs_projects_with_pc_dedup.csv \
  --output output/violations_unordered_57_cs_projects_with_pc_fp_analysis.csv
```

Main outputs:
- `*_fp_analysis.csv`
  - one row per detector result, enriched with canonical context, rule decisions and evidence
- `*_filtered_all.csv`
  - all detector rows except `ConfirmedFalsePositive`
- `*_violations_all.csv`
  - only rows with `Violation=YES` before removing false positives
- `*_violations_filtered.csv`
  - only rows with `Violation=YES` after removing false positives
- `*_context_summary.csv`
  - one row per `(Project, File, Caller, unordered API pair)`
- `*_coverage_evidence.csv`
  - one row per complementary-coverage witness

Important columns in `*_fp_analysis.csv`:
- `RowId`
- `ContextKey`
- `PairKey`
- `CanonicalCallee_Left`
- `CanonicalCallee_Right`
- `CanonicalPC_Left`
- `CanonicalPC_Right`
- `MatchedPCsCount`
- `MatchedPCs`
- `OnlyLeftCount`
- `OnlyLeftPCs`
- `OnlyRightCount`
- `OnlyRightPCs`
- `FPStatus`
- `FPReason`
- `FPRule`
- `DecisionStage`
- `CoverageWitnessId`
- `CoverageBasePC`
- `CoverageBranchPC1`
- `CoverageBranchPC2`
- `CoverageCoveredPC`

Important:
- this step does **not** change the detector baseline
- it is a post-processing analysis step
- the notebook-oriented CSVs are the primary artifacts for exploratory analysis

## Notebook workflow
The recommended analysis workflow is now:
1. generate raw detector output
2. deduplicate
3. run `src/identify_false_positives.py`
4. explore the generated CSVs in Jupyter Notebook

A starter notebook is available at:
- `notebooks/violation_exploration.ipynb`

## Synthetic dataset and regression

## Generate synthetic CSV from `test_cases.c`
```bash
python3 src/generate_test_pc_csv.py
```

## Run end-to-end regression
```bash
python3 src/run_test_cases_regression.py
```

Regression validates:
1. synthetic PC generation
2. detector execution
3. expected `YES`/`NO` counts
4. expected deduplication output
