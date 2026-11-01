"""A signs-only file must not pass as the full dialogue subtitle.

Prod 2026-11 (Slime S03E24): AnimeTosho's "English Signs [Official]" track,
7 events in style "Default" with actor "Sign", replaced a 405-cue English SRT
as an "SRT->ASS upgrade" and was then translated to German, 7 of 7 lines,
quality 93, no warning. The German sidecar held no dialogue at all.
"""

import os
from unittest.mock import MagicMock

import pytest

_HEAD = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,20
Style: Signs,Arial,20

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# The prod file, events as shipped (text shortened).
SIGNS_ONLY = (
    _HEAD
    + "Dialogue: 0,0:00:54.95,0:00:59.66,Default,Sign,0,0,0,,{\\an8}EPISODE 72: AFTER THE FESTIVAL\n"
    + "Dialogue: 0,0:12:14.12,0:12:27.89,Default,Sign,0,0,0,,{\\an8}KINGDOM OF BLUMUND\n"
    + "Dialogue: 0,0:15:48.59,0:15:52.43,Default,Sign,0,0,0,,{\\an8}THE SECRET OF FAITH AND GRACE\n"
    + "Dialogue: 0,0:15:52.43,0:15:54.09,Default,Sign,0,0,0,,{\\an8}THE SECRET\\NHIDDEN ART\n"
    + "Dialogue: 0,0:15:54.09,0:15:54.43,Default,Sign,0,0,0,,{\\an8}THE SECRET\\NHIDDEN ART\\NANALYSIS\n"
    + "Dialogue: 0,0:15:54.43,0:15:57.39,Default,Sign,0,0,0,,{\\an8}THE SECRET\\NEXTREMELY EFFECTIVE\n"
    + "Dialogue: 0,0:17:34.90,0:17:36.74,Default,Sign,0,0,0,,{\\an8}PSEUDONYM'S GRILL\n"
).encode()

EPISODE_S = 1472.0


def _ts(seconds: float) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _ass(dialogue: int, *, span_s: float = 1400.0, signs: int = 0, layers: int = 1, actor=""):
    step = span_s / max(dialogue, 1)
    lines = [
        f"Dialogue: {layer},{_ts(i * step)},{_ts(i * step + 1.5)},Default,{actor},0,0,0,,line {i}"
        for i in range(dialogue)
        for layer in range(layers)
    ] + [
        f"Dialogue: 0,{_ts(i * 7.0)},{_ts(i * 7.0 + 2)},Signs,,0,0,0,,{{\\pos(10,10)}}sign {i}"
        for i in range(signs)
    ]
    return (_HEAD + "\n".join(lines) + "\n").encode()


def _srt(cues: int, span_s: float = 1400.0) -> bytes:
    step = span_s / max(cues, 1)
    blocks = []
    for i in range(cues):
        a, b = i * step, i * step + 1.5
        fmt = lambda t: _ts(t).replace(".", ",") + "0"  # noqa: E731
        blocks.append(f"{i + 1}\n0{fmt(a)} --> 0{fmt(b)}\nline {i}\n")
    return "\n".join(blocks).encode()


# --- the assessment -------------------------------------------------------------


def test_the_prod_signs_file_is_sparse():
    from subtitle_dialogue import assess_content

    verdict = assess_content(SIGNS_ONLY, EPISODE_S)

    assert verdict.dialogue_events == 0
    assert verdict.sparse_reason


def test_seven_plain_events_are_sparse_even_without_the_actor_hint():
    from subtitle_dialogue import assess_content

    content = SIGNS_ONLY.replace(b",Sign,", b",,")

    assert assess_content(content, EPISODE_S).sparse_reason
    assert assess_content(content, None).sparse_reason  # tiny, duration unknown


def test_a_real_dialogue_track_is_plausible():
    from subtitle_dialogue import assess_content

    verdict = assess_content(_ass(400), EPISODE_S)

    assert verdict.dialogue_events == 400
    assert verdict.sparse_reason is None


