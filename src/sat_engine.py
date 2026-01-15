# src/sat_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

try:
    from pysat.formula import IDPool
    from pysat.solvers import Solver
except Exception as e:
    raise ImportError(
        "PySAT is required for Milestone 3.\n"
        "Install with:\n"
        "  python3 -m pip install --user \"python-sat[pblib,aiger]\"\n"
    ) from e


# -----------------------------
# AST node definitions
# -----------------------------

@dataclass(frozen=True)
class Node:
    pass

@dataclass(frozen=True)
class Const(Node):
    value: bool

@dataclass(frozen=True)
class Var(Node):
    name: str

@dataclass(frozen=True)
class Not(Node):
    x: Node

@dataclass(frozen=True)
class And(Node):
    a: Node
    b: Node

@dataclass(frozen=True)
class Or(Node):
    a: Node
    b: Node


# -----------------------------
# Tokenizer and parser
# -----------------------------

OPERATORS = {"&&", "||", "!", "(", ")"}

def tokenize(expr: str) -> List[str]:
    """
    Tokenize a PC string.
    Recognized tokens: '&&', '||', '!', '(', ')'
    Everything else is an ATOM token, including spaces, until an operator is hit.

    This allows atoms like:
      DEBUG >= 2
      defined(FOO)   (if it ever appears)
      SOME_MACRO
    """
    s = expr.strip()
    tokens: List[str] = []
    i = 0
    buf: List[str] = []

    def flush_buf():
        nonlocal buf
        atom = "".join(buf).strip()
        if atom:
            tokens.append(atom)
        buf = []

    while i < len(s):
        # Two-char operators first
        if s.startswith("&&", i) or s.startswith("||", i):
            flush_buf()
            tokens.append(s[i:i+2])
            i += 2
            continue

        ch = s[i]
        if ch in ["!", "(", ")"]:
            flush_buf()
            tokens.append(ch)
            i += 1
            continue

        # Otherwise accumulate into atom buffer
        buf.append(ch)
        i += 1

    flush_buf()
    return tokens


