"""Every pause reason the sweep writes maps to a stable code the UI translates."""

import re
from pathlib import Path

from services.foreign_tracks.stats import PAUSE_CODES, pause_code

_SWEEP = Path(__file__).resolve().parent.parent / "services" / "foreign_tracks" / "sweep.py"


def test_every_pause_reason_has_a_code():
    source = _SWEEP.read_text(encoding="utf-8")
    # Every string literal assigned to a paused_reason starts with a known prefix.
    starts = re.findall(r'paused_reason(?:"\])?\s*=\s*\(?\s*f?"([^"{]+)', source)
    assert starts, "the scan found no pause reasons — the regex is stale"
    for text in starts:
        assert pause_code(text.strip()) is not None, f"no code for pause reason: {text!r}"


def test_codes():
    assert pause_code("disk floor reached (min_free_gb=500) — paused before the next file") == (
        "disk_floor"
    )
    assert pause_code("3 consecutive probe failures — pausing") == "probe_failures"
    assert pause_code(None) is None
    assert pause_code("something new") is None
    assert len({code for _, code in PAUSE_CODES}) == len(PAUSE_CODES)