def test_a_short_format_episode_with_few_lines_passes():
    from subtitle_dialogue import assess_content

    # A 3-minute short with 15 lines is 5/min — legitimately small.
    assert assess_content(_ass(15, span_s=170), 180.0).sparse_reason is None


def test_a_one_minute_short_with_seven_lines_passes():
    from subtitle_dialogue import assess_content

    assert assess_content(_ass(7, span_s=55), 60.0).sparse_reason is None
    assert assess_content(_ass(0, signs=5), 60.0).sparse_reason  # but not an empty one


def test_dialogue_after_an_inline_drawing_counts():
    from subtitle_dialogue import assess_content

    content = _ass(300).replace(b",,line ", b",,{\\p1}m 0 0 l 10 0 10 10{\\p0}line ")

    assert assess_content(content, EPISODE_S).dialogue_events == 300


def test_unbalanced_braces_cost_linear_time():
    import time

    from subtitle_dialogue import assess_content

    content = (
        _HEAD.encode()
        + b"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,"
        + b"{a" * 40000
        + b"\n"
    )
    start = time.perf_counter()
    assess_content(content, EPISODE_S)

    assert time.perf_counter() - start < 1.0


def test_few_lines_over_a_long_episode_are_sparse():
    from subtitle_dialogue import assess_content

    assert assess_content(_ass(15), EPISODE_S).sparse_reason
    assert assess_content(_ass(35), EPISODE_S).sparse_reason
    # Forty lines or more are left alone: sparse for 24 min, but possible.
    assert assess_content(_ass(45), EPISODE_S).sparse_reason is None
    # A 12-minute short with 30 lines (2.5/min) is fine.
    assert assess_content(_ass(30, span_s=700), 720.0).sparse_reason is None


def test_layers_are_counted_once():
    from subtitle_dialogue import assess_content

    # Six events, each drawn on three layers: still six lines, not eighteen.
    verdict = assess_content(_ass(6, layers=3), EPISODE_S)

    assert verdict.dialogue_events == 6
    assert verdict.sparse_reason


def test_a_typeset_heavy_signs_track_is_not_saved_by_its_event_count():
    from subtitle_dialogue import assess_content

    # Thousands of animated sign events, no dialogue lines.
    assert assess_content(_ass(0, signs=3000), EPISODE_S).sparse_reason


def test_srt_is_judged_by_its_cues():
    from subtitle_dialogue import assess_content

    assert assess_content(_srt(7), EPISODE_S).sparse_reason
    assert assess_content(_srt(400), EPISODE_S).sparse_reason is None


def test_unreadable_content_gives_no_verdict():
    from subtitle_dialogue import assess_content

    assert assess_content(b"", EPISODE_S) is None
    assert assess_content(b"\xff\xfe garbage", EPISODE_S) is None


@pytest.mark.parametrize(
    ("old", "new", "dropped"),
    [
        (_srt(405), SIGNS_ONLY, True),
        (_srt(405), _ass(60), True),  # 15 % of the old lines
        (_srt(405), _ass(380), False),  # cues merged or split: fine
        (_srt(30), SIGNS_ONLY, True),  # a complete short loses its lines too
        (_srt(6), _ass(1), False),  # too few lines to call it a lost track
    ],
    ids=["signs-for-srt", "fifteen-percent", "merged-cues", "short", "tiny"],
)
def test_dialogue_drop(old, new, dropped):
    from subtitle_dialogue import dialogue_drop

    assert bool(dialogue_drop(old, new)) is dropped


def test_the_upgrade_keeps_a_full_srt_against_a_signs_ass(tmp_path):
    from wanted_search.process import _dialogue_drop_reason

    srt = tmp_path / "ep.en.srt"
    srt.write_bytes(_srt(405))

    assert _dialogue_drop_reason(str(srt), SIGNS_ONLY)
    assert _dialogue_drop_reason(str(srt), _ass(400)) is None
    assert _dialogue_drop_reason(str(tmp_path / "missing.srt"), SIGNS_ONLY) is None


