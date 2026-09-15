"""SubSource v1 contract from https://subsource.net/api-docs (2026-09-15).

Fixtures reflect the documented schema, not a keyed live response. A release
still needs a live account check of search and ZIP download (GH #207).
"""

import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from providers.base import ProviderAuthError, ProviderError, ProviderRateLimitError, VideoQuery
from providers.subsource import SubsourceProvider

API = "https://api.subsource.net/api/v1"
MOVIE = {
    "movieId": 12345,
    "title": "Some Movie",
    "type": "movie",
    "releaseYear": 2023,
    "imdbId": "tt1234567",
}
SUBTITLE = {
    "subtitleId": 6789,
    "movieId": 12345,
    "language": "english",
    "releaseInfo": ["Some.Movie.2023.BluRay"],
    "hearingImpaired": True,
    "foreignParts": True,
}


def _response(data):
    return MagicMock(status_code=200, json=lambda: {"success": True, "data": data})


def _provider(*responses):
    p = SubsourceProvider(api_key="test-key")
    p.session = MagicMock()
    p.session.get.side_effect = responses
    return p


def _zip(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in files:
            archive.writestr(name, data)
    return out.getvalue()


def test_search_uses_documented_movie_and_subtitle_requests():
    p = _provider(_response([MOVIE]), _response([SUBTITLE]))
    results = p.search(
        VideoQuery(title="Some Movie", year=2023, imdb_id="tt1234567", languages=["en"])
    )
    assert len(results) == 1
    assert results[0].subtitle_id == "6789"
    assert results[0].hearing_impaired and results[0].forced
    calls = p.session.get.call_args_list
    assert calls[0].args[0] == API + "/movies/search"
    assert calls[0].kwargs["params"] == {
        "type": "movie",
        "year": 2023,
        "searchType": "imdb",
        "imdb": "tt1234567",
    }
    assert calls[1].args[0] == API + "/subtitles"
    assert calls[1].kwargs["params"] == {"movieId": 12345, "language": "english", "limit": 100}
    assert all(
        c.kwargs["headers"] == {"X-API-Key": "test-key"} and c.kwargs["allow_redirects"] is False
        for c in calls
    )
    assert "test-key" not in repr(results)


def test_missing_key_is_an_auth_error_not_no_results():
    p = SubsourceProvider()
    p.session = MagicMock()
    with pytest.raises(ProviderAuthError, match="not configured"):
        p.search(VideoQuery(title="Some Movie"))
    p.session.get.assert_not_called()
    assert p.health_check() == (False, "API key not configured")


@pytest.mark.parametrize("status", [404, 405, 500])
def test_http_failures_reach_the_coordinator(status):
    p = _provider(MagicMock(status_code=status))
    with pytest.raises(ProviderError, match=str(status)):
        p.search(VideoQuery(title="Some Movie"))


@pytest.mark.parametrize(
    "error", [ProviderAuthError("invalid key"), ProviderRateLimitError("quota")]
)
def test_retry_session_errors_are_preserved(error):
    p = _provider(error)
    with pytest.raises(type(error)):
        p.search(VideoQuery(title="Some Movie"))


@pytest.mark.parametrize(
    "payload", [{"subs": []}, {"success": False, "data": []}, {"success": True, "data": {}}]
)
def test_schema_errors_do_not_count_as_empty_results(payload):
    p = _provider(MagicMock(status_code=200, json=lambda: payload))
    with pytest.raises(ProviderError, match="invalid response"):
        p.search(VideoQuery(title="Some Movie"))


def test_imdb_miss_falls_back_to_text_and_checks_identity():
    p = _provider(_response([]), _response([dict(MOVIE, imdbId="tt9999999"), MOVIE]), _response([]))
    assert p.search(VideoQuery(title="Some Movie", imdb_id="tt1234567")) == []
    assert p.session.get.call_args_list[1].kwargs["params"]["searchType"] == "text"
    assert p.session.get.call_args_list[2].kwargs["params"]["movieId"] == 12345


def test_title_search_does_not_select_a_remake_or_sequel():
    p = _provider(_response([dict(MOVIE, releaseYear=2024), dict(MOVIE, title="Some Movie 2")]))
    assert p.search(VideoQuery(title="Some Movie", year=2023)) == []
    assert p.session.get.call_count == 1


def test_language_filter_applies_to_each_response():
    p = _provider(
        _response([MOVIE]),
        _response([dict(SUBTITLE, language="german")]),
        _response([dict(SUBTITLE, language="german")]),
    )
    results = p.search(VideoQuery(title="Some Movie", languages=["en", "de"]))
    assert [r.language for r in results] == ["de"]


def test_season_pack_download_selects_the_requested_episode():
    movie = dict(MOVIE, type="series", season=2, title="Some Show")
    subs = [
        dict(SUBTITLE, releaseInfo=["Some.Show.S02"]),
        dict(SUBTITLE, releaseInfo=["Some.Show.S02E09"]),
    ]
    p = _provider(_response([movie]), _response(subs))
    results = p.search(VideoQuery(series_title="Some Show", season=2, episode=3))
    assert len(results) == 1
    archive = _zip([("Some.Show.S02E01.srt", b"wrong"), ("Some.Show.S02E03.ass", b"right")])
    with patch("providers.subsource._stream_download", return_value=archive) as download:
        assert p.download(results[0]) == b"right"
    assert results[0].format.value == "ass"
    assert download.call_args.kwargs["allow_redirects"] is False
    assert download.call_args.kwargs["headers"] == {"X-API-Key": "test-key"}
    assert download.call_args.args[1] == API + "/subtitles/6789/download"


def test_wrong_archive_episode_is_rejected_even_for_a_single_file():
    movie = dict(MOVIE, type="series", season=2, title="Some Show")
    p = _provider(_response([movie]), _response([dict(SUBTITLE, releaseInfo=["Some.Show.S02E03"])]))
    result = p.search(VideoQuery(series_title="Some Show", season=2, episode=3))[0]
    with (
        patch(
            "providers.subsource._stream_download",
            return_value=_zip([("Some.Show.S02E01.srt", b"wrong")]),
        ),
        pytest.raises(ProviderError, match="different episode"),
    ):
        p.download(result)


def test_html_is_never_returned_as_a_subtitle():
    p = _provider(_response([MOVIE]), _response([SUBTITLE]))
    result = p.search(VideoQuery(title="Some Movie"))[0]
    with (
        patch("providers.subsource._stream_download", return_value=b"<html>Login</html>"),
        pytest.raises(ProviderError, match="ZIP"),
    ):
        p.download(result)


def test_key_is_exposed_as_a_required_password_field_and_masked():
    from config_settings import Settings, UISettings
    from providers.manager_config_mixin import ConfigResolvingMixin

    settings = Settings(ui=UISettings(subsource_api_key="test-key"))
    manager = ConfigResolvingMixin()
    manager.settings = settings
    assert manager._get_provider_config("subsource") == {"api_key": "test-key"}
    assert settings.providers.subsource_api_key == "test-key"
    assert settings.get_safe_config()["subsource_api_key"] == "***configured***"
    assert SubsourceProvider.config_fields == [
        {"key": "subsource_api_key", "label": "API Key", "type": "password", "required": True}
    ]


def test_saving_the_key_encrypts_masks_and_reloads_the_provider(client, monkeypatch):
    from config import get_settings
    from config_crypto import is_encrypted
    from db.models.core import ConfigEntry
    from extensions import db

    invalidate = MagicMock()
    monkeypatch.setattr("providers.invalidate_manager", invalidate)
    response = client.put("/api/v1/config", json={"subsource_api_key": " test-key "})
    assert response.status_code == 200
    assert response.get_json()["config"]["subsource_api_key"] == "***configured***"
    invalidate.assert_called_once()
    assert get_settings().subsource_api_key == "test-key"
    stored = db.session.get(ConfigEntry, "subsource_api_key")
    assert is_encrypted(stored.value)
    assert "test-key" not in stored.value
