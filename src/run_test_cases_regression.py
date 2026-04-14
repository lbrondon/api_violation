from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

from dedup_unordered import UnorderedViolationDeduplicator
from generate_test_pc_csv import TestPcCsvGenerator
from identify_false_positives import MatchFirstFalsePositiveAnalyzer
from unordered_detector import UnorderedViolationDetector, EvaluationRow


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_INPUT_C = os.path.join(BASE_DIR, "data", "test_cases.c")
DEFAULT_PC_CSV = os.path.join(BASE_DIR, "data", "cs_projects__with_pc_test.csv")
DEFAULT_PATTERNS = os.path.join(BASE_DIR, "data", "patterns_unordered_test.csv")
DEFAULT_OUT = os.path.join(BASE_DIR, "output", "violations_unordered_test_generated.csv")


@dataclass(frozen=True)
class DetectorRowKey:
    caller: str
    callee_a: str
    callee_b: str
    pc_a: str
    pc_b: str
    violation: str


@dataclass(frozen=True)
class CsvRowKey:
    caller: str
    callee: str
    pc: str


class RegressionAssertions:
    EXPECTED_GENERATED_ROW_COUNT = 48
    EXPECTED_DETECTOR_ROW_COUNT = 56
    EXPECTED_VIOLATION_COUNTS = {"YES": 38, "NO": 18}
    EXPECTED_DEDUP_ROW_COUNT = 28

    REQUIRED_CSV_ROWS: Set[CsvRowKey] = {
        CsvRowKey("TC6_fopen_ifndef_fclose_ifdef", "fopen", "!(FEATURE_A)"),
        CsvRowKey("TC7_fopen_elif_fclose_only_A", "fopen", "(!(FEATURE_A)) && (FEATURE_B)"),
        CsvRowKey("TC12_if_expr_partial_overlap", "fopen", "FEATURE_A && (FEATURE_B || FEATURE_C)"),
        CsvRowKey("TC20_malloc_elif_free_only_A", "malloc", "(!(FEATURE_A)) && (!(FEATURE_B)) && (FEATURE_C)"),
    }

    REQUIRED_DETECTOR_ROWS: Set[DetectorRowKey] = {
        DetectorRowKey("TC2_fopen_fclose_same_pc", "fopen", "fclose", "_WIN32", "_WIN32", "NO"),
        DetectorRowKey("TC2_fopen_fclose_same_pc", "fclose", "fopen", "_WIN32", "_WIN32", "NO"),
        DetectorRowKey("TC6_fopen_ifndef_fclose_ifdef", "fopen", "fclose", "!(FEATURE_A)", "FEATURE_A", "YES"),
        DetectorRowKey("TC6_fopen_ifndef_fclose_ifdef", "fclose", "fopen", "FEATURE_A", "!(FEATURE_A)", "YES"),
        DetectorRowKey(
            "TC7_fopen_elif_fclose_only_A",
            "fopen",
            "fclose",
            "(!(FEATURE_A)) && (FEATURE_B)",
            "FEATURE_A",
            "YES",
        ),
        DetectorRowKey(
            "TC7_fopen_elif_fclose_only_A",
            "fclose",
            "fopen",
            "FEATURE_A",
            "(!(FEATURE_A)) && (FEATURE_B)",
            "YES",
        ),
        DetectorRowKey(
            "TC20_malloc_elif_free_only_A",
            "malloc",
            "free",
            "(!(FEATURE_A)) && (!(FEATURE_B)) && (FEATURE_C)",
            "FEATURE_A",
            "YES",
        ),
        DetectorRowKey(
            "TC20_malloc_elif_free_only_A",
            "free",
            "malloc",
            "FEATURE_A",
            "(!(FEATURE_A)) && (!(FEATURE_B)) && (FEATURE_C)",
            "YES",
        ),
        DetectorRowKey("TC15_malloc_free_same_A", "malloc", "free", "FEATURE_A", "FEATURE_A", "NO"),
        DetectorRowKey("TC15_malloc_free_same_A", "free", "malloc", "FEATURE_A", "FEATURE_A", "NO"),
    }