def test_format_cleanup_keeps_a_full_srt_beside_a_signs_ass(tmp_path, app_ctx):
    from services.cleanup_executors import execute_format_upgrade

    (tmp_path / "Show - S01E01.mkv").write_bytes(b"")
    (tmp_path / "Show - S01E01.en.srt").write_bytes(_srt(405))
    (tmp_path / "Show - S01E01.en.ass").write_bytes(SIGNS_ONLY)
    (tmp_path / "Show - S01E01.de.srt").write_bytes(_srt(405))
    (tmp_path / "Show - S01E01.de.ass").write_bytes(_ass(400))

    result = execute_format_upgrade(str(tmp_path), {"keep_format": "ass"}, dry_run=False)

    assert (tmp_path / "Show - S01E01.en.srt").exists()
    assert not (tmp_path / "Show - S01E01.de.srt").exists()  # a real upgrade still applies
    assert result["deleted"] == 1, result


# --- after download -------------------------------------------------------------


def _result(fmt="ass"):
    from providers.base import SubtitleFormat, SubtitleResult

    result = SubtitleResult(
        provider_name="animetosho",
        subtitle_id="510324:2884598",
        language="en",
        format=SubtitleFormat.ASS if fmt == "ass" else SubtitleFormat.SRT,
    )
    result.set_kind("full", 1.0)
    return result


def test_a_full_item_refuses_the_prod_signs_file():
    from forced_detection import content_kind_mismatch

    query = MagicMock(forced_only=False, full_only=True)

    reason = content_kind_mismatch(_result(), SIGNS_ONLY, query, duration_s=EPISODE_S)

    assert reason and "sparse" in reason


def test_a_full_item_refuses_a_sparse_srt():
    from forced_detection import content_kind_mismatch

    query = MagicMock(forced_only=False, full_only=True)

    assert content_kind_mismatch(_result("srt"), _srt(7), query, duration_s=EPISODE_S)
    assert content_kind_mismatch(_result("srt"), _srt(400), query, duration_s=EPISODE_S) is None


def test_without_a_known_video_length_the_download_is_not_judged_sparse():
    from forced_detection import content_kind_mismatch

    query = MagicMock(forced_only=False, full_only=True)

    assert content_kind_mismatch(_result("srt"), _srt(7), query, duration_s=None) is None


def test_a_forced_item_still_takes_the_signs_file():
    from forced_detection import content_kind_mismatch

    query = MagicMock(forced_only=True, full_only=False)

    assert content_kind_mismatch(_result(), SIGNS_ONLY, query, duration_s=EPISODE_S) is None


def test_the_download_gate_passes_the_video_length_to_the_kind_check(monkeypatch):
    import subtitle_plausibility
    from providers.download_manager import _LengthCheck

    monkeypatch.setattr(subtitle_plausibility, "video_duration_s", lambda _p: EPISODE_S)
    check = _LengthCheck(MagicMock(file_path="/media/x.mkv"))

    assert check.duration() == EPISODE_S


# --- translation ----------------------------------------------------------------


def test_translation_refuses_a_signs_only_source(tmp_path, monkeypatch):
    import subtitle_plausibility
    import translator.core as core
    from translator.errors import SPARSE_SOURCE

    monkeypatch.setattr(subtitle_plausibility, "video_duration_s", lambda _p: EPISODE_S)
    called = MagicMock()
    monkeypatch.setattr(core._pkg(), "_translate_with_manager", called)
    video = tmp_path / "ep.mkv"
    video.write_bytes(b"")
    source = tmp_path / "ep.en.ass"
    source.write_bytes(SIGNS_ONLY.replace(b",Sign,", b",,"))

    result = core._translate_external_ass(str(video), str(source), target_language="de")

    assert result["success"] is False
    assert result["reason"] == SPARSE_SOURCE
    called.assert_not_called()


