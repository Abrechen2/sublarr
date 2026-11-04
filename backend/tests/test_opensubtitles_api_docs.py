"""OpenSubtitles REST v1 as documented (https://opensubtitles.stoplight.io/docs/opensubtitles-api)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from providers.base import ProviderRateLimitError, SubtitleResult, VideoQuery
from providers.opensubtitles import OpenSubtitlesProvider


def _provider():
    provider = OpenSubtitlesProvider(api_key="k", username="u", password="p")
    provider.session = MagicMock()
    provider.session.headers = {}
    return provider


def test_an_episode_search_sends_the_series_as_parent_imdb_id():
    provider = _provider()
    provider._fetch_and_parse = MagicMock(return_value=[])
    provider.search(
        VideoQuery(
            series_title="Frieren", imdb_id="tt22248376", season=1, episode=3, languages=["en"]
        )
    )
    params = provider._fetch_and_parse.call_args.args[0]
    assert params["parent_imdb_id"] == "22248376" and "imdb_id" not in params


def test_a_movie_search_keeps_imdb_id():
    provider = _provider()
    provider._fetch_and_parse = MagicMock(return_value=[])
    provider.search(VideoQuery(title="Akira", imdb_id="tt0094625", languages=["en"]))
    assert provider._fetch_and_parse.call_args.args[0]["imdb_id"] == "0094625"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("vip-api.opensubtitles.com", "https://vip-api.opensubtitles.com/api/v1"),
        ("evil.example.com", "https://api.opensubtitles.com/api/v1"),
        ("", "https://api.opensubtitles.com/api/v1"),
    ],
)
def test_login_moves_to_the_accounts_host(base_url, expected):
    provider = _provider()
    provider.session.post.return_value = MagicMock(
        status_code=200, json=MagicMock(return_value={"token": "t", "base_url": base_url})
    )
    assert provider._login()
    assert provider._api_base == expected


def _download_response(remaining, reset):
    return MagicMock(
        status_code=200,
        json=MagicMock(
            return_value={
                "link": "https://www.opensubtitles.com/download/x/sub.srt",
                "file_name": "sub.srt",
                "remaining": remaining,
                "reset_time_utc": reset,
            }
        ),
    )


def test_the_last_download_of_the_quota_blocks_the_next(monkeypatch):
    provider = _provider()
    reset = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    provider.session.post.return_value = _download_response(0, reset)
    monkeypatch.setattr("providers.opensubtitles._stream_download", lambda *a, **k: b"1\n")
    result = SubtitleResult(
        provider_name="opensubtitles", subtitle_id="1", language="en", provider_data={"file_id": 1}
    )
    assert provider.download(result) == b"1\n"
    with pytest.raises(ProviderRateLimitError):
        provider.download(result)
    assert provider.session.post.call_count == 1  # the second never asked


def test_quota_left_does_not_block(monkeypatch):
    provider = _provider()
    provider.session.post.return_value = _download_response(5, "2099-01-01T00:00:00Z")
    monkeypatch.setattr("providers.opensubtitles._stream_download", lambda *a, **k: b"1\n")
    result = SubtitleResult(
        provider_name="opensubtitles", subtitle_id="1", language="en", provider_data={"file_id": 1}
    )
    provider.download(result)
    provider.download(result)
    assert provider.session.post.call_count == 2
