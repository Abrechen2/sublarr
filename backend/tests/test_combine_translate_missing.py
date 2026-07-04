"""Tests for the on-demand 'Translate & combine' path (V1.6 Feature #1, C3b).

When a requested combine language is missing and ``translate_missing`` is set,
combine_for_video generates it via the translation stack (translator.translate_file,
synchronously in the caller's app-context) and then composes. A disabled
translation feature or a failed translation surfaces a clear CombineError(422)
and leaves no partial combined artifact on disk.
"""

from __future__ import annotations

import os
from pathlib import Path

import pysubs2
import pytest

from services.subtitle_combine import CombineError


def _write_sidecar(directory, stem, lang, text="Text", fmt="srt"):
    subs = pysubs2.SSAFile()
    ev = pysubs2.SSAEvent(start=1000, end=3000)
    ev.plaintext = text
    subs.events.append(ev)
    path = os.path.join(directory, f"{stem}.{lang}.{fmt}")
    subs.save(path, format_=fmt)
    return path


def test_translate_missing_generates_then_combines(temp_dir, monkeypatch, app_ctx):
    from services import combine_service

    video = os.path.join(temp_dir, "ep.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep", "en", "Hello world")  # DE missing

    monkeypatch.setattr("services.combine_service._translation_enabled", lambda: True)

    def fake_translate_file(mkv_path, target_language=None, target_language_name=None, **kw):
        # Simulate the translation stack producing the missing DE sidecar.
        _write_sidecar(temp_dir, "ep", target_language, "Hallo Welt")
        return {"success": True, "output_path": f"{temp_dir}/ep.{target_language}.srt"}

    monkeypatch.setattr("translator.translate_file", fake_translate_file)

    result = combine_service.combine_for_video(
        video,
        ["de", "en"],
        "srt",
        None,
        [temp_dir],
        translate_missing=True,
    )
    assert os.path.exists(result["combined_path"])
    combined = pysubs2.SSAFile.load(result["combined_path"])
    joined = combined.events[0].plaintext
    assert "Hallo Welt" in joined and "Hello world" in joined


def test_translate_missing_disabled_raises_422(temp_dir, monkeypatch, app_ctx):
    from services import combine_service

    video = os.path.join(temp_dir, "ep2.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep2", "en", "Hello")

    monkeypatch.setattr("services.combine_service._translation_enabled", lambda: False)

    with pytest.raises(CombineError) as exc:
        combine_service.combine_for_video(
            video, ["de", "en"], "srt", None, [temp_dir], translate_missing=True
        )
    assert exc.value.status == 422
    assert not os.path.exists(os.path.join(temp_dir, "ep2.de-en.combined.srt"))


def test_translate_missing_failure_leaves_no_artifact(temp_dir, monkeypatch, app_ctx):
    from services import combine_service

    video = os.path.join(temp_dir, "ep3.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep3", "en", "Hello")

    monkeypatch.setattr("services.combine_service._translation_enabled", lambda: True)
    monkeypatch.setattr(
        "translator.translate_file",
        lambda *a, **k: {"success": False, "error": "quality gate failed"},
    )

    with pytest.raises(CombineError) as exc:
        combine_service.combine_for_video(
            video, ["de", "en"], "srt", None, [temp_dir], translate_missing=True
        )
    assert exc.value.status == 422
    assert "quality gate" in exc.value.message
    assert not os.path.exists(os.path.join(temp_dir, "ep3.de-en.combined.srt"))


def test_missing_without_translate_flag_does_not_translate(temp_dir, monkeypatch, app_ctx):
    from services import combine_service

    video = os.path.join(temp_dir, "ep4.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep4", "en", "Hello")

    called = {"n": 0}

    def _should_not_run(*a, **k):
        called["n"] += 1
        return {"success": True}

    monkeypatch.setattr("translator.translate_file", _should_not_run)

    with pytest.raises(CombineError) as exc:
        combine_service.combine_for_video(
            video, ["de", "en"], "srt", None, [temp_dir], translate_missing=False
        )
    assert exc.value.status == 422
    assert called["n"] == 0  # translation never attempted
