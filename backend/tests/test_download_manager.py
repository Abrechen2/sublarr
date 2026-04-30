"""Tests for providers/download_manager module.

Covers: _stream_download, download_subtitle, search_and_download_best,
save_subtitle (partial — skips disk I/O heavy parts).
"""

from unittest.mock import MagicMock, patch

import pytest

from providers.download_manager import (
    _MAX_SUBTITLE_SIZE,
    _stream_download,
    download_subtitle,
    search_and_download_best,
)

# ---------------------------------------------------------------------------
# _stream_download
# ---------------------------------------------------------------------------


class TestStreamDownload:
    def _make_response(self, chunks, content_length=None, status_code=200):
        """Build a mock streaming response."""
        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = {}
        if content_length is not None:
            resp.headers["Content-Length"] = str(content_length)
        resp.iter_content.return_value = iter(chunks)
        resp.raise_for_status.return_value = None
        # Context manager support
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_successful_download(self):
        session = MagicMock()
        resp = self._make_response([b"hello", b" world"], content_length=11)
        session.get.return_value = resp

        result = _stream_download(session, "https://example.com/sub.srt")
        assert result == b"hello world"

    def test_content_length_exceeds_limit(self):
        session = MagicMock()
        resp = self._make_response([], content_length=_MAX_SUBTITLE_SIZE + 1)
        session.get.return_value = resp

        with pytest.raises(RuntimeError, match="too large"):
            _stream_download(session, "https://example.com/big.srt")

    def test_streaming_exceeds_limit(self):
        """Actual content exceeds limit even if Content-Length is absent."""
        session = MagicMock()
        # Generate chunks totaling > _MAX_SUBTITLE_SIZE
        big_chunk = b"x" * (_MAX_SUBTITLE_SIZE + 1)
        resp = self._make_response([big_chunk])
        session.get.return_value = resp

        with pytest.raises(RuntimeError, match="exceeded size limit"):
            _stream_download(session, "https://example.com/big.srt")

    def test_non_integer_content_length(self):
        """Non-integer Content-Length is ignored (proceed with streaming)."""
        session = MagicMock()
        resp = self._make_response([b"data"], content_length="invalid")
        resp.headers["Content-Length"] = "invalid"
        session.get.return_value = resp

        result = _stream_download(session, "https://example.com/sub.srt")
        assert result == b"data"

    def test_no_content_length_header(self):
        """Missing Content-Length -> proceed with streaming check."""
        session = MagicMock()
        resp = self._make_response([b"content"])
        session.get.return_value = resp

        result = _stream_download(session, "https://example.com/sub.srt")
        assert result == b"content"

    def test_empty_response(self):
        session = MagicMock()
        resp = self._make_response([], content_length=0)
        session.get.return_value = resp

        result = _stream_download(session, "https://example.com/empty.srt")
        assert result == b""


# ---------------------------------------------------------------------------
# download_subtitle
# ---------------------------------------------------------------------------


class TestDownloadSubtitle:
    def _make_result(self, provider_name="test_provider"):
        result = MagicMock()
        result.provider_name = provider_name
        result.content = None
        return result

    def test_provider_not_found(self):
        result = self._make_result("missing")
        ret = download_subtitle({}, {}, lambda x: True, result)
        assert ret is None

    def test_rate_limited(self):
        provider = MagicMock()
        result = self._make_result("test")
        rate_checker = MagicMock(return_value=False)

        ret = download_subtitle({"test": provider}, {}, rate_checker, result)
        assert ret is None
        provider.download.assert_not_called()

    def test_successful_download(self):
        provider = MagicMock()
        provider.download.return_value = b"subtitle content"
        result = self._make_result("test")

        ret = download_subtitle({"test": provider}, {}, lambda x: True, result)
        assert ret == b"subtitle content"
        assert result.content == b"subtitle content"

    def test_download_exception(self):
        provider = MagicMock()
        provider.download.side_effect = Exception("network error")
        result = self._make_result("test")

        ret = download_subtitle({"test": provider}, {}, lambda x: True, result)
        assert ret is None


# ---------------------------------------------------------------------------
# search_and_download_best
# ---------------------------------------------------------------------------


