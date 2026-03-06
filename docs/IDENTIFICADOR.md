# API Usage Pattern Identifier

## Scope
This document explains how the API usage pattern identifier works at architecture and implementation level, including algorithms, data contracts, and operational practices.

## Problem statement
In configurable C systems, API calls may exist only under subsets of build configurations controlled by preprocessor directives (`#if`, `#ifdef`, etc.). The system detects inconsistencies in API usage pairs using `Presence Conditions (PC)`.

Example pairs:
- `fopen` and `fclose`
- `malloc` and `free`
- `open` and `close`

## Data model

## Input 1: calls with PC
CSV columns:
- `Project`
- `File`
- `Caller`
- `Callee`
- `PC`

Semantics:
- each row represents one call occurrence `Caller -> Callee` under condition `PC`
- `PC=TRUE` means unconditional call
- sentinels (`FILE_NOT_FOUND`, `CALLER_NOT_FOUND`, `CALL_NOT_FOUND`) are tracked as data-quality errors and excluded from logical checks

## Input 2: pattern catalog
CSV columns:
- `antecedents`
- `consequents`
- `support`
- `confidence`
- `lift`

Semantics:
- catalog is treated as an unordered relation
- if `(A,B)` exists, `(B,A)` is also analyzed

## Outputs
Main output artifacts:
- `violations_unordered_*.csv` for `unordered-string`
- `violations_unordered_*_dedup.csv` for deduplicated output
- `violations_summary*.csv` and `violations_evidence*.csv` for summary modes

## Architecture by module

## Orchestration and CLI
- File: `src/main.py`
- Responsibilities:
  - parse CLI arguments
  - resolve default paths
  - dispatch selected mode
  - trigger optional post-processing deduplication

## Pattern loading
- File: `src/csv_io.py`
- Responsibilities:
  - load catalog rows
  - symmetrically expand unordered pairs
  - deduplicate repeated pairs

## `unordered-string` baseline
- File: `src/unordered_detector.py`
- Responsibilities:
  - build per-context call/PC index
  - evaluate API pairs with string comparison
  - emit `YES/NO` rows

## Summary modes
- File: `src/detector.py`
- Modes:
  - `short-circuit`: A/B presence-absence logic
  - `summary-string`: PC set comparison
  - `sat`: satisfiability-based decision when both sides exist

## SAT engine
- File: `src/sat_engine.py`
- Responsibilities:
  - parse boolean expressions
  - simplify formulas
  - encode via Tseitin CNF
  - solve SAT with caching

## Deduplication
- Files:
  - `src/dedup_unordered.py`
  - `src/deduplicate_unordered_output.py`
- Responsibilities:
  - canonical key generation for mirrored-row removal
  - reduction statistics
  - standalone CLI post-processing

## Algorithm flow for `unordered-string`

## 1. Normalization and indexing
For each valid call row:
1. build group key `G = (Project, File, Caller)`
2. aggregate into `pc_map[G][Callee] -> set(normalized_PC)`

Note:
- normalization is textual (whitespace + outer parentheses), not semantic equivalence

## 2. Unordered catalog expansion
For each catalog pair `(A,B)`:
1. keep `(A,B)`
2. add `(B,A)` if missing

## 3. Candidate generation per group
For each group:
1. collect present callees
2. query pattern index by callee
3. avoid scanning the full catalog for every group

## 4. Decision rule
For each candidate pair `(A,B)`:
1. read `PCs(A)` and `PCs(B)`
2. if either side is absent, emit nothing in baseline mode
3. if both exist, iterate over Cartesian product `PCs(A) x PCs(B)`
4. classify:
   - `Violation=YES` if `PC_A != PC_B`
   - `Violation=NO` if `PC_A == PC_B`

## Complexity (high-level)
Given:
- `G` = number of groups
- `P_g` = candidate patterns per group
- `a_g` = |PCs(A)|
- `b_g` = |PCs(B)|

Dominant time cost per group:
- `O(sum_{p in P_g}(a_g * b_g))`

Dominant memory:
- size of `pc_map`

## Deduplication model and decision

## Problem
With unordered catalog expansion plus Cartesian products, mirrored rows appear, e.g.:
- `(Callee_A=fclose, Callee_B=fopen, PC_A=NATIVE_ZOS, PC_B=TRUE)`
- `(Callee_A=fclose, Callee_B=fopen, PC_A=TRUE, PC_B=NATIVE_ZOS)`

They encode the same logical fact in an unordered interpretation.

## Implemented solution
Deduplication uses canonical key:
1. fixed context: `(Project, File, Caller)`
2. lexicographically ordered API pair
3. lexicographically ordered PC pair
4. `Violation` label

If two rows map to the same canonical key, the first is kept and the next is dropped.

## Guarantees
- deterministic for fixed input order
- stable for pipeline use
- preserves original CSV schema

## How to run

## Default command
```bash
python3 src/main.py --mode unordered-string
```

## With automatic deduplication
```bash
python3 src/main.py --mode unordered-string --dedup-unordered-output
```

## Standalone deduplication
```bash
python3 src/deduplicate_unordered_output.py \
  --input output/violations_unordered_57_cs_projects_with_pc.csv \
  --output output/violations_unordered_57_cs_projects_with_pc_dedup.csv
```

## Validation commands

## Synthetic regression
```bash
python3 src/run_test_cases_regression.py
```

## CLI help smoke test
```bash
python3 src/main.py --help
python3 src/deduplicate_unordered_output.py --help
```

## Operational best practices
- pin dataset and catalog versions per experiment
- keep output suffixes explicit (`_dedup`, `_sat`, `_string`)
- run synthetic regression before changing decision rules
- keep `chunksize` fixed during comparative experiments

## Known limitations
- string baseline does not prove semantic equivalence for different textual PCs
- extraction quality of PCs strongly impacts precision
- results depend on the chosen textual normalization policy

## Recommended evolution strategy
1. keep string baseline as stable reference
2. improve textual canonicalization
3. run SAT-based comparisons in controlled experiments
4. keep deduplication as explicit, auditable post-processing
