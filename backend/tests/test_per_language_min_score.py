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


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "[1, 2]",
        None,
        '{"de": 1e309}',
        '{"de": NaN}',
        '{"de": -1e309}',
        '{"de": ' + "1" + "0" * 400 + "}",
    ],
)
def test_a_malformed_value_is_ignored(raw):
    assert per_language_min_scores(SimpleNamespace(score_threshold_per_language=raw)) == {}


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ('{"de": 80}', True),
        ('{"de": 0, "en": 10000}', True),
        ("{}", True),
        ("", True),
        ("nope", False),
        ('{"de": "high"}', False),
        ('{"de": 1e309}', False),  # infinity (#65)
        ('{"de": -1e309}', False),
        ('{"de": NaN}', False),
        ('{"de": -5}', False),
        ('{"de": 10001}', False),
        ('{"de": ' + "1" + "0" * 400 + "}", False),  # 401-digit integer (#65 follow-up)
        ('{"de": -' + "1" + "0" * 400 + "}", False),
    ],
)
def test_put_checks_the_shape(client, value, ok):
    response = client.put("/api/v1/config", json={"score_threshold_per_language": value})

    assert (response.status_code == 200) is ok, response.get_json()


def test_a_saved_threshold_reaches_a_manager_created_before_the_save(client, monkeypatch):
    """#64: the manager kept its creation-time settings, so the saved value had no effect."""
    import decision_log
    from providers import get_provider_manager
    from providers.base import SubtitleFormat, SubtitleResult, VideoQuery

    monkeypatch.setattr("db.blacklist.is_blacklisted", lambda *a, **kw: False)
    assert client.put("/api/v1/config", json={"providers_enabled": "none"}).status_code == 200
    with client.application.app_context():
        manager = get_provider_manager()

    response = client.put("/api/v1/config", json={"score_threshold_per_language": '{"de": 10000}'})
    assert response.status_code == 200, response.get_json()

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
    with client.application.app_context():
        assert get_provider_manager() is manager
        kept = manager._finalise_search_results(
            [result("de", "de1"), result("en", "en1")], query, None, 0, None, None
        )

    assert [r.subtitle_id for r in kept] == ["en1"]


def test_the_import_reports_a_huge_integer_instead_of_failing(client):
    value = '{"de": ' + "1" + "0" * 400 + "}"

    response = client.post("/api/v1/config/import", json={"score_threshold_per_language": value})

    assert response.status_code == 200, response.get_json()
    assert [e["key"] for e in response.get_json()["skipped_invalid"]] == [
        "score_threshold_per_language"
    ]
