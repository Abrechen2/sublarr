"""Case B2 must not offer a same-language file to the translator.

Prod, 2026-09-10: the long-term watch flagged rising "suspicious log lines".
They were six `ValueError: refusing same-language translation (en → en)` from
the SRT→ASS upgrade path, on English-target items whose embedded ASS track
carried no language tag:

    Selected stream 0: '' (non-signs ASS)
    Case B2: Upgrading — translating source ASS to target ASS
    Loaded 1222 events, 21 styles
    ValueError: refusing same-language translation (en → en)

The guard did its job and nothing damaging was written. But B2 called
translate_ass without a source language, so it fell back to the global
`settings.source_language` — and only found out at the bottom of the stack,
after loading 1 222 events.

Case C1 already refuses this, and its comment states the reasoning: a stream
whose language IS the target wants extraction, not an LLM round-trip. The
same test simply never reached B2.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _core_env(monkeypatch, tmp_path):
    """Patch the package namespace translator.core resolves its helpers through.

    core.translate_file binds get_settings / get_media_streams /
    select_best_subtitle_stream from `_pkg()` at call time precisely so tests
    can patch them there — patching the module attributes does nothing.
    """
    import translator
    import translator.core as core

    settings = MagicMock()
    settings.source_language = "en"
    settings.target_language = "de"
    settings.target_language_name = "German"
    settings.auto_translate_any_source = True
    settings.auto_translate_source_languages = ["en", "ja"]
    monkeypatch.setattr(translator, "get_settings", lambda: settings, raising=False)

    media = tmp_path / "S01E01.mkv"
    media.write_bytes(b"x")
    core._test_media_path = str(media)
    return core


def _run_case_b2(core, stream_language, target_language):
    """Drive translate_file into Case B and report what B2 did."""
    import translator

    stream = {"format": "ass", "language": stream_language, "index": 0, "sub_index": 0}

    with (
        patch.object(translator, "get_media_streams", return_value={"streams": []}, create=True),
        patch.object(translator, "select_best_subtitle_stream", return_value=stream, create=True),
        patch.object(core, "detect_existing_target_for_lang", return_value="srt"),
        patch.object(core, "_search_providers_for_target_ass", return_value=None),
        patch.object(core, "translate_ass") as translate,
    ):
        translate.return_value = {"success": True, "stats": {}, "output_path": "/x.ass"}
        result = core.translate_file(core._test_media_path, target_language=target_language)
    return translate, result


def test_untagged_stream_is_not_translated_into_its_own_language(_core_env):
    """The reported case: no tag, global source en, target en."""
    translate, result = _run_case_b2(_core_env, stream_language="", target_language="en")

    translate.assert_not_called()
    # Falls through to B3: the target SRT stays, and nothing was translated.
    assert result["stats"]["skipped"] is True
    assert "no ass upgrade available" in result["stats"]["reason"].lower()


def test_a_tagged_english_stream_is_not_translated_into_english(_core_env):
    translate, _ = _run_case_b2(_core_env, stream_language="eng", target_language="en")
    translate.assert_not_called()


def test_a_real_translation_still_runs_and_carries_its_source(_core_env):
    """English source, German target — B2 must work, and say what it reads from."""
    translate, _ = _run_case_b2(_core_env, stream_language="eng", target_language="de")

    translate.assert_called_once()
    assert translate.call_args.kwargs["source_language"] == "en", (
        "B2 used to pass no source language at all, so the flow fell back to "
        "the global setting instead of the stream it actually selected"
    )