class TestSearchAndDownloadBest:
    def test_no_results(self):
        search_fn = MagicMock(return_value=[])
        download_fn = MagicMock()
        stats_fn = MagicMock()

        ret = search_and_download_best(search_fn, download_fn, stats_fn, "query")
        assert ret is None
        download_fn.assert_not_called()

    def test_first_result_downloads(self):
        result = MagicMock()
        result.provider_name = "test"
        result.score = 85
        result.subtitle_id = "sub1"

        search_fn = MagicMock(return_value=[result])
        download_fn = MagicMock(return_value=b"content")
        stats_fn = MagicMock()

        with patch("providers.reranker.apply_auto_reranking"):
            ret = search_and_download_best(search_fn, download_fn, stats_fn, "query")

        assert ret == result
        stats_fn.assert_called_once_with("test", success=True, score=85)

    def test_first_fails_second_succeeds(self):
        result1 = MagicMock(provider_name="p1", score=90, subtitle_id="s1")
        result2 = MagicMock(provider_name="p2", score=80, subtitle_id="s2")

        search_fn = MagicMock(return_value=[result1, result2])
        download_fn = MagicMock(side_effect=[None, b"content"])
        stats_fn = MagicMock()

        with patch("providers.reranker.apply_auto_reranking"):
            ret = search_and_download_best(search_fn, download_fn, stats_fn, "query")

        assert ret == result2
        assert stats_fn.call_count == 2

    def test_all_downloads_fail(self):
        result1 = MagicMock(provider_name="p1", score=90, subtitle_id="s1")
        result2 = MagicMock(provider_name="p2", score=80, subtitle_id="s2")

        search_fn = MagicMock(return_value=[result1, result2])
        download_fn = MagicMock(return_value=None)
        stats_fn = MagicMock()

        ret = search_and_download_best(search_fn, download_fn, stats_fn, "query")
        assert ret is None

    def test_download_raises_exception(self):
        result = MagicMock(provider_name="p1", score=90, subtitle_id="s1")

        search_fn = MagicMock(return_value=[result])
        download_fn = MagicMock(side_effect=Exception("fail"))
        stats_fn = MagicMock()

        ret = search_and_download_best(search_fn, download_fn, stats_fn, "query")
        assert ret is None
        stats_fn.assert_called_once_with("p1", success=False, score=0)

    def test_passes_filter_params(self):
        search_fn = MagicMock(return_value=[])
        download_fn = MagicMock()
        stats_fn = MagicMock()

        search_and_download_best(
            search_fn,
            download_fn,
            stats_fn,
            "query",
            min_score=50,
            must_contain=["720p"],
            must_not_contain=["hardcoded"],
        )

        search_fn.assert_called_once_with(
            "query",
            format_filter=None,
            min_score=50,
            must_contain=["720p"],
            must_not_contain=["hardcoded"],
        )

    def test_reranking_exception_ignored(self):
        """apply_auto_reranking failure doesn't break the flow."""
        result = MagicMock(provider_name="p1", score=90, subtitle_id="s1")

        search_fn = MagicMock(return_value=[result])
        download_fn = MagicMock(return_value=b"content")
        stats_fn = MagicMock()

        with patch(
            "providers.reranker.apply_auto_reranking",
            side_effect=Exception("rerank error"),
        ):
            ret = search_and_download_best(search_fn, download_fn, stats_fn, "query")

        assert ret == result


class TestSearchAndDownloadBestHashBlacklist:
    """Plan B3 regression: a blacklisted content hash must be honoured at
    download-time even though the (provider, subtitle_id) pre-filter passed.

    Pre-2026-04-30 the blacklist's `file_hash` column existed end-to-end
    (migration, repository, route, frontend column) but no production call
    site ever consulted it — adding a hash via the API was a no-op.
    """

    def test_blacklisted_hash_is_skipped_and_next_result_returned(self):
        result1 = MagicMock(provider_name="p1", score=90, subtitle_id="s1")
        result2 = MagicMock(provider_name="p2", score=80, subtitle_id="s2")

        search_fn = MagicMock(return_value=[result1, result2])
        download_fn = MagicMock(side_effect=[b"banned-bytes", b"good-bytes"])
        stats_fn = MagicMock()

        # Only the first result's content hash is blacklisted.
        import hashlib

        bad_hash = hashlib.sha256(b"banned-bytes").hexdigest()

        def fake_check(provider, content_hash):
            return provider == "p1" and content_hash == bad_hash

        with (
            patch("db.blacklist.is_blacklisted_by_hash", side_effect=fake_check),
            patch("providers.reranker.apply_auto_reranking"),
        ):
            ret = search_and_download_best(search_fn, download_fn, stats_fn, "query")

        assert ret == result2
        # First result downloaded but skipped — stats NOT recorded as success
        # for p1 (it isn't a usable result). Second is the real success.
        stats_fn.assert_called_once_with("p2", success=True, score=80)

    def test_blacklisted_hash_with_no_fallback_returns_none(self):
        """Single result, hash blacklisted -> caller gets None."""
        result = MagicMock(provider_name="p1", score=90, subtitle_id="s1")
        search_fn = MagicMock(return_value=[result])
        download_fn = MagicMock(return_value=b"banned")
        stats_fn = MagicMock()

        with patch("db.blacklist.is_blacklisted_by_hash", return_value=True):
            ret = search_and_download_best(search_fn, download_fn, stats_fn, "query")

        assert ret is None
        # No success/failure stats recorded — provider behaved fine, we
        # refused on policy grounds.
        stats_fn.assert_not_called()

    def test_hash_check_failure_does_not_block_download(self):
        """If the blacklist check itself raises, the download must still proceed."""
        result = MagicMock(provider_name="p1", score=90, subtitle_id="s1")
        search_fn = MagicMock(return_value=[result])
        download_fn = MagicMock(return_value=b"content")
        stats_fn = MagicMock()

        with (
            patch(
                "db.blacklist.is_blacklisted_by_hash",
                side_effect=RuntimeError("DB unavailable"),
            ),
            patch("providers.reranker.apply_auto_reranking"),
        ):
            ret = search_and_download_best(search_fn, download_fn, stats_fn, "query")

        assert ret == result
        stats_fn.assert_called_once_with("p1", success=True, score=90)
