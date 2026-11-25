"""AST linter — no raw exception text in API responses (Forgejo #77 N-4).

``str(exc)`` / ``repr(exc)`` / ``f"{exc}"`` of a caught exception carries file
system paths, SQL, library internals and, for HTTP client errors, URLs whose
query string holds an API key. Exception text belongs in the log; responses
use ``error_utils.internal_error_response`` or a fixed public message.

Inside an ``except ... as name`` handler under ``backend/routes`` this flags
exception text that reaches a response sink:

* a ``jsonify(...)`` argument,
* a dict literal value (response payloads, job/step results),
* a ``return`` value,
* a keyword argument named ``error`` / ``message`` / ``reason`` / ``detail``,
* an argument of ``.append`` / ``emit`` / ``emit_event``.

Deliberate user-facing validation errors (our own exception type, text written
for the user) are allowed by a ``# user-facing-error`` comment on a line of the
flagged expression or on the line directly above it.

Exit code 1 on any violation, 0 otherwise. Designed for CI.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROUTES_DIR = Path(__file__).resolve().parent.parent / "routes"
MARKER = "# user-facing-error"

_SKIP_DIR_PARTS = {"venv", ".venv", "site-packages", "__pycache__", "node_modules"}
_SINK_KEYWORDS = {"error", "message", "reason", "detail"}
_SINK_METHODS = {"append", "emit", "emit_event"}


def _leaks(expr: ast.AST, names: set[str]) -> list[ast.AST]:
    """Sub-nodes of ``expr`` that render an exception variable as text."""
    found: list[ast.AST] = []
    for node in ast.walk(expr):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"str", "repr"}
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in names
        ) or (
            isinstance(node, ast.FormattedValue)
            and isinstance(node.value, ast.Name)
            and node.value.id in names
        ):
            found.append(node)
    return found


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _sinks(body: list[ast.stmt]) -> list[ast.AST]:
    """Expressions in an except body that end up in a response or payload."""
    sinks: list[ast.AST] = []
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Return) and node.value is not None:
                sinks.append(node.value)
            elif isinstance(node, ast.Dict):
                sinks.extend(v for v in node.values if v is not None)
            elif isinstance(node, ast.Call):
                name = _call_name(node)
                if name == "jsonify" or name in _SINK_METHODS:
                    sinks.extend(node.args)
                for kw in node.keywords:
                    if kw.arg in _SINK_KEYWORDS:
                        sinks.append(kw.value)
    return sinks


def scan_source(source: str, filename: str = "<src>") -> list[tuple[int, str]]:
    """Return (lineno, text) violations for one module's source."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []
    lines = source.splitlines()
    violations: dict[int, str] = {}
    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler) or not handler.name:
            continue
        names = {handler.name}
        for sink in _sinks(handler.body):
            for leak in _leaks(sink, names):
                start = leak.lineno
                end = getattr(leak, "end_lineno", start) or start
                span = range(max(start - 1, 1), end + 1)
                if any(MARKER in lines[n - 1] for n in span if n <= len(lines)):
                    continue
                violations[start] = lines[start - 1].strip()
    return sorted(violations.items())


def scan(routes_dir: Path) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for py in sorted(routes_dir.rglob("*.py")):
        if set(py.parts) & _SKIP_DIR_PARTS:
            continue
        try:
            source = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, text in scan_source(source, str(py)):
            findings.append((py, lineno, text))
    return findings


def main(argv: list[str]) -> int:
    routes_dir = Path(argv[1]) if len(argv) > 1 else ROUTES_DIR
    if not routes_dir.is_dir():
        print(f"no-exception-text linter: directory not found: {routes_dir}")
        return 1
    findings = scan(routes_dir)
    if not findings:
        print(f"no-exception-text linter: clean ({routes_dir})")
        return 0
    print(f"no-exception-text linter: {len(findings)} violation(s):")
    for path, lineno, text in findings:
        try:
            rel = path.relative_to(routes_dir.parent)
        except ValueError:
            rel = path
        print(f"  {rel}:{lineno}: {text}")
    print()
    print("Exception text must not reach API responses (paths, SQL, URLs with keys).")
    print("Log the exception and return error_utils.internal_error_response(msg, exc)")
    print(f"or a fixed message. Deliberate user-facing validation text: add `{MARKER}`.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv))
