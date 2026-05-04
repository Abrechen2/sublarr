"""Self-test for the is_safe_path AST linter.

Builds a tiny synthetic project tree containing one good call and a few
known reversed-arg patterns, then asserts the scanner flags exactly the
reversed ones. Run with: `python tools/test_lint_is_safe_path.py`.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Make the linter importable without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_is_safe_path import scan  # noqa: E402

# fmt: off
GOOD = """
from security_utils import is_safe_path
def f(file_path, media_path):
    is_safe_path(file_path, media_path)
    is_safe_path(subtitle_path, getattr(settings, 'config_dir', '/config'))
    is_safe_path('/some/dir', media_path)
    is_safe_path(target, base_dir)
"""

REVERSED = """
from security_utils import is_safe_path
def bug1(file_path, media_path):
    is_safe_path(media_path, file_path)
def bug2(backup_path, settings):
    is_safe_path(settings.config_dir, backup_path)
def bug3(target, trash_root):
    is_safe_path(trash_root, target)
"""
# fmt: on


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ok.py").write_text(GOOD, encoding="utf-8")
        (root / "bad.py").write_text(REVERSED, encoding="utf-8")
        violations = scan(root)
        bad_lines = sorted(line for path, line, *_ in violations if path.name == "bad.py")
        good_lines = [line for path, line, *_ in violations if path.name == "ok.py"]
        if good_lines:
            print(f"FAIL: linter false-positives in ok.py at lines {good_lines}", file=sys.stderr)
            return 1
        # Three reversed calls expected: bug1, bug2, bug3.
        if len(bad_lines) != 3:
            print(
                f"FAIL: expected 3 violations in bad.py, got {len(bad_lines)} at lines {bad_lines}",
                file=sys.stderr,
            )
            return 1
    print("is_safe_path linter self-test: ok (3 reversed calls flagged, 0 false positives)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
