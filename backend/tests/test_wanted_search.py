"""Unit tests for wanted_search.py — core subtitle search pipeline."""

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _make_settings(**kwargs):
    """MagicMock Settings with production-accurate attribute names."""
    s = MagicMock()
    s.wanted_adaptive_backoff_enabled = True
    s.wanted_backoff_base_hours = 1.0
    s.wanted_backoff_cap_hours = 168.0
    s.wanted_auto_translate = True
    s.target_language = "de"
    s.source_language = "en"
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def _make_wanted_item(tmp_path, target_language="de"):
    """Create a real wanted item in the test DB, return (id, mkv_path).

    Note: upsert_wanted_item does not accept source_language — that is a global
    settings concern, not stored per-item.
    """
    from db.wanted import upsert_wanted_item

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    row_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(mkv),
        target_language=target_language,
    )
    return row_id, mkv


def _make_subtitle_result(language="de", score=80, fmt_value="ass"):
    """Build a MagicMock SubtitleResult with all fields _result_to_dict accesses."""
    r = MagicMock()
    r.provider_name = "test_provider"
    r.subtitle_id = "sub123"
    r.language = language
    r.format.value = fmt_value
    r.filename = f"subtitle.{fmt_value}"
    r.release_info = "SomeGroup"
    r.score = score
    r.hearing_impaired = False
    r.matches = set()
    return r


class TestComputeRetryAfter:
    """_compute_retry_after: exponential backoff with configurable cap."""

    def test_first_search_returns_approximately_base_delay(self):
        from wanted_search import _compute_retry_after

        settings = _make_settings(wanted_backoff_base_hours=2.0, wanted_backoff_cap_hours=48.0)
        result = _compute_retry_after(search_count=1, settings=settings)
        assert result is not None
        ts = result
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        delta_hours = (ts - now).total_seconds() / 3600
        assert 1.9 <= delta_hours <= 2.1, f"Expected ~2h delay, got {delta_hours:.2f}h"

    def test_each_retry_increases_delay(self):
        from wanted_search import _compute_retry_after

        settings = _make_settings(wanted_backoff_base_hours=1.0, wanted_backoff_cap_hours=168.0)
        now = datetime.now(UTC)
        delays = []
        for count in range(1, 5):
            ts = _compute_retry_after(count, settings)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            delays.append((ts - now).total_seconds() / 3600)
        for i in range(len(delays) - 1):
            assert delays[i + 1] > delays[i], f"Delay did not increase at step {i + 1}"

    def test_cap_is_respected(self):
        from wanted_search import _compute_retry_after

        settings = _make_settings(wanted_backoff_base_hours=1.0, wanted_backoff_cap_hours=10.0)
        result = _compute_retry_after(search_count=20, settings=settings)
        ts = result
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        delay_hours = (ts - now).total_seconds() / 3600
        assert delay_hours <= 10.5, f"Cap exceeded: {delay_hours:.2f}h"

    def test_adaptive_backoff_disabled_returns_none(self):
        from wanted_search import _compute_retry_after

        settings = _make_settings(wanted_adaptive_backoff_enabled=False)
        result = _compute_retry_after(search_count=3, settings=settings)
        assert result is None, "Expected None when adaptive backoff is disabled"


class TestBuildQueryFromWanted:
    """build_query_from_wanted: metadata enrichment for provider search."""

    def test_filename_fallback_when_no_arr_client(self, monkeypatch, app_ctx):
        from wanted_search import build_query_from_wanted

        # No sonarr_series_id/radarr_movie_id → filename fallback path
        item = {
            "id": 1,
            "item_type": "episode",
            "file_path": "/media/shows/Attack on Titan S01E01.mkv",
            "target_language": "de",
            "source_language": "en",
            "sonarr_series_id": None,
            "sonarr_episode_id": None,
            "radarr_movie_id": None,
            "standalone_series_id": None,
            "standalone_movie_id": None,
            "instance_name": None,
            "season_episode": "",
            "subtitle_type": "full",
        }
        query = build_query_from_wanted(item)
        assert query is not None
        # Filename "Attack on Titan S01E01" should parse S01E01
        assert query.season == 1
        assert query.episode == 1

    def test_sonarr_api_failure_falls_back_gracefully(self, monkeypatch, app_ctx):
        """When Sonarr raises, build_query_from_wanted must not raise itself."""
        from wanted_search import build_query_from_wanted

        class BrokenSonarr:
            def get_episode_metadata(self, series_id, episode_id):
                raise ConnectionError("Sonarr unreachable")

        monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: BrokenSonarr())
        item = {
            "id": 1,
            "item_type": "episode",
            "file_path": "/media/shows/Attack on Titan S01E05.mkv",
            "target_language": "de",
            "source_language": "en",
            "sonarr_series_id": 10,
            "sonarr_episode_id": 99,
            "radarr_movie_id": None,
            "standalone_series_id": None,
            "standalone_movie_id": None,
            "instance_name": None,
            "season_episode": "",
            "subtitle_type": "full",
        }
        query = build_query_from_wanted(item)
        assert query is not None  # Must not raise

    def test_item_target_language_used_in_query(self, app_ctx):
        """Query languages list is built from item's target_language field."""
        from wanted_search import build_query_from_wanted

        item = {
            "id": 1,
            "item_type": "movie",
            "file_path": "/media/movies/Inception 2010.mkv",
            "target_language": "fr",
            "source_language": "en",
            "sonarr_series_id": None,
            "sonarr_episode_id": None,
            "radarr_movie_id": None,
            "standalone_series_id": None,
            "standalone_movie_id": None,
            "instance_name": None,
            "season_episode": "",
            "subtitle_type": "full",
        }
        query = build_query_from_wanted(item)
        assert "fr" in query.languages

    def test_forced_subtitle_type_sets_forced_only(self, app_ctx):
        """When subtitle_type is 'forced', query.forced_only must be True."""
        from wanted_search import build_query_from_wanted

        item = {
            "id": 1,
            "item_type": "episode",
            "file_path": "/media/shows/Series S01E01.mkv",
            "target_language": "de",
            "source_language": "en",
            "sonarr_series_id": None,
            "sonarr_episode_id": None,
            "radarr_movie_id": None,
            "standalone_series_id": None,
            "standalone_movie_id": None,
            "instance_name": None,
            "season_episode": "",
            "subtitle_type": "forced",
        }
        query = build_query_from_wanted(item)
        assert query.forced_only is True


