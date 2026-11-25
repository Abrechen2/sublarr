"""The SRT skip must not outlive the assumption it rests on.

GH #206: `wanted_skip_srt_on_no_ass` defaults to True and skips steps 3+4
whenever steps 1+2 found no ASS. The reasoning in the code — "providers
likely have nothing" — holds while ASS availability is a fair proxy for
subtitle availability. On an anime library it is; on a live-action one it is
backwards, since SRT is the norm and ASS the exception.

The reporter's install ran `wanted_anime_only = False`: across 976 wanted
items, the SRT stage was skipped 974 times and ran zero times. One title
confirmed by hand had no ASS from any provider and an English SRT waiting at
OpenSubtitles.
"""

from types import SimpleNamespace

import pytest

from wanted_search.process import skip_srt_reason


def _settings(**overrides):
    base = {"wanted_skip_srt_on_no_ass": True, "wanted_anime_only": True}
    base.update(overrides)
    return SimpleNamespace(**base)


def test_anime_only_library_still_skips_when_no_ass_was_found():
    """The optimisation survives where its assumption holds."""
    reason = skip_srt_reason(_settings(), ass_had_results=False)
    assert reason is not None
    assert "wanted_skip_srt_on_no_ass" in reason


def test_mixed_library_runs_the_srt_steps():
    """Absence of ASS says nothing about SRT once live action is in scope."""
    assert skip_srt_reason(_settings(wanted_anime_only=False), ass_had_results=False) is None


def test_no_skip_once_an_ass_candidate_exists():
    assert skip_srt_reason(_settings(), ass_had_results=True) is None


def test_the_setting_still_turns_the_whole_thing_off():
    assert (
        skip_srt_reason(_settings(wanted_skip_srt_on_no_ass=False), ass_had_results=False) is None
    )


@pytest.mark.parametrize("missing", ["wanted_skip_srt_on_no_ass", "wanted_anime_only"])
def test_an_absent_setting_falls_back_to_its_default(missing):
    """Optional settings are read with getattr defaults, per the house rule."""
    values = {"wanted_skip_srt_on_no_ass": True, "wanted_anime_only": True}
    del values[missing]
    reason = skip_srt_reason(SimpleNamespace(**values), ass_had_results=False)
    assert reason is not None, "both defaults are True, so an anime-only skip is expected"


# The helper alone is not enough: #206 was about the SRT step never running.
# Drive the real step sequence and assert Step 3 is reached on a mixed library
# when Steps 1+2 found no ASS.
def _run_steps(monkeypatch, *, anime_only: bool):
    from unittest.mock import MagicMock

    import wanted_search.process as process

    calls: list[str] = []
    monkeypatch.setattr(process, "abort_requested", lambda: False)
    monkeypatch.setattr(process, "_try_target_ass_direct", lambda ctx: None)

    def no_source_ass(ctx):
        ctx["ass_had_results"] = False

    monkeypatch.setattr(process, "_try_source_ass_translation", no_source_ass)
    monkeypatch.setattr(
        process, "_try_target_srt_direct", lambda ctx: calls.append("srt") or {"status": "found"}
    )
    monkeypatch.setattr("services.series_format.get_series_format_requirement", lambda key: "any")
    settings = SimpleNamespace(wanted_skip_srt_on_no_ass=True, wanted_anime_only=anime_only)
    ctx = {
        "item": {"id": 1, "sonarr_series_id": 5},
        "item_id": 1,
        "settings": settings,
        "ass_had_results": False,
        "auto_translate": True,
        "manager": MagicMock(),
        # Stop before Step 5 (extraction/translation) — only Steps 1-4 matter.
        "dry_run": True,
    }
    return calls, process._run_search_steps(ctx)


def test_mixed_library_reaches_the_srt_step(monkeypatch):
    calls, result = _run_steps(monkeypatch, anime_only=False)
    assert calls == ["srt"]
    assert result == {"status": "found"}


def test_anime_only_library_skips_the_srt_step(monkeypatch):
    calls, _ = _run_steps(monkeypatch, anime_only=True)
    assert calls == []
