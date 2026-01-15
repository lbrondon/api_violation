# api_violation

String-based detector for API-usage pattern violations in configurable C systems,
using presence conditions (PC) extracted from preprocessor directives.

## Inputs (default locations)
- data/cs_projects__with_pc.csv
  Columns: Project, File, Caller, Callee, PC
  PC may be a boolean expression or sentinel values:
  - TRUE
  - FILE_NOT_FOUND, CALLER_NOT_FOUND, CALL_NOT_FOUND

- data/patterns_unordered.csv
  Columns: antecedents, consequents, support, confidence, lift

## Outputs
- output/violations_summary.csv
- output/violations_evidence.csv

## Run (Milestone 1: indexing + validation)
python3 src/main.py

## Install dependencies (no venv)
Option 1 (APT):
sudo apt update
sudo apt install -y python3-pandas python3-tqdm

Option 2 (pip --user):
python3 -m pip install --user pandas tqdm

## Run
python3 src/main.py

## Data files (not committed)
This repository does **not** commit large CSV inputs/outputs. Make sure you place the required files locally under `data/`.

### Required inputs
Put these files in the `data/` folder:

- `data/cs_projects__with_pc.csv`
  - Columns: `Project, File, Caller, Callee, PC`
  - `PC` may be a boolean expression, `TRUE`, or sentinel values (`FILE_NOT_FOUND`, `CALLER_NOT_FOUND`, `CALL_NOT_FOUND`).

- `data/patterns_unordered.csv`
  - Columns: `antecedents, consequents, support, confidence, lift`

### Outputs
Running the pipeline generates CSV files under `output/`, for example:

- `output/violations_summary.csv`
- `output/violations_evidence.csv`
- `output/violations_summary_string.csv`
- `output/violations_evidence_string.csv`