class TestSearchWantedItem:
    """search_wanted_item: provider orchestration and error handling."""

    def test_missing_item_returns_error_dict(self, app_ctx):
        from wanted_search import search_wanted_item

        result = search_wanted_item(item_id=999999)
        assert isinstance(result, dict)
        assert result.get("wanted_id") == 999999
        assert "error" in result

    def test_all_providers_failing_returns_empty_results(self, app_ctx, monkeypatch, tmp_path):
        from wanted_search import search_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        mock_mgr = MagicMock()
        mock_mgr.search.side_effect = Exception("all down")
        monkeypatch.setattr("wanted_search.search.get_provider_manager", lambda: mock_mgr)

        result = search_wanted_item(item_id)
        assert result.get("wanted_id") == item_id
        assert isinstance(result.get("target_results", []), list)
        assert len(result.get("target_results", [])) == 0

    def test_results_split_into_target_and_source(self, app_ctx, monkeypatch, tmp_path):
        """Results are split into target_results and source_results lists."""
        from wanted_search import search_wanted_item

        item_id, _ = _make_wanted_item(tmp_path, target_language="de")

        de_result = _make_subtitle_result(language="de", score=80, fmt_value="ass")
        en_result = _make_subtitle_result(language="en", score=75, fmt_value="ass")
        en_result.subtitle_id = "sub456"  # distinct ID to survive dedup

        mock_mgr = MagicMock()
        # First call (target ASS) returns de, second (source ASS) returns en, rest empty
        mock_mgr.search.side_effect = [
            [de_result],
            [en_result],
            [],
            [],
        ]
        monkeypatch.setattr("wanted_search.search.get_provider_manager", lambda: mock_mgr)

        result = search_wanted_item(item_id)
        assert result.get("wanted_id") == item_id
        target = result.get("target_results", [])
        source = result.get("source_results", [])
        assert isinstance(target, list)
        assert isinstance(source, list)
        # de subtitle ends up in target_results
        assert any(r["language"] == "de" for r in target)
        # en subtitle ends up in source_results
        assert any(r["language"] == "en" for r in source)

    def test_results_are_dicts_with_score_key(self, app_ctx, monkeypatch, tmp_path):
        """search_wanted_item converts SubtitleResults to dicts via _result_to_dict."""
        from wanted_search import search_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)

        sub = _make_subtitle_result(language="de", score=90, fmt_value="ass")
        mock_mgr = MagicMock()
        mock_mgr.search.side_effect = [[sub], [], [], []]
        monkeypatch.setattr("wanted_search.search.get_provider_manager", lambda: mock_mgr)

        result = search_wanted_item(item_id)
        target = result.get("target_results", [])
        if target:
            assert isinstance(target[0], dict)
            assert "score" in target[0]
            assert "language" in target[0]
            assert "provider" in target[0]


