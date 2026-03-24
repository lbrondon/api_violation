from __future__ import annotations

import argparse
import csv
import os
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from pc_utils import normalize_pc


CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
FUNC_DEF_RE = re.compile(
    r"^\s*(?:[A-Za-z_]\w*|\*)[\w\s\*]*\b([A-Za-z_]\w*)\s*\([^;]*\)\s*\{\s*$"
)
DIRECTIVE_RE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)$")
IDENT_RE = re.compile(r"[A-Za-z_]\w*")
DEFINED_PAREN_RE = re.compile(r"\bdefined\s*\(\s*([A-Za-z_]\w*)\s*\)")
DEFINED_BARE_RE = re.compile(r"\bdefined\s+([A-Za-z_]\w*)")
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
}


@dataclass(frozen=True)
class PcCallRow:
    project: str
    file: str
    caller: str
    callee: str
    pc: str


@dataclass
class ConditionalFrame:
    prior_branch_exprs: List[str] = field(default_factory=list)
    active_guard: str = "TRUE"
    seen_else: bool = False

    @staticmethod
    def for_first_branch(expr: str) -> "ConditionalFrame":
        return ConditionalFrame(prior_branch_exprs=[expr], active_guard=expr, seen_else=False)

    def switch_to_elif(self, expr: str) -> None:
        if self.seen_else:
            raise ValueError("Found #elif after #else in the same conditional block.")
        negated_priors = [ExprOps.negate(e) for e in self.prior_branch_exprs]
        self.active_guard = ExprOps.join_and(*negated_priors, expr)
        self.prior_branch_exprs.append(expr)

    def switch_to_else(self) -> None:
        if self.seen_else:
            raise ValueError("Duplicate #else in the same conditional block.")
        self.active_guard = ExprOps.join_and_negated(self.prior_branch_exprs)
        self.seen_else = True


class ExprOps:
    @staticmethod
    def normalize(expr: str) -> str:
        s = expr.strip()
        if not s:
            return ""
        return normalize_pc(s)

    @staticmethod
    def wrap(expr: str) -> str:
        expr = ExprOps.normalize(expr)
        if expr in {"", "TRUE"}:
            return expr
        if expr == "FALSE":
            return expr
        return f"({expr})"

    @staticmethod
    def negate(expr: str) -> str:
        expr = ExprOps.normalize(expr)
        if expr == "TRUE":
            return "FALSE"
        if expr == "FALSE":
            return "TRUE"
        return ExprOps.normalize(f"!({expr})")

    @staticmethod
    def join_and(*exprs: str) -> str:
        normalized = [ExprOps.normalize(e) for e in exprs if ExprOps.normalize(e)]
        if not normalized:
            return "TRUE"
        out: List[str] = []
        for e in normalized:
            if e == "FALSE":
                return "FALSE"
            if e == "TRUE":
                continue
            out.append(e)
        if not out:
            return "TRUE"
        if len(out) == 1:
            return out[0]
        return ExprOps.normalize(" && ".join(ExprOps.wrap(e) for e in out))

    @staticmethod
    def join_or(exprs: Iterable[str]) -> str:
        normalized = [ExprOps.normalize(e) for e in exprs if ExprOps.normalize(e)]
        if not normalized:
            return "FALSE"
        out: List[str] = []
        for e in normalized:
            if e == "TRUE":
                return "TRUE"
            if e == "FALSE":
                continue
            out.append(e)
        if not out:
            return "FALSE"
        if len(out) == 1:
            return out[0]
        return ExprOps.normalize(" || ".join(ExprOps.wrap(e) for e in out))

    @staticmethod
    def join_and_negated(exprs: Iterable[str]) -> str:
        return ExprOps.join_and(*(ExprOps.negate(e) for e in exprs))


class PreprocessorExpressionNormalizer:
    def normalize_if_expr(self, expr: str) -> str:
        s = self._remove_comments(expr)
        s = DEFINED_PAREN_RE.sub(r"\1", s)
        s = DEFINED_BARE_RE.sub(r"\1", s)
        s = " ".join(s.split())
        return ExprOps.normalize(s)

    def normalize_ifdef(self, symbol: str) -> str:
        sym = self._normalize_identifier(symbol)
        return sym

    def normalize_ifndef(self, symbol: str) -> str:
        sym = self._normalize_identifier(symbol)
        return ExprOps.negate(sym)

    def _normalize_identifier(self, symbol: str) -> str:
        s = self._remove_comments(symbol).strip()
        m = IDENT_RE.search(s)
        if not m:
            raise ValueError(f"Invalid preprocessor symbol: {symbol!r}")
        return m.group(0)

    @staticmethod
    def _remove_comments(s: str) -> str:
        return re.sub(r"/\*.*?\*/", "", s)


class PresenceConditionStack:
    def __init__(self) -> None:
        self._frames: List[ConditionalFrame] = []

    def push_if(self, expr: str) -> None:
        self._frames.append(ConditionalFrame.for_first_branch(expr))

    def elif_(self, expr: str) -> None:
        if not self._frames:
            raise ValueError("Found #elif without an open conditional block.")
        self._frames[-1].switch_to_elif(expr)

    def else_(self) -> None:
        if not self._frames:
            raise ValueError("Found #else without an open conditional block.")
        self._frames[-1].switch_to_else()

    def endif(self) -> None:
        if not self._frames:
            raise ValueError("Found #endif without an open conditional block.")
        self._frames.pop()

    def current_pc(self) -> str:
        if not self._frames:
            return "TRUE"
        return ExprOps.join_and(*(f.active_guard for f in self._frames))

    def ensure_balanced(self) -> None:
        if self._frames:
            raise ValueError("Unbalanced preprocessor directives: missing #endif.")


