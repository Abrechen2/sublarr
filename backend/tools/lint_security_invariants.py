"""AST linter — security invariants we assert ourselves (Forgejo #10).

Scanners find known patterns; this asserts our own rules and fails loudly the
first time someone breaks one:

- ``sql``: no SQL built from strings at run time. ``execute``/``text``/
  ``exec_driver_sql``/``executescript`` must not receive an f-string with
  placeholders, a ``+``/``%`` expression or a ``.format()`` call. Values go in
  as bound parameters. A statement that only interpolates fixed identifiers
  (table names from a constant or a validated allowlist) is marked with the
  comment ``# sql-identifiers-only`` on one of its lines, after review.
  Alembic migrations are skipped: they are one-off DDL over fixed names.
- ``shell``: no shell. ``shell=`` anything but ``False`` and ``os.system`` /
  ``os.popen`` are refused; subprocess takes an argument list.

Exit code 1 on any violation, 0 otherwise. Designed for pre-commit and CI.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

_SKIP_DIR_PARTS = {"venv", ".venv", "site-packages", "__pycache__", "node_modules", "tests"}
_SQL_SINKS = {"execute", "text", "exec_driver_sql", "executescript"}
_SQL_MARKER = "sql-identifiers-only"


def _is_migration(rel: Path) -> bool:
    return rel.parts[:2] == ("db", "migrations")


def _is_dynamic_string(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Mod):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    )


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def _statement_spans(tree: ast.AST) -> list[tuple[int, int]]:
    return [
        (n.lineno, getattr(n, "end_lineno", n.lineno))
        for n in ast.walk(tree)
        if isinstance(n, ast.stmt)
    ]


def _has_marker(lines: list[str], node: ast.AST, spans: list[tuple[int, int]]) -> bool:
    """The marker may sit anywhere in the innermost statement holding ``node``.

    The formatter moves a trailing comment to wherever it breaks the line, so
    the call's own span is too narrow.
    """
    inside = [(a, b) for a, b in spans if a <= node.lineno <= b]
    start, end = min(inside, key=lambda span: span[1] - span[0], default=(node.lineno, node.lineno))
    return any(_SQL_MARKER in lines[i - 1] for i in range(start, end + 1))


def _is_shell_call(node: ast.Call) -> bool:
    for kw in node.keywords:
        if kw.arg == "shell" and not (
            isinstance(kw.value, ast.Constant) and kw.value.value is False
        ):
            return True
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
        and func.attr in ("system", "popen")
    )


def scan_file(py: Path, rel: Path) -> list[tuple[int, str]]:
    """Return (lineno, rule) violations for one file."""
    try:
        source = py.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py))
    except (SyntaxError, UnicodeDecodeError):
        return []
    lines = source.splitlines()
    spans = _statement_spans(tree)
    check_sql = not _is_migration(rel)
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if (
            check_sql
            and _call_name(node) in _SQL_SINKS
            and node.args
            and _is_dynamic_string(node.args[0])
            and not _has_marker(lines, node, spans)
        ):
            violations.append((node.lineno, "sql"))
        if _is_shell_call(node):
            violations.append((node.lineno, "shell"))
    return violations


def scan(root: Path) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        if set(rel.parts) & _SKIP_DIR_PARTS or rel.parts[0] == "tools":
            continue
        for lineno, rule in scan_file(py, rel):
            findings.append((py, lineno, rule))
    return findings


_RULE_TEXT = {
    "sql": "SQL built from a string at run time — bind values as parameters "
    f"(mark reviewed identifier-only statements with '# {_SQL_MARKER}')",
    "shell": "shell execution — pass subprocess an argument list with shell=False",
}


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else BACKEND_DIR
    findings = scan(root)
    if not findings:
        print(f"security-invariants linter: clean ({root})")
        return 0
    print(f"security-invariants linter: {len(findings)} violation(s):")
    for path, lineno, rule in findings:
        print(f"  {path.relative_to(root)}:{lineno}: [{rule}] {_RULE_TEXT[rule]}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