def test_without_a_known_video_length_translation_is_not_judged(tmp_path, monkeypatch):
    import subtitle_plausibility
    from subtitle_dialogue import sparse_source_reason
    from subtitle_encoding import load_subtitle_file

    monkeypatch.setattr(subtitle_plausibility, "video_duration_s", lambda _p: None)
    source = tmp_path / "ep.en.ass"
    source.write_bytes(SIGNS_ONLY)

    assert sparse_source_reason(load_subtitle_file(str(source)), "/x.mkv", is_ass=True) is None


def test_srt_translation_refuses_a_sparse_source(tmp_path, monkeypatch):
    import subtitle_plausibility
    import translator.core as core
    from translator.errors import SPARSE_SOURCE

    monkeypatch.setattr(subtitle_plausibility, "video_duration_s", lambda _p: EPISODE_S)
    called = MagicMock()
    monkeypatch.setattr(core._pkg(), "_translate_with_manager", called)
    video = tmp_path / "ep.mkv"
    video.write_bytes(b"")
    source = tmp_path / "ep.en.srt"
    source.write_bytes(_srt(7))

    result = core.translate_srt_from_file(str(video), str(source), target_language="de")

    assert result["success"] is False
    assert result["reason"] == SPARSE_SOURCE
    called.assert_not_called()


def test_the_automation_runner_does_not_retry_a_sparse_source():
    from services import subtitle_automation_runner as runner

    assert runner.SPARSE_SOURCE in runner._TERMINAL_TRANSLATE_REASONS


_SPARSE = {"success": False, "reason": "sparse_source", "error": "signs", "stats": {}}
_DONE = {"success": True, "stats": {}, "output_path": "x"}


def _translate_file_env(tmp_path, monkeypatch, *, stream=None, external=None, provider=None):
    """translate_file with every source stubbed; returns (video, sources tried)."""
    import translator.core as core
    import translator.jobs as jobs

    video = tmp_path / "ep.mkv"
    video.write_bytes(b"\x00")
    settings = MagicMock(target_language="de", target_language_name="German", source_language="en")
    pkg = MagicMock()
    pkg.get_settings.return_value = settings
    pkg.get_media_streams.return_value = {"streams": []}
    pkg.select_best_subtitle_stream.return_value = stream
    monkeypatch.setattr(core, "_pkg", lambda: pkg)
    monkeypatch.setattr(core, "detect_existing_target_for_lang", lambda *_a, **_k: None)
    monkeypatch.setattr(core, "_search_providers_for_target_ass", lambda *_a, **_k: None)
    monkeypatch.setattr(core, "_get_whisper_fallback_min_score", lambda: 0)
    monkeypatch.setattr(core, "_is_whisper_enabled", lambda: False)
    monkeypatch.setattr(jobs, "_record_config_hash_for_result", lambda *_a, **_k: None)
    monkeypatch.setattr(jobs, "_notify_integrations", lambda *_a, **_k: None)
    monkeypatch.setattr(
        core,
        "find_any_source_sub",
        lambda *_a, **_k: (external, "en") if external else (None, None),
    )
    monkeypatch.setattr(
        core,
        "_search_providers_for_source_sub",
        lambda *_a, **_k: (provider, "ass", 300, "en") if provider else (None, None, 0, None),
    )
    tried = []
    full = {provider, str(tmp_path / "ep.en.srt")}

    def _source(name):
        def _translate(_mkv, source, *_a, **_kw):
            label = source if isinstance(source, str) else name
            tried.append(label)
            return _DONE if label in full else _SPARSE

        return _translate

    monkeypatch.setattr(core, "_translate_external_ass", _source("external_ass"))
    monkeypatch.setattr(core, "translate_srt_from_file", _source("external_srt"))
    monkeypatch.setattr(core, "translate_ass", _source("embedded_ass"))
    monkeypatch.setattr(core, "translate_srt_from_stream", _source("embedded_srt"))
    return video, tried


