"""Live extraction check: every sidecar the extractor writes must hold the
stream its name promises.

Prod 2026-08-30: fourteen ``.de.srt`` files next to Blu-ray remuxes held the
container's ARABIC track (verified byte-for-byte against ``ffmpeg -map 0:s:3``),
while the real German track sat untouched at ``.ger.srt``. This test builds a
real MKV with ffmpeg — the same tool the extractor drives — laid out like that
remux: skipped streams first (SDH, stood in for the PGS tracks ffmpeg cannot
author), then a run of foreign text tracks, then German. It then runs the
unmocked pipeline and reads every file back.

Skipped when ffmpeg is not installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

# (language tag, title, dialogue) in container order. The three SDH tracks are
# skipped by the extractor when ``embedded_allow_sdh`` is off — they occupy
# subtitle-stream slots exactly like the PGS tracks on the remux did.
_TRACKS = [
    ("eng", "English (SDH)", "english sdh one"),
    ("eng", "English (SDH)", "english sdh two"),
    ("eng", "English (SDH)", "english sdh three"),
    ("ara", "Arabic", "ARABIC-TRACK"),
    ("chi", "Chinese (Simplified)", "CHINESE-SIMPLIFIED"),
    ("chi", "Chinese (Traditional)", "CHINESE-TRADITIONAL"),
    ("fre", "French", "FRENCH-TRACK"),
    ("ger", "German", "GERMAN-TRACK"),
    ("ind", "Indonesian", "INDONESIAN-TRACK"),
    ("jpn", "Japanese", "JAPANESE-TRACK"),
]


def _srt(text: str) -> str:
    return f"1\n00:00:01,000 --> 00:00:02,000\n{text}\n\n"


def _build_mkv(tmp_path):
    srt_paths = []
    for i, (_lang, _title, text) in enumerate(_TRACKS):
        p = tmp_path / f"in{i}.srt"
        p.write_text(_srt(text), encoding="utf-8")
        srt_paths.append(p)
    out = tmp_path / "[Show] - [Group] (2023)" / "Ep - S02E01 Remux.mkv"
    out.parent.mkdir()
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=3"]
    for p in srt_paths:
        cmd += ["-i", str(p)]
    cmd += ["-map", "0:v"]
    for i in range(len(srt_paths)):
        cmd += ["-map", f"{i + 1}:s"]
    for i, (lang, title, _text) in enumerate(_TRACKS):
        cmd += [f"-metadata:s:s:{i}", f"language={lang}", f"-metadata:s:s:{i}", f"title={title}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-c:s", "srt", str(out)]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    return out


def _probe(path) -> dict:
    import json

    res = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(res.stdout)


def test_every_extracted_sidecar_holds_the_stream_its_name_promises(tmp_path, app_ctx):
    from config import get_settings
    from services import embedded_extractor

    video = _build_mkv(tmp_path)
    probe = _probe(video)
    # Legacy-named German sidecar from an older run, exactly as on prod.
    legacy = video.with_suffix("").with_suffix(".ger.srt")
    legacy.write_text(_srt("GERMAN-LEGACY"), encoding="utf-8")

    settings = get_settings()
    with patch.object(type(settings), "embedded_allow_sdh", False, create=True):
        result = embedded_extractor.extract_and_cleanup(
            str(video),
            probe,
            keep_langs={"de", "en"},
            target_language="de",
            log_label="live-test",
        )

    assert result.any_extracted
    mismatches = []
    for entry in result.extracted:
        text = open(entry["output_path"], encoding="utf-8").read()
        expected = next(t for tag, _title, t in _TRACKS if tag == entry["language"])
        if entry["language"] == "ger":
            expected_any = {"GERMAN-TRACK", "GERMAN-LEGACY"}
        else:
            expected_any = {expected}
        if not any(e in text for e in expected_any):
            mismatches.append((entry["language"], entry["output_path"], text.strip()[-40:]))
    assert not mismatches, mismatches

    # The German primary must be German, never a foreign track under a .de name.
    assert result.primary_language == "ger"
    de_srt = video.with_suffix("").with_suffix(".de.srt")
    if de_srt.exists():
        assert "GERMAN" in de_srt.read_text(encoding="utf-8")