class Parser:
    def __init__(self, tokens: List[str]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Optional[str]:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def consume(self, expected: str) -> None:
        got = self.peek()
        if got != expected:
            raise ValueError(f"Expected token '{expected}', got '{got}'")
        self.pos += 1

    def parse(self) -> Node:
        node = self.parse_or()
        if self.peek() is not None:
            raise ValueError(f"Unexpected trailing token: {self.peek()}")
        return node

    # Grammar:
    # expr := or_expr
    # or_expr := and_expr ( '||' and_expr )*
    # and_expr := unary ( '&&' unary )*
    # unary := '!' unary | primary
    # primary := ATOM | '(' expr ')'

    def parse_or(self) -> Node:
        node = self.parse_and()
        while self.peek() == "||":
            self.consume("||")
            rhs = self.parse_and()
            node = Or(node, rhs)
        return node

    def parse_and(self) -> Node:
        node = self.parse_unary()
        while self.peek() == "&&":
            self.consume("&&")
            rhs = self.parse_unary()
            node = And(node, rhs)
        return node

    def parse_unary(self) -> Node:
        if self.peek() == "!":
            self.consume("!")
            return Not(self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> Node:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")

        if tok == "(":
            self.consume("(")
            node = self.parse_or()
            self.consume(")")
            return node

        # ATOM
        self.pos += 1
        atom = tok.strip()

        # Constants
        up = atom.upper()
        if up == "TRUE" or atom == "1":
            return Const(True)
        if up == "FALSE" or atom == "0":
            return Const(False)

        return Var(atom)


def simplify(node: Node) -> Node:
    """
    Lightweight simplifier (critical for performance):
    - constant folding
    - remove double negations
    - simplify And/Or with constants
    """
    if isinstance(node, Const) or isinstance(node, Var):
        return node

    if isinstance(node, Not):
        x = simplify(node.x)
        if isinstance(x, Const):
            return Const(not x.value)
        if isinstance(x, Not):
            return simplify(x.x)
        return Not(x)

    if isinstance(node, And):
        a = simplify(node.a)
        b = simplify(node.b)
        if isinstance(a, Const) and isinstance(b, Const):
            return Const(a.value and b.value)
        if isinstance(a, Const):
            return b if a.value else Const(False)
        if isinstance(b, Const):
            return a if b.value else Const(False)
        if a == b:
            return a
        return And(a, b)

    if isinstance(node, Or):
        a = simplify(node.a)
        b = simplify(node.b)
        if isinstance(a, Const) and isinstance(b, Const):
            return Const(a.value or b.value)
        if isinstance(a, Const):
            return Const(True) if a.value else b
        if isinstance(b, Const):
            return Const(True) if b.value else a
        if a == b:
            return a
        return Or(a, b)

    return node


# -----------------------------
# Tseitin CNF encoding
# -----------------------------

class TseitinEncoder:
    def __init__(self):
        self.vpool = IDPool()
        self.var_ids: Dict[str, int] = {}     # Var.name -> id
        self.node_ids: Dict[Node, int] = {}   # Node -> id (for subformulas)

    def lit_for_var(self, name: str) -> int:
        if name not in self.var_ids:
            self.var_ids[name] = self.vpool.id(f"v:{name}")
        return self.var_ids[name]

    def lit_for_node(self, node: Node) -> int:
        if node in self.node_ids:
            return self.node_ids[node]
        nid = self.vpool.id(f"n:{len(self.node_ids)}")
        self.node_ids[node] = nid
        return nid

    def encode(self, node: Node, clauses: List[List[int]]) -> int:
        """
        Returns a literal (positive var id) representing the formula.
        Appends CNF clauses enforcing equivalence.
        Assumes node has no top-level Const after simplification, or handles it.
        """
        node = simplify(node)

        if isinstance(node, Const):
            # We'll return a fresh node literal forced to True/False.
            v = self.lit_for_node(node)
            clauses.append([v] if node.value else [-v])
            return v

        if isinstance(node, Var):
            return self.lit_for_var(node.name)

        if isinstance(node, Not):
            a = self.encode(node.x, clauses)
            v = self.lit_for_node(node)
            # v <-> ¬a
            clauses.append([-v, -a])
            clauses.append([v, a])
            return v

        if isinstance(node, And):
            a = self.encode(node.a, clauses)
            b = self.encode(node.b, clauses)
            v = self.lit_for_node(node)
            # v <-> (a ∧ b)
            clauses.append([-v, a])
            clauses.append([-v, b])
            clauses.append([v, -a, -b])
            return v

        if isinstance(node, Or):
            a = self.encode(node.a, clauses)
            b = self.encode(node.b, clauses)
            v = self.lit_for_node(node)
            # v <-> (a ∨ b)
            clauses.append([v, -a])
            clauses.append([v, -b])
            clauses.append([-v, a, b])
            return v

        raise TypeError(f"Unsupported node type: {type(node)}")


# -----------------------------
# SAT engine with caching
# -----------------------------

class SatEngine:
    """
    SAT engine that parses PC expressions and checks satisfiability.
    Uses caching heavily to avoid repeated parsing/encoding.
    """

    def __init__(self, solver_name: str = "glucose3"):
        self.solver_name = solver_name

        # Cache: expression string -> simplified AST
        self.ast_cache: Dict[str, Node] = {}

        # Cache: expression string -> SAT result
        self.sat_cache: Dict[str, bool] = {}

    def parse_expr(self, expr: str) -> Node:
        expr = expr.strip()
        if expr in self.ast_cache:
            return self.ast_cache[expr]
        tokens = tokenize(expr)
        parser = Parser(tokens)
        ast = simplify(parser.parse())
        self.ast_cache[expr] = ast
        return ast

    def is_sat(self, expr: str) -> bool:
        expr = expr.strip()
        if expr in self.sat_cache:
            return self.sat_cache[expr]

        ast = self.parse_expr(expr)
        ast = simplify(ast)

        # Trivial constants
        if isinstance(ast, Const):
            self.sat_cache[expr] = ast.value
            return ast.value

        clauses: List[List[int]] = []
        enc = TseitinEncoder()
        top = enc.encode(ast, clauses)

        # Force top formula to be True
        clauses.append([top])

        with Solver(name=self.solver_name) as s:
            for cl in clauses:
                s.add_clause(cl)
            res = s.solve()

        self.sat_cache[expr] = bool(res)
        return bool(res)

    def sat_and_not(self, a_expr: str, b_expr: str) -> bool:
        """
        Checks SAT(a AND NOT b) with small constant short-circuits.
        """
        a_expr = a_expr.strip()
        b_expr = b_expr.strip()

        # Constant short-circuits
        if a_expr == "FALSE":
            return False
        if b_expr == "TRUE":
            return False
        if a_expr == "TRUE" and b_expr == "FALSE":
            return True

        # Build a combined expression
        combined = f"({a_expr}) && !({b_expr})"
        return self.is_sat(combined)


if __name__ == "__main__":
    # Tiny sanity checks (run: python3 src/sat_engine.py)
    se = SatEngine()
    tests = [
        ("TRUE", True),
        ("FALSE", False),
        ("A && !A", False),
        ("A && !B", True),
        ("(A || B) && !A", True),  # B=True, A=False
        ("(A || B) && !A && !B", False),
    ]
    for expr, expected in tests:
        got = se.is_sat(expr)
        print(expr, "=>", got, "(expected", expected, ")")
