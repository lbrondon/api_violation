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
