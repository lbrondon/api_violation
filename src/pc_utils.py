from __future__ import annotations

SENTINELS = {"FILE_NOT_FOUND", "CALLER_NOT_FOUND", "CALL_NOT_FOUND"}

# Heuristics to flag "corrupted" PCs that are not real boolean guards.
INVALID_PC_MARKERS = [
    "\\n",        # literal backslash-n in the string
    "#define",
    "define ",
    "\";",        # common artifact in extracted string/code
]


def is_valid_pc(pc: str) -> bool:
    """
    Return False if the PC looks corrupted (contains code fragments / string literals).
    This is a heuristic-based guard to avoid poisoning the analysis.
    """
    if pc is None:
        return False
    s = str(pc)
    if "\n" in s or "\r" in s:
        return False
    s_lower = s.lower()
    for m in INVALID_PC_MARKERS:
        if m.lower() in s_lower:
            return False
    return True


def _strip_outer_parens(s: str) -> str:
    """
    Remove redundant outer parentheses: '((A && B))' -> 'A && B'
    Only strips when parentheses wrap the entire expression.
    """
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        ok = True
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(s) - 1:
                    ok = False
                    break
        if ok:
            s = s[1:-1].strip()
        else:
            break
    return s


def normalize_pc(pc: str) -> str:
    """
    Normalize a PC string for *string-based comparisons*.

    Goals:
    - stable formatting (whitespace normalization)
    - remove redundant outer parentheses
    - keep the internal content intact (we are not doing SAT here)

    NOTE: We intentionally do NOT try to enforce logical equivalence.
    """
    s = str(pc).strip()
    if not s:
        return s

    # Normalize whitespace
    s = " ".join(s.split())

    # Normalize outer parentheses
    s = _strip_outer_parens(s)

    return s


def or_aggregate(pcs: set[str]) -> str:
    """
    Aggregate a set of PCs using OR.

    Conventions:
    - empty set -> 'FALSE'
    - contains TRUE -> 'TRUE'
    - otherwise -> '(pc1) || (pc2) || ...'
    """
    if not pcs:
        return "FALSE"
    if "TRUE" in pcs:
        return "TRUE"
    items = sorted(pcs)
    return " || ".join(f"({p})" for p in items)