class TestProcessWantedItem:
    """process_wanted_item: download + optional translation + DB status update."""

    def test_missing_item_returns_error_dict(self, app_ctx):
        from wanted_search import process_wanted_item

        result = process_wanted_item(item_id=999999)
        assert isinstance(result, dict)
        assert result.get("wanted_id") == 999999
        assert result.get("status") == "error"

    def test_no_provider_result_does_not_crash(self, app_ctx, monkeypatch, tmp_path):
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        mock_mgr = MagicMock()
        mock_mgr.search.return_value = []
        mock_mgr.search_and_download_best.return_value = None
        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)

        result = process_wanted_item(item_id)
        assert isinstance(result, dict)
        assert "wanted_id" in result

    def test_auto_translate_not_called_when_disabled(self, app_ctx, monkeypatch, tmp_path):
        """When wanted_auto_translate=False, _translate_external_ass must not be called."""
        import os

        from config import reload_settings
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        os.environ["SUBLARR_WANTED_AUTO_TRANSLATE"] = "false"
        reload_settings()
        try:
            translate_called = []

            def _fake_translate(*a, **kw):
                translate_called.append(True)
                return {"status": "ok"}

            # _translate_external_ass is imported lazily inside function bodies,
            # so we must patch it at the translator module level.
            monkeypatch.setattr("translator._translate_external_ass", _fake_translate)

            mock_mgr = MagicMock()
            mock_mgr.search.return_value = []
            mock_mgr.search_and_download_best.return_value = None
            monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)

            process_wanted_item(item_id)
            assert not translate_called, (
                "_translate_external_ass called despite auto_translate=False"
            )
        finally:
            os.environ.pop("SUBLARR_WANTED_AUTO_TRANSLATE", None)
            reload_settings()

    def test_file_not_on_disk_returns_failed(self, app_ctx, monkeypatch, tmp_path):
        """If the video file is missing, process_wanted_item returns status=failed."""
        from db.wanted import upsert_wanted_item
        from wanted_search import process_wanted_item

        missing_path = str(tmp_path / "nonexistent_video.mkv")
        # Do NOT create the file
        item_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=missing_path,
            target_language="de",
        )

        result = process_wanted_item(item_id)
        assert isinstance(result, dict)
        assert result.get("status") == "failed"
        assert result.get("wanted_id") == item_id


class TestSaveSubtitleReturnPathPropagated:
    """Regression tests for the save_subtitle return-path propagation contract.

    download_manager.save_subtitle rewrites the file extension when the input
    path's extension does not match the actual subtitle format (e.g. caller
    asked for ".de.ass" but the downloaded content is detected as SRT). The
    function returns the actual saved path. Callers MUST use that return value
    for downstream operations (auto-sync, NFO writing, response dict),
    otherwise auto-sync chases a non-existent ".de.ass" while the file is on
    disk as ".de.srt".

    Reproduces the production symptom observed for FateZero, FateApocrypha,
    To Your Eternity, Zombie Land Saga, To LOVE-Ru on 2026-04-15 where
    wanted_search.post_processor logged "Auto-sync skipped: subtitle path does
    not exist on disk" en masse after ffsubsync was bundled into the image.
    """

    def test_step1_target_ass_propagates_rewritten_path(self, app_ctx, monkeypatch, tmp_path):
        """Step 1 (target ASS direct): when save_subtitle rewrites .ass→.srt,
        _try_auto_sync must be called with the rewritten path, not the input."""
        from wanted_search import process_wanted_item

        item_id, mkv_path = _make_wanted_item(tmp_path)
        # Provider says ASS, but save_subtitle decides SRT after content detection
        result = _make_subtitle_result(language="de", score=80, fmt_value="ass")
        result.content = b"1\n00:00:01,000 --> 00:00:02,000\nHi\n"

        # save_subtitle rewrites the extension ass→srt and returns the new path
        def _save_rewriting(_result, output_path, series_id=None):
            base, _ = output_path.rsplit(".", 1)
            actual = f"{base}.srt"
            return actual

        mock_mgr = MagicMock()
        mock_mgr.search.return_value = []
        mock_mgr.search_and_download_best.return_value = result
        mock_mgr.save_subtitle.side_effect = _save_rewriting

        captured = {}

        def _fake_try_auto_sync(subtitle_path, video_path, settings, *, item_id, target_language):
            captured["subtitle_path"] = subtitle_path
            captured["video_path"] = video_path
            captured["item_id"] = item_id
            captured["target_language"] = target_language

        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)
        monkeypatch.setattr("wanted_search.process._try_auto_sync", _fake_try_auto_sync)
        # Prevent NFO sidecar writes from touching disk during test
        monkeypatch.setattr("nfo_export.maybe_write_nfo", lambda *a, **kw: None)

        out = process_wanted_item(item_id)

        # The CRITICAL assertion: auto-sync must be invoked with the saved path,
        # not the original .de.ass we asked for.
        assert captured.get("subtitle_path", "").endswith(".de.srt"), (
            f"Auto-sync got input path instead of save_subtitle return value: "
            f"{captured.get('subtitle_path')!r}"
        )
        assert out.get("output_path", "").endswith(".de.srt"), (
            f"Returned output_path is the stale input, not the saved path: "
            f"{out.get('output_path')!r}"
        )
