"""Log noise measured on prod (36 769 of 63 000 lines in two days) — L1, L2."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
import requests


class TestSourceSubtitleLinesAreDebug:
    """L1: "Found … source subtitle" ran per episode per scan at INFO."""

    def test_external_source_hit_is_not_info(self, tmp_path, monkeypatch, caplog):
        import translator._helpers as helpers

        mkv = tmp_path / "Show.S01E01.mkv"
        mkv.write_bytes(b"")
        (tmp_path / "Show.S01E01.en.srt").write_text("1\n", encoding="utf-8")
        monkeypatch.setattr(
            helpers,
            "get_settings",
            lambda: MagicMock(get_source_patterns=lambda fmt: [f".en.{fmt}"]),
        )
        caplog.set_level(logging.DEBUG, logger=helpers.logger.name)

        assert helpers.find_external_source_sub(str(mkv))

        hits = [r for r in caplog.records if "Found external source subtitle" in r.getMessage()]
        assert hits and all(r.levelno == logging.DEBUG for r in hits)

    def test_preferred_source_hit_is_not_info(self, app_ctx, tmp_path, caplog):
        import translator._helpers as helpers

        mkv = tmp_path / "Show.S01E01.mkv"
        mkv.write_bytes(b"")
        (tmp_path / "Show.S01E01.en.srt").write_text("1\n", encoding="utf-8")
        caplog.set_level(logging.DEBUG, logger=helpers.logger.name)

        path, lang = helpers.find_any_source_sub(str(mkv), target_language="de")

        assert lang == "en"
        hits = [r for r in caplog.records if "Found preferred source subtitle" in r.getMessage()]
        assert hits and all(r.levelno == logging.DEBUG for r in hits)


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(
        f"{status} Client Error: Not Found for url: https://x", response=response
    )


class TestProviderSideDownloadFailuresAreWarnings:
    """L2: a provider's 404 on a download is the provider's problem, not ours."""

    def _download(self, exc):
        from providers.download_manager import download_subtitle

        provider = MagicMock()
        provider.download.side_effect = exc
        breaker = MagicMock()
        breaker.allow_request.return_value = True
        result = MagicMock(provider_name="jimaku", subtitle_id="1", content=None)
        ret = download_subtitle({"jimaku": provider}, {"jimaku": breaker}, lambda n: True, result)
        return ret, breaker

    @pytest.mark.parametrize(
        "exc",
        [
            _http_error(404),
            _http_error(429),
            _http_error(503),
            requests.Timeout("read timed out"),
        ],
    )
    def test_provider_side_failure_is_warning(self, exc, caplog):
        caplog.set_level(logging.DEBUG, logger="providers.download_manager")

        ret, breaker = self._download(exc)

        assert ret is None
        breaker.record_failure.assert_called_once()
        records = [r for r in caplog.records if "Download from jimaku failed" in r.getMessage()]
        assert [r.levelno for r in records] == [logging.WARNING]

    def test_unexpected_exception_stays_error(self, caplog):
        caplog.set_level(logging.DEBUG, logger="providers.download_manager")

        self._download(KeyError("parser bug"))

        records = [r for r in caplog.records if "Download from jimaku failed" in r.getMessage()]
        assert [r.levelno for r in records] == [logging.ERROR]
