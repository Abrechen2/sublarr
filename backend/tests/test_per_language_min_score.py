"""Settings → Scoring → per-language scores take effect (#61 A16).

``score_threshold_per_language`` was saved and never read; the search applied
the global minimum to every language.
"""

from types import SimpleNamespace

import pytest

from providers.search_coordinator.scoring import per_language_min_scores


def test_the_json_is_read_by_canonical_language():
    settings = SimpleNamespace(score_threshold_per_language='{"ger": 80, "en": 50.5, "x": true}')

    assert per_language_min_scores(settings) == {"de": 80, "en": 50}


@pytest.mark.parametrize("raw", ["", "not json", "[1, 2]", None])
def test_a_malformed_value_is_ignored(raw):
    assert per_language_min_scores(SimpleNamespace(score_threshold_per_language=raw)) == {}


@pytest.mark.parametrize(
    ("value", "ok"),
    [('{"de": 80}', True), ("{}", True), ("", True), ("nope", False), ('{"de": "high"}', False)],
)
def test_put_checks_the_shape(client, value, ok):
    response = client.put("/api/v1/config", json={"score_threshold_per_language": value})

    assert (response.status_code == 200) is ok, response.get_json()


def test_the_search_drops_results_below_their_languages_minimum(app_ctx, monkeypatch):
    import decision_log
    from providers import ProviderManager
    from providers.base import SubtitleFormat, SubtitleResult, VideoQuery

    monkeypatch.setattr("db.blacklist.is_blacklisted", lambda *a, **kw: False)
    manager = ProviderManager.__new__(ProviderManager)
    manager.settings = SimpleNamespace(score_threshold_per_language='{"de": 10000}')
    query = VideoQuery(series_title="Show", season=1, episode=2, languages=["de", "en"])

    def result(lang, sid):
        return SubtitleResult(
            provider_name="p",
            subtitle_id=sid,
            language=lang,
            format=SubtitleFormat.SRT,
            filename=f"Show.S01E02.{lang}.srt",
            matches={"series", "season", "episode"},
        )

    decision_log.finish()
    kept = manager._finalise_search_results(
        [result("de", "de1"), result("en", "en1")], query, None, 0, None, None
    )

    assert [r.subtitle_id for r in kept] == ["en1"]
