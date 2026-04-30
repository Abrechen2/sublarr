"""Regression tests for routes/tools/line_fixes.py.

The four cue-level routes (overlap-fix, timing-normalize, merge-lines,
split-lines) used to let a pysubs2 load/save failure bubble up as a 500
from Flask's default error path with no logging or structured JSON. This
file pins the wrapped behaviour: every internal failure now returns
{'error': '<route> failed: ...'} with HTTP 500.
"""

import os
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Resolve once -- avoids 8.3 short-name vs long-name mismatch on Windows
_TEMP_DIR = os.path.realpath(tempfile.gettempdir())


def _make_srt(name: str) -> str:
    """Write a minimal valid SRT under the media_path temp dir."""
    abs_path = os.path.join(_TEMP_DIR, name)
    content = "1\n00:00:01,000 --> 00:00:03,000\nHello\n\n2\n00:00:04,000 --> 00:00:06,000\nWorld\n"
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    return abs_path


def _cleanup(path: str) -> None:
    for p in (path, path.replace(".srt", ".bak.srt")):
        try:
            if os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


@pytest.mark.parametrize(
    ("endpoint", "label"),
    [
        ("/api/v1/tools/overlap-fix", "overlap-fix"),
        ("/api/v1/tools/timing-normalize", "timing-normalize"),
        ("/api/v1/tools/merge-lines", "merge-lines"),
        ("/api/v1/tools/split-lines", "split-lines"),
    ],
)
def test_line_fix_route_returns_500_with_error_json_on_pysubs2_failure(client, endpoint, label):
    """If pysubs2 raises while the route is processing the file, the response
    must be a structured 500 instead of an unhandled traceback."""
    srt = _make_srt(f"test_line_fix_err_{label.replace('-', '_')}.srt")
    try:
        with patch("pysubs2.load", side_effect=RuntimeError("simulated parse failure")):
            rv = client.post(endpoint, json={"file_path": srt})
        assert rv.status_code == 500
        body = rv.get_json()
        assert "error" in body
        # The wrapped message should mention the route name so the user knows
        # which tool blew up, not just "RuntimeError".
        assert label in body["error"]
    finally:
        _cleanup(srt)


def test_overlap_fix_happy_path_still_returns_200(client):
    """Sanity check that the try/except wrapper didn't break the success path."""
    srt = _make_srt("test_line_fix_overlap_ok.srt")
    try:
        rv = client.post("/api/v1/tools/overlap-fix", json={"file_path": srt})
        assert rv.status_code == 200
        body = rv.get_json()
        assert "fixed" in body
        assert "backup_path" in body
    finally:
        _cleanup(srt)
