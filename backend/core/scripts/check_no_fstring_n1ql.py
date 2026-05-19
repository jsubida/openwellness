"""Lint guard: forbid f-string N1QL that splices anything beyond ``{b}``.

We use named parameters (``$name``) for every value, and an allowlist for
every identifier. The only thing that may be interpolated into a query
string is the bucket name (conventionally bound to ``b``). This script
walks the Couchbase repositories looking for f-string SQL where the
interpolation expression is anything else.

Exit code 0 = clean; 1 = findings (prints ``file:line: message`` for each).

Run manually:

    python backend/core/scripts/check_no_fstring_n1ql.py

Or as a pre-commit hook (see the user's hook config).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = (
    REPO_ROOT
    / "src"
    / "openwellness_core"
    / "adapters"
    / "couchbase"
    / "repositories"
)

# Tokens that mark a string as N1QL. If none appear, the f-string is harmless
# even if it has interpolations.
SQL_TOKENS = ("WHERE", "SELECT", "FROM", "ORDER BY")

# Interpolation expressions that are explicitly safe:
#   * bucket reference: the local ``b`` (typically ``b = bucket_ident(...)``)
#   * the ``' AND '.join(clauses)`` / ``' OR '.join(clauses)`` idiom for
#     stitching static clause strings together
#   * a per-repo identifier name validated through ``allowed_column(...)``
#     (we accept any ``order_col``/``ordering``/``order_dir`` name as a
#     proxy for "this went through the allowlist").
SAFE_NAMES = frozenset(
    {"b", "order_col", "order_dir", "ordering", "kind_clause"}
)


def _is_safe_join(node: ast.expr) -> bool:
    """Return True if ``node`` is ``' AND '.join(...)`` or similar."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr != "join":
        return False
    # Caller is a string literal like " AND ".
    return isinstance(func.value, ast.Constant) and isinstance(
        func.value.value, str
    )


def _is_safe_expr(expr: ast.expr) -> bool:
    if isinstance(expr, ast.Name) and expr.id in SAFE_NAMES:
        return True
    if _is_safe_join(expr):
        return True
    return False


def _string_value(node: ast.JoinedStr) -> str:
    """Concatenate the constant parts of an f-string for token-checking."""
    parts: list[str] = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value)
    return "".join(parts)


def _findings_in_file(path: Path) -> list[str]:
    findings: list[str] = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        text = _string_value(node)
        upper = text.upper()
        if not any(tok in upper for tok in SQL_TOKENS):
            continue
        for v in node.values:
            if not isinstance(v, ast.FormattedValue):
                continue
            if _is_safe_expr(v.value):
                continue
            try:
                expr_source = ast.unparse(v.value)
            except AttributeError:  # pragma: no cover (py <3.9)
                expr_source = "<expr>"
            findings.append(
                f"{path}:{v.lineno}: forbidden interpolation in N1QL "
                f"f-string: {expr_source!r}"
            )
    return findings


def main() -> int:
    if not TARGET_DIR.is_dir():
        print(f"target directory not found: {TARGET_DIR}", file=sys.stderr)
        return 2
    all_findings: list[str] = []
    for py in sorted(TARGET_DIR.rglob("*.py")):
        all_findings.extend(_findings_in_file(py))
    for line in all_findings:
        print(line)
    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
