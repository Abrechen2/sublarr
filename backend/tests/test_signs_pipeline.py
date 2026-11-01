"""Kind-aware search: full items skip signs, [Forced] items rank signs first."""

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery


def _result(sid, filename, fmt=SubtitleFormat.ASS, provider_data=None, forced=False):
    return SubtitleResult(
        provider_name="animetosho",
        subtitle_id=sid,
        language="en",
        format=fmt,
        filename=filename,
        matches={"series", "season", "episode"},
        provider_data=provider_data or {},
        forced=forced,
    )


def _finalise(client, monkeypatch, query, results):
    import decision_log
    from providers import get_provider_manager

    monkeypatch.setattr("db.blacklist.is_blacklisted", lambda *a, **kw: False)
    assert client.put("/api/v1/config", json={"providers_enabled": "none"}).status_code == 200
    decision_log.finish()
    with client.application.app_context():
        return get_provider_manager()._finalise_search_results(results, query, None, 0, None, None)


def _query(**kw):
    return VideoQuery(series_title="Show", season=1, episode=2, languages=["en"], **kw)


def test_the_regular_item_never_gets_a_signs_track(client, monkeypatch):
    kept = _finalise(
        client,
        monkeypatch,
        _query(full_only=True),
        [_result("signs", "Signs__Songs.eng.ass"), _result("dialogue", "Dialogue.eng.ass")],
    )

    assert [r.subtitle_id for r in kept] == ["dialogue"]


def test_interactive_search_shows_every_kind_with_its_label(client, monkeypatch):
    kept = _finalise(
        client,
        monkeypatch,
        _query(),
        [
            _result("signs", "Signs__Songs.eng.ass"),
            _result("dialogue", "Dialogue.eng.ass"),
            _result("forced", "track3.eng.ass", provider_data={"track_forced": True}),
        ],
    )

    assert {r.subtitle_id: r.kind for r in kept} == {
        "signs": "signs",
        "dialogue": "full",
        "forced": "forced",
    }


def test_prefer_signs_ranks_a_signs_srt_above_a_forced_ass(client, monkeypatch):
    kept = _finalise(
        client,
        monkeypatch,
        _query(forced_only=True, prefer_signs=True),
        [
            _result("forced-ass", "English.Forced.en.ass"),
            _result("signs-srt", "Show.S01E02.Signs.and.Songs.en.srt", fmt=SubtitleFormat.SRT),
        ],
    )

    assert [r.subtitle_id for r in kept] == ["signs-srt", "forced-ass"]


def test_without_the_preference_forced_items_keep_ass_first(client, monkeypatch):
    kept = _finalise(
        client,
        monkeypatch,
        _query(forced_only=True),
        [
            _result("signs-srt", "Show.S01E02.Signs.and.Songs.en.srt", fmt=SubtitleFormat.SRT),
            _result("forced-ass", "English.Forced.en.ass"),
        ],
    )

    assert [r.subtitle_id for r in kept] == ["forced-ass", "signs-srt"]


def test_likely_signs_rank_after_certain_signs(client, monkeypatch):
    kept = _finalise(
        client,
        monkeypatch,
        _query(forced_only=True, prefer_signs=True),
        [
            _result(
                "likely",
                "English_Signs_Official.eng.ass",
                provider_data={"track_name": "English (Signs) Official"},
            ),
            _result(
                "certain", "Signs__Songs.eng.ass", provider_data={"track_name": "Signs & Songs"}
            ),
        ],
    )

    assert [r.subtitle_id for r in kept] == ["certain", "likely"]


def test_the_cache_separates_forced_and_regular_searches():
    from providers.search_coordinator.cache import SearchCacheMixin

    cache = object.__new__(SearchCacheMixin)
    cache._language_excludes_cache_token = lambda: ""
    keys = {
        cache._make_cache_key(_query(**kw))
        for kw in (
            {},
            {"forced_only": True},
            {"full_only": True},
            {"forced_only": True, "prefer_signs": True},
            {"forced_scoring": "only"},
            {"hi_preference": "exclude"},
        )
    }

    assert len(keys) == 6


def test_kind_survives_the_cache():
    from providers.search_coordinator.cache import SearchCacheMixin

    result = _result("signs", "Signs__Songs.eng.ass")
    result.set_kind("signs", 0.95)
    restored = SearchCacheMixin._deserialize_results(
        [
            {
                "provider_name": result.provider_name,
                "subtitle_id": result.subtitle_id,
                "language": "en",
                "format": "ass",
                "forced": result.forced,
                "subtitle_kind": result.subtitle_kind,
                "kind_confidence": result.kind_confidence,
            }
        ]
    )[0]

    assert (restored.kind, restored.forced, restored.kind_confidence) == ("signs", True, 0.95)


def test_a_full_perfect_match_does_not_end_a_forced_search():
    from providers.search_coordinator import _fits_requested_kind

    full = _result("full", "Dialogue.eng.ass")
    signs = _result("signs", "Signs__Songs.eng.ass")

    assert not _fits_requested_kind(full, _query(forced_only=True))
    assert _fits_requested_kind(signs, _query(forced_only=True))
    assert not _fits_requested_kind(signs, _query(full_only=True))
    assert _fits_requested_kind(full, _query())