class CommentStripper:
    """Stateful stripper for C block comments across lines."""

    def __init__(self) -> None:
        self._in_block = False

    def strip(self, line: str) -> str:
        out: List[str] = []
        i = 0
        while i < len(line):
            if self._in_block:
                end = line.find("*/", i)
                if end == -1:
                    return "".join(out)
                self._in_block = False
                i = end + 2
                continue

            if line.startswith("/*", i):
                self._in_block = True
                i += 2
                continue

            if line.startswith("//", i):
                break

            out.append(line[i])
            i += 1

        return "".join(out)


class CCallExtractor:
    def extract_callees(self, code_line: str) -> List[str]:
        cleaned = STRING_RE.sub('""', code_line)
        out: List[str] = []
        for m in CALL_RE.finditer(cleaned):
            name = m.group(1)
            if name in KEYWORDS:
                continue
            out.append(name)
        return out


@dataclass
class FunctionContext:
    name: str
    brace_depth: int = 1


class TestPcCsvGenerator:
    def __init__(self, project: str = "proj_test", file_value: Optional[str] = None) -> None:
        self.project = project
        self.file_value = file_value
        self.expr_norm = PreprocessorExpressionNormalizer()
        self.pc_stack = PresenceConditionStack()
        self.comment_stripper = CommentStripper()
        self.call_extractor = CCallExtractor()

    def generate_rows_from_file(self, c_path: str) -> List[PcCallRow]:
        file_value = self.file_value or os.path.basename(c_path)
        rows: List[PcCallRow] = []
        current_func: Optional[FunctionContext] = None

        with open(c_path, "r", encoding="utf-8") as f:
            for lineno, raw_line in enumerate(f, start=1):
                line_wo_comments = self.comment_stripper.strip(raw_line.rstrip("\n"))
                stripped = line_wo_comments.strip()

                if self._handle_directive(stripped):
                    continue

                if not stripped:
                    continue

                if current_func is None:
                    func_name = self._match_function_definition(stripped)
                    if func_name:
                        current_func = FunctionContext(name=func_name, brace_depth=1)
                    continue

                for callee in self.call_extractor.extract_callees(stripped):
                    rows.append(
                        PcCallRow(
                            project=self.project,
                            file=file_value,
                            caller=current_func.name,
                            callee=callee,
                            pc=self.pc_stack.current_pc(),
                        )
                    )

                current_func.brace_depth += stripped.count("{")
                current_func.brace_depth -= stripped.count("}")
                if current_func.brace_depth <= 0:
                    current_func = None

        self.pc_stack.ensure_balanced()
        return rows

    def write_csv(self, rows: List[PcCallRow], out_path: str) -> int:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Project", "File", "Caller", "Callee", "PC"])
            w.writeheader()
            for r in rows:
                w.writerow(
                    {
                        "Project": r.project,
                        "File": r.file,
                        "Caller": r.caller,
                        "Callee": r.callee,
                        "PC": r.pc,
                    }
                )
        return len(rows)

    def _handle_directive(self, stripped_line: str) -> bool:
        if not stripped_line.startswith("#"):
            return False
        m = DIRECTIVE_RE.match(stripped_line)
        if not m:
            return True

        kind = m.group(1)
        rest = m.group(2).strip()
        if kind == "if":
            expr = self.expr_norm.normalize_if_expr(rest)
            self.pc_stack.push_if(expr)
        elif kind == "ifdef":
            self.pc_stack.push_if(self.expr_norm.normalize_ifdef(rest))
        elif kind == "ifndef":
            self.pc_stack.push_if(self.expr_norm.normalize_ifndef(rest))
        elif kind == "elif":
            expr = self.expr_norm.normalize_if_expr(rest)
            self.pc_stack.elif_(expr)
        elif kind == "else":
            self.pc_stack.else_()
        elif kind == "endif":
            self.pc_stack.endif()
        return True

    @staticmethod
    def _match_function_definition(stripped_line: str) -> Optional[str]:
        m = FUNC_DEF_RE.match(stripped_line)
        if not m:
            return None
        return m.group(1)


def build_arg_parser() -> argparse.ArgumentParser:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ap = argparse.ArgumentParser(
        description="Generate data/cs_projects__with_pc_test.csv automatically from data/test_cases.c."
    )
    ap.add_argument(
        "--input",
        default=os.path.join(base_dir, "data", "test_cases.c"),
        help="Path to test_cases.c",
    )
    ap.add_argument(
        "--output",
        default=os.path.join(base_dir, "data", "cs_projects__with_pc_test.csv"),
        help="Output CSV path",
    )
    ap.add_argument(
        "--project",
        default="proj_test",
        help="Value for Project column (default: proj_test)",
    )
    ap.add_argument(
        "--file-value",
        default="",
        help="Value for File column (default: basename of --input)",
    )
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    gen = TestPcCsvGenerator(project=args.project, file_value=(args.file_value or None))
    rows = gen.generate_rows_from_file(args.input)
    n = gen.write_csv(rows, args.output)
    print(f"Generated {n} rows: {args.output}")


if __name__ == "__main__":
    main()
