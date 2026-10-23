"""A 406 for a file OpenSubtitles no longer has is not the daily quota.

OpenSubtitles answers both with HTTP 406. The quota body carries
``remaining`` and ``reset_time_utc``; the missing-file body is only
``{"message": "Invalid file_id"}``. Reading the second as the first stopped
every OpenSubtitles download until midnight UTC: prod 1.17.0-rc.12, a repair
pass halted on a deleted subtitle with 974 of 1000 VIP downloads left.
"""

from __future__ import annotations

import pytest

from providers.base import ProviderError, ProviderRateLimitError, SubtitleResult
from providers.opensubtitles import OpenSubtitlesProvider


class _Resp:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def _provider(body: dict) -> OpenSubtitlesProvider:
    provider = OpenSubtitlesProvider(api_key="k")
    provider.session = object()  # download() only checks it is set
    provider._request_download_link = lambda _file_id: _Resp(406, body)
    return provider


def _result() -> SubtitleResult:
    return SubtitleResult(
        provider_name="opensubtitles",
        subtitle_id="9682460",
        language="en",
        provider_data={"file_id": "9682460"},
    )


def test_a_missing_file_fails_alone():
    provider = _provider({"message": "Invalid file_id"})
    with pytest.raises(ProviderError) as exc:
        provider.download(_result())
    assert not isinstance(exc.value, ProviderRateLimitError)
    assert "Invalid file_id" in str(exc.value)


def test_the_quota_body_still_reads_as_the_quota():
    provider = _provider(
        {
            "requests": 1000,
            "remaining": 0,
            "message": "You have downloaded your allowed 1000 subtitles for 24h",
            "reset_time_utc": "2026-10-23T23:59:58.000Z",
        }
    )
    with pytest.raises(ProviderRateLimitError) as exc:
        provider.download(_result())
    assert exc.value.reset_at is not None


def test_an_unreadable_406_stays_the_quota():
    provider = _provider({})
    with pytest.raises(ProviderRateLimitError):
        provider.download(_result())
