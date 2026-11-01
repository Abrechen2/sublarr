"""The profile's forced preference sees signs & songs that only the file name marks.

AnimeTosho, Jimaku and SubDL do not flag forced subtitles; the coordinator
classifies them from the file name after scoring. The score was computed
first, so "Only" rejected the signs file as well and the full subtitle stayed
on top, and "Prefer" never applied.
"""

import pytest


def _finalise(client, monkeypatch, pref):
    import decision_log
    from providers import get_provider_manager
    from providers.base import SubtitleFormat, SubtitleResult, VideoQuery

    monkeypatch.setattr("db.blacklist.is_blacklisted", lambda *a, **kw: False)
    assert client.put("/api/v1/config", json={"providers_enabled": "none"}).status_code == 200
    query = VideoQuery(series_title="Show", season=1, episode=2, languages=["en"])
    query.forced_scoring = pref

    def result(sid, filename):
        return SubtitleResult(
            provider_name="animetosho",
            subtitle_id=sid,
            language="en",
            format=SubtitleFormat.ASS,
            filename=filename,
            matches={"series", "season", "episode", "release_group"},
        )

    results = [
        result("full", "[Group] Show - S01E02 (1080p).en.ass"),
        result("signs", "[Group] Show - S01E02 (1080p).en.signs.ass"),
    ]
    decision_log.finish()
    with client.application.app_context():
        return get_provider_manager()._finalise_search_results(results, query, None, 0, None, None)


@pytest.mark.parametrize("pref", ["only", "prefer"])
def test_signs_recognised_by_name_win_under_the_profile_preference(client, monkeypatch, pref):
    kept = _finalise(client, monkeypatch, pref)

    assert kept[0].subtitle_id == "signs"
    assert kept[0].score > kept[1].score


def test_include_still_scores_both_alike(client, monkeypatch):
    kept = _finalise(client, monkeypatch, "include")

    assert kept[0].score == kept[1].score
