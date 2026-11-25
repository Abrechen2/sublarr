"""Self-test for the no-exception-text-in-responses linter.

Run with: ``python tools/test_lint_no_exception_text_in_responses.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_no_exception_text_in_responses import scan_source  # noqa: E402

# fmt: off
LEAK_JSONIFY = '''
def r():
    try:
        pass
    except Exception as e:
        return jsonify({"error": str(e)}), 500
'''

LEAK_FSTRING = '''
def r():
    try:
        pass
    except OSError as exc:
        return jsonify({"error": f"Failed: {exc}"}), 500
'''

LEAK_PAYLOAD = '''
def r(steps):
    try:
        pass
    except Exception as e:
        steps.append({"scan": {"error": str(e)}})
'''

LEAK_KEYWORD = '''
def r():
    try:
        pass
    except Exception as exc:
        _update_job(1, "failed", error=repr(exc))
'''

MARKED = '''
def r():
    try:
        pass
    except ValueError as e:
        return jsonify({"error": str(e)}), 400  # user-facing-error
'''

MARKED_ABOVE = '''
def r():
    try:
        pass
    except ValueError as e:
        # user-facing-error
        return jsonify({"error": str(e)}), 400
'''

CLEAN = '''
def r():
    try:
        pass
    except Exception as e:
        logger.warning("failed: %s", e)
        if "not found" in str(e):
            pass
        logger.error(f"boom {e}")
        return jsonify({"error": "Failed"}), 500
    x = {"error": str(other)}
'''
# fmt: on


def main() -> int:
    cases = [
        ("jsonify str", LEAK_JSONIFY, 1),
        ("f-string", LEAK_FSTRING, 1),
        ("payload append", LEAK_PAYLOAD, 1),
        ("keyword repr", LEAK_KEYWORD, 1),
        ("marker same line", MARKED, 0),
        ("marker line above", MARKED_ABOVE, 0),
        ("clean", CLEAN, 0),
    ]
    failed = 0
    for name, src, expected in cases:
        got = len(scan_source(src))
        status = "ok" if got == expected else "FAIL"
        if got != expected:
            failed += 1
        print(f"{status}: {name} (expected {expected}, got {got})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