class TestCasesRegressionRunner:
    def __init__(self, test_c_path: str, pc_csv_out: str, patterns_csv: str, detector_out: str) -> None:
        self.test_c_path = test_c_path
        self.pc_csv_out = pc_csv_out
        self.patterns_csv = patterns_csv
        self.detector_out = detector_out

    def run(self) -> None:
        generated_rows = self._generate_pc_csv()
        self._assert_generated_csv(generated_rows)

        detector_rows = self._run_detector()
        self._assert_detector_output(detector_rows)
        self._assert_dedup_output()
        self._assert_false_positive_filters()

        print("[regression] OK: generator + unordered-string detector outputs match expected results.")

    def _generate_pc_csv(self):
        gen = TestPcCsvGenerator(project="proj_test", file_value="test_cases.c")
        rows = gen.generate_rows_from_file(self.test_c_path)
        gen.write_csv(rows, self.pc_csv_out)
        print(f"[regression] Generated PC CSV rows: {len(rows)} -> {self.pc_csv_out}")
        return rows

    def _run_detector(self) -> List[EvaluationRow]:
        patterns = UnorderedViolationDetector.load_patterns(self.patterns_csv)
        detector = UnorderedViolationDetector(patterns)
        pc_map = detector.build_pc_index(self.pc_csv_out)
        rows = detector.evaluate(pc_map)
        detector.write_csv(self.detector_out, rows)
        print(f"[regression] Detector rows: {len(rows)} -> {self.detector_out}")
        return rows

    def _assert_generated_csv(self, rows) -> None:
        if len(rows) != RegressionAssertions.EXPECTED_GENERATED_ROW_COUNT:
            raise AssertionError(
                f"Generated PC CSV row count mismatch: got {len(rows)}, "
                f"expected {RegressionAssertions.EXPECTED_GENERATED_ROW_COUNT}"
            )

        got: Set[CsvRowKey] = {
            CsvRowKey(r.caller, r.callee, r.pc)
            for r in rows
        }
        missing = RegressionAssertions.REQUIRED_CSV_ROWS - got
        if missing:
            raise AssertionError(f"Missing expected generated CSV rows: {sorted(missing, key=lambda x: (x.caller, x.callee, x.pc))}")

    def _assert_detector_output(self, rows: List[EvaluationRow]) -> None:
        if len(rows) != RegressionAssertions.EXPECTED_DETECTOR_ROW_COUNT:
            raise AssertionError(
                f"Detector output row count mismatch: got {len(rows)}, "
                f"expected {RegressionAssertions.EXPECTED_DETECTOR_ROW_COUNT}"
            )

        counts: Dict[str, int] = {}
        for r in rows:
            counts[r.violation] = counts.get(r.violation, 0) + 1
        if counts != RegressionAssertions.EXPECTED_VIOLATION_COUNTS:
            raise AssertionError(
                f"Violation counts mismatch: got {counts}, "
                f"expected {RegressionAssertions.EXPECTED_VIOLATION_COUNTS}"
            )

        got_rows: Set[DetectorRowKey] = {
            DetectorRowKey(r.caller, r.callee_a, r.callee_b, r.pc_a, r.pc_b, r.violation)
            for r in rows
        }
        missing_rows = RegressionAssertions.REQUIRED_DETECTOR_ROWS - got_rows
        if missing_rows:
            raise AssertionError(
                f"Missing expected detector rows: "
                f"{sorted(missing_rows, key=lambda x: (x.caller, x.pc_a, x.pc_b))}"
            )

    def _assert_dedup_output(self) -> None:
        dedup_out = os.path.splitext(self.detector_out)[0] + "_dedup.csv"
        dedup = UnorderedViolationDeduplicator()
        stats = dedup.deduplicate_file(self.detector_out, dedup_out)
        if stats.output_rows != RegressionAssertions.EXPECTED_DEDUP_ROW_COUNT:
            raise AssertionError(
                f"Dedup output row count mismatch: got {stats.output_rows}, "
                f"expected {RegressionAssertions.EXPECTED_DEDUP_ROW_COUNT}"
            )

    def _assert_false_positive_filters(self) -> None:
        analyzer = MatchFirstFalsePositiveAnalyzer()
        rows = [
            {
                "Project": "ASF_MapReady",
                "File": "ASF_MapReady/src/stp/stp.c",
                "Caller": "on_execute_button_clicked",
                "Callee_A": "free",
                "Callee_B": "malloc",
                "PC_A": "!(win32)",
                "PC_B": "TRUE",
                "Violation": "YES",
            },
            {
                "Project": "ASF_MapReady",
                "File": "ASF_MapReady/src/stp/stp.c",
                "Caller": "on_execute_button_clicked",
                "Callee_A": "free",
                "Callee_B": "malloc",
                "PC_A": "win32",
                "PC_B": "TRUE",
                "Violation": "YES",
            },
            {
                "Project": "proj_test",
                "File": "test_cases.c",
                "Caller": "TC_control_candidate",
                "Callee_A": "free",
                "Callee_B": "malloc",
                "PC_A": "FEATURE_B",
                "PC_B": "FEATURE_A",
                "Violation": "YES",
            },
            {
                "Project": "proj_test",
                "File": "test_cases.c",
                "Caller": "TC_control_candidate",
                "Callee_A": "free",
                "Callee_B": "malloc",
                "PC_A": "FEATURE_A",
                "PC_B": "FEATURE_A",
                "Violation": "NO",
            },
        ]

        analyzed_rows, stats, context_rows, coverage_rows = analyzer.analyze_rows(rows)
        fp_rows = [row for row in analyzed_rows if row["Project"] == "ASF_MapReady"]
        if len(fp_rows) != 2:
            raise AssertionError(f"Expected 2 ASF_MapReady rows, got {len(fp_rows)}")

        for row in fp_rows:
            if row["FPStatus"] != "ConfirmedFalsePositive":
                raise AssertionError(f"Expected complementary coverage FP, got {row['FPStatus']}")
            if row["FPReason"] != "complementary_branch_coverage":
                raise AssertionError(f"Unexpected FPReason: {row['FPReason']}")
            if row["CoverageBasePC"] != "TRUE":
                raise AssertionError(f"Expected base PC TRUE, got {row['CoverageBasePC']}")

        candidate_rows = [
            row for row in analyzed_rows
            if row["Caller"] == "TC_control_candidate" and row["Violation"] == "YES"
        ]
        if len(candidate_rows) != 1 or candidate_rows[0]["FPStatus"] != "CandidateViolation":
            raise AssertionError("Control violation should remain a candidate violation.")

        if stats.confirmed_false_positives != 2:
            raise AssertionError(
                f"Expected 2 confirmed false positives, got {stats.confirmed_false_positives}"
            )
        if stats.coverage_witnesses != 1:
            raise AssertionError(f"Expected 1 coverage witness, got {stats.coverage_witnesses}")
        if not coverage_rows or coverage_rows[0]["BasePC"] != "TRUE":
            raise AssertionError("Coverage evidence CSV rows were not generated as expected.")


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Regression test for test_cases generator + unordered string detector."
    )
    ap.add_argument("--test-c", default=DEFAULT_INPUT_C, help="Path to test_cases.c")
    ap.add_argument("--pc-csv-out", default=DEFAULT_PC_CSV, help="Generated PC CSV path")
    ap.add_argument("--patterns", default=DEFAULT_PATTERNS, help="patterns_unordered_test.csv")
    ap.add_argument("--detector-out", default=DEFAULT_OUT, help="Detector output CSV")
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    runner = TestCasesRegressionRunner(
        test_c_path=args.test_c,
        pc_csv_out=args.pc_csv_out,
        patterns_csv=args.patterns,
        detector_out=args.detector_out,
    )
    runner.run()


if __name__ == "__main__":
    main()
