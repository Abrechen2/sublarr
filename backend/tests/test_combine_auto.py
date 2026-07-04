"""Tests for automatic per-profile combine (V1.6 Feature #1, C3c).

maybe_auto_combine fires after a sidecar lands: when the governing profile has
combine_enabled and every combine_languages sidecar is present, it composes the
combined file. It never raises (the acquisition pipeline must not break), skips
silently on a missing language, and does not re-write an already-fresh combined
file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pysubs2

from services import combine_service


def _write_sidecar(directory, stem, lang, text="Text", fmt="srt"):
    subs = pysubs2.SSAFile()
    ev = pysubs2.SSAEvent(start=1000, end=3000)
    ev.plaintext = text
    subs.events.append(ev)
    path = os.path.join(directory, f"{stem}.{lang}.{fmt}")
    subs.save(path, format_=fmt)
    return path


_ENABLED = {
    "combine_enabled": True,
    "combine_format": "srt",
    "combine_languages": ["de", "en"],
    "combine_position": {"primary": "bottom", "secondary": "top"},
}


def test_auto_combine_composes_when_enabled_and_present(temp_dir, app_ctx):
    video = os.path.join(temp_dir, "ep.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep", "de", "Hallo")
    _write_sidecar(temp_dir, "ep", "en", "Hello")

    result = combine_service.maybe_auto_combine(video, profile=_ENABLED)
    assert result is not None
    assert os.path.exists(result["combined_path"])


def test_auto_combine_noop_when_disabled(temp_dir, app_ctx):
    video = os.path.join(temp_dir, "ep2.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep2", "de", "Hallo")
    _write_sidecar(temp_dir, "ep2", "en", "Hello")

    result = combine_service.maybe_auto_combine(video, profile={"combine_enabled": False})
    assert result is None
    assert not os.path.exists(os.path.join(temp_dir, "ep2.de-en.combined.srt"))


def test_auto_combine_silent_skip_on_missing_language(temp_dir, app_ctx):
    video = os.path.join(temp_dir, "ep3.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep3", "de", "Hallo")  # EN missing

    result = combine_service.maybe_auto_combine(video, profile=_ENABLED)
    assert result is None
    assert not os.path.exists(os.path.join(temp_dir, "ep3.de-en.combined.srt"))


def test_auto_combine_never_raises(temp_dir, monkeypatch, app_ctx):
    video = os.path.join(temp_dir, "ep4.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep4", "de", "Hallo")
    _write_sidecar(temp_dir, "ep4", "en", "Hello")

    monkeypatch.setattr(
        combine_service,
        "combine_for_video",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert combine_service.maybe_auto_combine(video, profile=_ENABLED) is None


def test_auto_combine_skips_when_already_fresh(temp_dir, app_ctx):
    video = os.path.join(temp_dir, "ep5.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep5", "de", "Hallo")
    _write_sidecar(temp_dir, "ep5", "en", "Hello")

    first = combine_service.maybe_auto_combine(video, profile=_ENABLED)
    assert first is not None
    out = first["combined_path"]
    mtime = os.path.getmtime(out)

    # Second call with no source change → no re-write.
    second = combine_service.maybe_auto_combine(video, profile=_ENABLED)
    assert second is None
    assert os.path.getmtime(out) == mtime


def test_auto_combine_resolves_profile_from_item(temp_dir, monkeypatch, app_ctx):
    video = os.path.join(temp_dir, "ep6.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep6", "de", "Hallo")
    _write_sidecar(temp_dir, "ep6", "en", "Hello")

    monkeypatch.setattr(
        "services.embedded_extractor.resolve_profile_for_item",
        lambda item, settings: _ENABLED,
    )
    result = combine_service.maybe_auto_combine(video, item={"sonarr_series_id": 42})
    assert result is not None
    assert os.path.exists(result["combined_path"])
