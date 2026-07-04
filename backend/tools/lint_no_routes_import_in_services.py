"""AST linter — forbid routes-layer imports inside the services layer.

Sublarr's layering contract: the import direction is routes → services,
never services → routes. A service importing from ``routes.*`` couples
business logic to HTTP wiring, invites circular imports (the historical
reason several services carried lazy ``from routes...`` imports inside
function bodies), and makes services untestable without the Flask app.

This linter walks every Python file under ``backend/services/`` and flags
ANY ``import routes...`` / ``from routes... import ...`` statement — at
module level or nested inside a function/method body (lazy imports count).
Strings and comments are ignored because the check is AST-based.

Exit code 1 on any violation, 0 otherwise. Designed for pre-commit and CI.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SERVICES_DIR = Path(__file__).resolve().parent.parent / "services"

_SKIP_DIR_PARTS = {"venv", ".venv", "site-packages", "__pycache__", "node_modules"}


def _is_routes_module(module_name: str | None) -> bool:
    """True when ``module_name`` is the routes package or a submodule of it."""
    if not module_name:
        return False
    return module_name == "routes" or module_name.startswith("routes.")


def scan_file(py: Path) -> list[tuple[int, str]]:
    """Return (lineno, statement) violations for one file."""
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    except (SyntaxError, UnicodeDecodeError):
        return []

    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_routes_module(alias.name):
                    violations.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            # Relative imports (level > 0) cannot reach the top-level routes
            # package from services/, so only absolute imports are checked.
            if node.level == 0 and _is_routes_module(node.module):
                names = ", ".join(alias.name for alias in node.names)
                violations.append((node.lineno, f"from {node.module} import {names}"))
    return violations


def scan(services_dir: Path) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for py in sorted(services_dir.rglob("*.py")):
        if set(py.parts) & _SKIP_DIR_PARTS:
            continue
        for lineno, stmt in scan_file(py):
            findings.append((py, lineno, stmt))
    return findings


def main(argv: list[str]) -> int:
    services_dir = Path(argv[1]) if len(argv) > 1 else SERVICES_DIR
    if not services_dir.is_dir():
        print(f"no-routes-import-in-services linter: directory not found: {services_dir}")
        return 1
    findings = scan(services_dir)
    if not findings:
        print(f"no-routes-import-in-services linter: clean ({services_dir})")
        return 0
    print(f"no-routes-import-in-services linter: {len(findings)} violation(s):")
    root = services_dir.parent
    for path, lineno, stmt in findings:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        print(f"  {rel}:{lineno}: {stmt}")
    print()
    print("Layering contract: routes -> services, never services -> routes.")
    print("Move the needed helper into a services/ (or other routes-independent)")
    print("module and import it from there; leave a delegating compat shim in the")
    print("routes module if tests patch the old path.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv))
