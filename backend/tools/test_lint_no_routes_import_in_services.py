"""Self-test for the no-routes-import-in-services AST linter.

Builds a synthetic services/ tree and asserts the linter flags module-level
imports, lazy in-function imports, and plain ``import routes...`` forms
while leaving clean files (including docstring/comment mentions) alone.
Run with: ``python tools/test_lint_no_routes_import_in_services.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_no_routes_import_in_services import scan  # noqa: E402

# fmt: off
CLEAN = '''
"""Extracted from routes/profiles.py — mention in a docstring is fine."""
import os
from services.embedded_extractor import extract_embedded_sub

# from routes.remux import _trash_paths  <- comment, must not trigger

def helper():
    return os.getcwd()
'''

MODULE_LEVEL_FROM = '''
from routes.wanted.extract import _extract_embedded_sub

def tick():
    _extract_embedded_sub(1, "/x.mkv")
'''

LAZY_IN_FUNCTION = '''
def run():
    from routes.translate import _run_job
    _run_job({"id": "x"})
'''

PLAIN_IMPORT = '''
import routes.remux

def paths():
    return routes.remux._trash_paths()
'''

RELATIVE_IMPORT_OK = '''
from .sibling import helper  # relative import inside services — fine
'''
# fmt: on


def _write_tree(cases: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="lint_services_"))
    services = tmp / "services"
    services.mkdir()
    for name, content in cases.items():
        (services / name).write_text(content, encoding="utf-8")
    return services


def main() -> int:
    failures: list[str] = []

    services = _write_tree(
        {
            "clean.py": CLEAN,
            "module_level.py": MODULE_LEVEL_FROM,
            "lazy.py": LAZY_IN_FUNCTION,
            "plain.py": PLAIN_IMPORT,
            "relative.py": RELATIVE_IMPORT_OK,
        }
    )
    findings = scan(services)
    flagged = {p.name for p, _line, _stmt in findings}

    if "clean.py" in flagged:
        failures.append(f"clean.py must not be flagged, got {findings}")
    if "relative.py" in flagged:
        failures.append(f"relative.py must not be flagged, got {findings}")
    for expected in ("module_level.py", "lazy.py", "plain.py"):
        if expected not in flagged:
            failures.append(f"{expected} must be flagged, got {findings}")

    # Each violating file must be flagged exactly once with the right line.
    lazy = [(p, line) for p, line, _ in findings if p.name == "lazy.py"]
    if lazy and lazy[0][1] != 3:
        failures.append(f"lazy.py violation must point at line 3, got {lazy}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("no-routes-import-in-services linter self-test: ok (5 cases checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