def test_a_signs_only_sidecar_falls_through_to_the_provider_source_search(tmp_path, monkeypatch):
    import translator.core as core

    provider = str(tmp_path / "provider.en.ass")
    video, tried = _translate_file_env(
        tmp_path, monkeypatch, external=str(tmp_path / "ep.en.ass"), provider=provider
    )

    result = core.translate_file(str(video))

    assert tried == [str(tmp_path / "ep.en.ass"), provider]
    assert result["success"] is True


def test_a_signs_only_ass_sidecar_falls_back_to_the_srt_beside_it(tmp_path, monkeypatch):
    import translator.core as core

    (tmp_path / "ep.en.srt").write_bytes(_srt(400))
    video, tried = _translate_file_env(tmp_path, monkeypatch, external=str(tmp_path / "ep.en.ass"))

    result = core.translate_file(str(video))

    assert tried == [str(tmp_path / "ep.en.ass"), str(tmp_path / "ep.en.srt")]
    assert result["success"] is True


def test_a_signs_only_embedded_track_falls_through_to_other_sources(tmp_path, monkeypatch):
    import translator.core as core

    provider = str(tmp_path / "provider.en.ass")
    stream = {"format": "ass", "index": 3, "language": "en"}
    video, tried = _translate_file_env(tmp_path, monkeypatch, stream=stream, provider=provider)

    result = core.translate_file(str(video))

    assert tried == ["embedded_ass", provider]
    assert result["success"] is True


def test_with_no_other_source_the_refusal_keeps_its_terminal_reason(tmp_path, monkeypatch):
    import translator.core as core
    from translator.errors import SPARSE_SOURCE

    video, tried = _translate_file_env(tmp_path, monkeypatch, external=str(tmp_path / "ep.en.ass"))

    result = core.translate_file(str(video))

    assert tried == [str(tmp_path / "ep.en.ass")]
    assert result["reason"] == SPARSE_SOURCE


def test_an_embedded_track_without_dialogue_styles_also_falls_through(tmp_path, monkeypatch):
    import translator.core as core
    from translator.errors import NO_TRANSLATABLE_DIALOGUE

    provider = str(tmp_path / "provider.en.ass")
    stream = {"format": "ass", "index": 3, "language": "en"}
    video, tried = _translate_file_env(tmp_path, monkeypatch, stream=stream, provider=provider)
    monkeypatch.setattr(
        core,
        "translate_ass",
        lambda *_a, **_k: (
            tried.append("embedded_ass")
            or {"success": False, "reason": NO_TRANSLATABLE_DIALOGUE, "stats": {}}
        ),
    )

    result = core.translate_file(str(video))

    assert tried == ["embedded_ass", provider]
    assert result["success"] is True


def test_a_machine_translated_srt_beside_the_signs_ass_is_not_a_source(tmp_path, monkeypatch):
    import services.mt_sidecars as mt
    import translator.core as core

    srt = tmp_path / "ep.en.srt"
    srt.write_bytes(_srt(400))
    monkeypatch.setattr(mt, "machine_translation_paths", lambda _v: {os.path.normcase(str(srt))})
    video, tried = _translate_file_env(tmp_path, monkeypatch, external=str(tmp_path / "ep.en.ass"))

    core.translate_file(str(video))

    assert tried == [str(tmp_path / "ep.en.ass")]


# --- source discovery -----------------------------------------------------------


def test_a_forced_or_signs_sidecar_is_never_a_translation_source(tmp_path, monkeypatch):
    from translator._helpers import find_any_source_sub

    video = tmp_path / "ep.mkv"
    video.write_bytes(b"")
    (tmp_path / "ep.en.forced.srt").write_bytes(_srt(7))
    (tmp_path / "ep.en.signs.ass").write_bytes(SIGNS_ONLY)

    assert find_any_source_sub(str(video), "de", preferred_languages=["en"]) == (None, None)

    (tmp_path / "ep.en.srt").write_bytes(_srt(400))

    assert find_any_source_sub(str(video), "de", preferred_languages=["en"]) == (
        str(tmp_path / "ep.en.srt"),
        "en",
    )
