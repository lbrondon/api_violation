# api_violation
<<<<<<< HEAD
Detects API usage-pattern violations in configurable C code using presence conditions (PC) and generates summary/evidence reports.
=======

Symbolic (SAT-based) detector for API-usage pattern violations in configurable C systems,
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
