"""Regression tests for the 2026-05-09 standalone-mode audit fixes.

Covers the twelve findings closed in this batch:

* G1   — ``StandaloneScanner.scan_folder`` now exists as a public method.
* S1-3 — ``get_scanner()`` is a real singleton; ``_scan_lock`` is shared.
* S0-1 — ``_cleanup_stale_*`` aborts when a watched root is unreachable.
* S1-5 — ``_cleanup_stale_series`` cascades to ``wanted_items``.
* S1-2 — ``process_single_file`` episode path is NFO-first.
* S1-1 — Resolver cache uses ``db.standalone`` directly with the right arity.
* S1-6 — Filename-stub results are not cached.
* G2   — ``TMDBClient._get`` retries once on 429 / transient 5xx.
* S0-2 — ``POST /folders`` rejects forbidden system roots.
* S0-3 — Scanner detects + prunes symlink cycles.
* S1-4 — ``upsert_standalone_series`` rolls back + UPDATEs on IntegrityError.
* G3/G4 — Watcher uses a bounded executor; ``/refresh-metadata`` returns 202.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# G1 — scan_folder public method
# ---------------------------------------------------------------------------


class TestScanFolderPublicMethod:
    def test_scanner_has_public_scan_folder(self):
        from standalone.scanner import StandaloneScanner

        assert hasattr(StandaloneScanner, "scan_folder"), (
            "StandaloneScanner must expose scan_folder() so launch_folder_scan works"
        )

    def test_scan_folder_accepts_string_path(self, app_ctx, tmp_path):
        from standalone.scanner import StandaloneScanner

        scanner = StandaloneScanner()
        # Should not raise AttributeError; passes through to _scan_folder.
        # Empty dir → all-zero summary.
        result = scanner.scan_folder(str(tmp_path))
        assert result == (0, 0, 0)

    def test_scan_folder_accepts_dict(self, app_ctx, tmp_path):
        from standalone.scanner import StandaloneScanner

        scanner = StandaloneScanner()
        result = scanner.scan_folder({"path": str(tmp_path), "label": "x", "media_type": "auto"})
        assert result == (0, 0, 0)


# ---------------------------------------------------------------------------
# S1-3 — singleton + shared lock
# ---------------------------------------------------------------------------


class TestScannerSingleton:
    def test_get_scanner_returns_same_instance(self):
        import standalone.scanner as mod

        # Reset singleton so this test is hermetic
        mod._scanner_singleton = None

        a = mod.get_scanner()
        b = mod.get_scanner()
        assert a is b, "get_scanner() must memoise the singleton"

    def test_scanner_singleton_thread_safe(self):
        """Concurrent get_scanner() calls must converge on one instance."""
        import standalone.scanner as mod

        mod._scanner_singleton = None
        instances = []

        def grab():
            instances.append(mod.get_scanner())

        threads = [threading.Thread(target=grab) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        first = instances[0]
        assert all(inst is first for inst in instances), (
            "Double-checked locking lost a race — multiple scanner instances created"
        )


# ---------------------------------------------------------------------------
# S0-1 — cleanup probe before mass-delete
# ---------------------------------------------------------------------------


class TestCleanupProbe:
    def test_cleanup_aborts_when_watched_root_unreachable(self, app_ctx):
        from standalone.scanner import StandaloneScanner

        scanner = StandaloneScanner()

        with patch("db.standalone.get_watched_folders") as gwf:
            gwf.return_value = [{"id": 1, "path": "/mnt/unreachable", "enabled": True}]
            with patch("os.stat", side_effect=OSError("mount lost")):
                # Fast path returns False — cleanup must NOT touch the DB.
                assert scanner._watched_roots_reachable() is False
                # And the public cleanups bail out early returning 0.
                assert scanner._cleanup_stale_series() == 0
                assert scanner._cleanup_stale_wanted() == 0

    def test_cleanup_aborts_when_no_watched_folders(self, app_ctx):
        from standalone.scanner import StandaloneScanner

        scanner = StandaloneScanner()
        with patch("db.standalone.get_watched_folders", return_value=[]):
            assert scanner._watched_roots_reachable() is False
            assert scanner._cleanup_stale_series() == 0


# ---------------------------------------------------------------------------
# S1-5 — cleanup cascade
# ---------------------------------------------------------------------------


class TestCleanupCascade:
    def test_cleanup_stale_series_uses_cascade(self, app_ctx, tmp_path):
        from standalone.scanner import StandaloneScanner

        scanner = StandaloneScanner()

        # Force watched-roots probe to succeed so cleanup runs.
        with (
            patch.object(StandaloneScanner, "_watched_roots_reachable", return_value=True),
            patch(
                "db.standalone.get_standalone_series",
                return_value=[
                    {"id": 1, "folder_path": "/nonexistent/series-a"},
                ],
            ),
            patch("services.standalone_manager.delete_series_cascade") as mock_cascade,
        ):
            scanner._cleanup_stale_series()
            mock_cascade.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# S1-2 — process_single_file episode is NFO-first
# ---------------------------------------------------------------------------


class TestWatcherNfoFirst:
    def test_process_single_file_episode_calls_parse_series_nfo(self, app_ctx, tmp_path):
        """The watcher entry point must hit parse_series_nfo before falling
        back to the resolver — otherwise watcher events overwrite NFO IDs.
        """
        from standalone.scanner import StandaloneScanner

        # Build a minimal series tree: one episode in a Season subfolder
        series_root = tmp_path / "Anime Series"
        season_dir = series_root / "Season 1"
        season_dir.mkdir(parents=True)
        ep = season_dir / "Anime Series - S01E01.mkv"
        ep.touch()
        # Bare-minimum tvshow.nfo with a TVDB id
        nfo = series_root / "tvshow.nfo"
        nfo.write_text(
            '<?xml version="1.0"?><tvshow><title>Anime Series</title>'
            "<tvdbid>1234</tvdbid></tvshow>",
            encoding="utf-8",
        )

        scanner = StandaloneScanner()
        with patch(
            "standalone.nfo_parser.parse_series_nfo",
            wraps=__import__(
                "standalone.nfo_parser", fromlist=["parse_series_nfo"]
            ).parse_series_nfo,
        ) as spy_nfo:
            with patch.object(scanner, "_get_resolver"):
                scanner.process_single_file(str(ep))

            assert spy_nfo.called, "process_single_file episode-branch must call parse_series_nfo"


# ---------------------------------------------------------------------------
# S1-1 + S1-6 — resolver cache works + filename-stub not cached
# ---------------------------------------------------------------------------


class TestResolverCache:
    def test_set_cached_writes_via_db_standalone(self):
        from metadata import MetadataResolver

        resolver = MetadataResolver()
        with patch("db.standalone.cache_metadata") as cm:
            resolver._set_cached(
                "series:test:2024",
                {"title": "Test", "metadata_source": "tmdb", "tmdb_id": 42},
            )
            cm.assert_called_once()
            args, kwargs = cm.call_args
            assert args[0] == "series:test:2024"
            # provider, response_json, ttl_days are kwargs
            assert kwargs["provider"] == "tmdb"
            payload = json.loads(kwargs["response_json"])
            assert payload["tmdb_id"] == 42
            assert kwargs["ttl_days"] == 30

    def test_filename_stub_is_not_cached(self):
        from metadata import MetadataResolver

        resolver = MetadataResolver()
        with patch("db.standalone.cache_metadata") as cm:
            resolver._set_cached(
                "series:test:2024",
                {"title": "Test", "metadata_source": "filename", "tmdb_id": None},
            )
            cm.assert_not_called()

    def test_get_cached_returns_parsed_json(self):
        from metadata import MetadataResolver

        resolver = MetadataResolver()
        with patch(
            "db.standalone.get_cached_metadata",
            return_value={"response_json": '{"title": "X", "tmdb_id": 42}'},
        ):
            data = resolver._get_cached("series:test:2024")
            assert data == {"title": "X", "tmdb_id": 42}

    def test_get_cached_handles_invalid_json(self):
        from metadata import MetadataResolver

        resolver = MetadataResolver()
        with patch(
            "db.standalone.get_cached_metadata",
            return_value={"response_json": "{not valid json"},
        ):
            assert resolver._get_cached("k") is None


# ---------------------------------------------------------------------------
# G2 — TMDB 429 retry
# ---------------------------------------------------------------------------


class TestTMDBRetry:
    def test_tmdb_get_retries_once_on_429(self):
        from metadata.tmdb_client import TMDBClient

        client = TMDBClient("test-key")
        # Two responses: 429 then 200
        rate_limited = MagicMock(status_code=429, headers={"Retry-After": "0.1"})
        success = MagicMock(status_code=200)
        success.json.return_value = {"results": [{"id": 1}]}
        success.raise_for_status.return_value = None

        with patch.object(client.session, "get", side_effect=[rate_limited, success]) as mock_get:
            with patch("time.sleep") as mock_sleep:  # speed up test
                result = client._get("/3/search/tv", params={"query": "x"})
            assert result == {"results": [{"id": 1}]}
            assert mock_get.call_count == 2
            mock_sleep.assert_called()

    def test_tmdb_parse_retry_after_caps_at_max(self):
        from metadata.tmdb_client import MAX_RETRY_AFTER_SECONDS, TMDBClient

        # A 600s Retry-After header must be capped.
        assert TMDBClient._parse_retry_after("600") == float(MAX_RETRY_AFTER_SECONDS)
        # Bad input falls back to 1.0
        assert TMDBClient._parse_retry_after(None) == 1.0
        assert TMDBClient._parse_retry_after("garbage") == 1.0
        assert TMDBClient._parse_retry_after("-5") == 1.0


# ---------------------------------------------------------------------------
# S0-2 — POST /folders boundary
# ---------------------------------------------------------------------------


class TestFolderBoundary:
    def test_validate_rejects_etc(self):
        from routes.standalone.folders import _validate_watched_folder_path

        assert _validate_watched_folder_path("/etc") is not None

    def test_validate_rejects_root(self):
        from routes.standalone.folders import _validate_watched_folder_path

        assert _validate_watched_folder_path("/") is not None

    def test_validate_rejects_proc(self):
        from routes.standalone.folders import _validate_watched_folder_path

        assert _validate_watched_folder_path("/proc") is not None

    def test_validate_accepts_real_dir(self, tmp_path):
        from routes.standalone.folders import _validate_watched_folder_path

        assert _validate_watched_folder_path(str(tmp_path)) is None

    def test_validate_rejects_missing_dir(self):
        from routes.standalone.folders import _validate_watched_folder_path

        assert _validate_watched_folder_path("/nonexistent/path/xyz") is not None


# ---------------------------------------------------------------------------
# S0-3 — symlink cycle pruning
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not hasattr(os, "symlink") or os.name == "nt",
    reason="Symlink cycle test requires POSIX symlinks",
)
class TestSymlinkCyclePruning:
    def test_cycle_pruning_does_not_hang(self, app_ctx, tmp_path):
        """A symlink that points back to its parent must not cause an
        infinite os.walk."""
        from standalone.scanner import StandaloneScanner

        # Build dir + cycle
        nested = tmp_path / "level1"
        nested.mkdir()
        cycle_link = nested / "back"
        os.symlink(str(tmp_path), str(cycle_link))

        scanner = StandaloneScanner()
        # If pruning is broken this hangs forever; pytest's default timeout
        # would catch that, but we also trust the loop pruning to bail.
        result = scanner._scan_folder({"path": str(tmp_path), "label": "", "media_type": "auto"})
        assert result == (0, 0, 0)


# ---------------------------------------------------------------------------
# S1-4 — UPSERT IntegrityError → rollback + update
# ---------------------------------------------------------------------------


class TestUpsertRace:
    def test_upsert_series_handles_integrity_error(self, app_ctx, tmp_path):
        from db.models.standalone import StandaloneSeries
        from db.repositories.standalone import StandaloneRepository
        from extensions import db

        # Clean any prior row
        db.session.query(StandaloneSeries).filter_by(folder_path=str(tmp_path)).delete()
        db.session.commit()

        repo = StandaloneRepository()
        # First insert wins
        first = repo.upsert_standalone_series(
            title="A",
            folder_path=str(tmp_path),
            tmdb_id=11,
            metadata_source="tmdb",
        )
        # Second call with different title must not raise; treated as UPDATE
        second = repo.upsert_standalone_series(
            title="B",
            folder_path=str(tmp_path),
            tmdb_id=22,
            metadata_source="tmdb",
        )
        assert first["id"] == second["id"]
        assert second["title"] == "B"
        assert second["tmdb_id"] == 22

        # Cleanup
        db.session.query(StandaloneSeries).filter_by(folder_path=str(tmp_path)).delete()
        db.session.commit()


# ---------------------------------------------------------------------------
# G3 — watcher bounded executor
# ---------------------------------------------------------------------------


class TestWatcherBoundedExecutor:
    def test_watcher_uses_threadpool(self):
        """The MediaFileWatcher must own a bounded ThreadPoolExecutor for
        stability checks (regression: previously each Timer thread did its
        own time.sleep, so 100 files = 100 concurrent threads)."""
        from concurrent.futures import ThreadPoolExecutor

        from standalone.watcher import MediaFileWatcher

        watcher = MediaFileWatcher(on_new_file=lambda p: None, debounce_seconds=0.01)
        try:
            assert isinstance(watcher._stability_pool, ThreadPoolExecutor)
            assert watcher._stability_pool._max_workers == 4
        finally:
            watcher.shutdown()


# ---------------------------------------------------------------------------
# G4 — /refresh-metadata async
# ---------------------------------------------------------------------------


class TestRefreshMetadataAsync:
    def test_refresh_route_returns_202(self, app_ctx):
        """The route must schedule the refresh asynchronously and return
        202 Accepted instead of blocking the worker thread."""
        from db.models.standalone import StandaloneSeries
        from extensions import db

        # Seed a series row to refresh
        series = StandaloneSeries(
            title="Async Test",
            folder_path="/tmp/async-refresh-test",
            metadata_source="filename",
            created_at=db.func.now(),
            updated_at=db.func.now(),
        )
        db.session.add(series)
        db.session.commit()
        series_id = series.id

        try:
            client = app_ctx.test_client()
            with patch("services.standalone_manager.refresh_series_metadata_async") as mock_async:
                resp = client.post(f"/api/v1/standalone/series/{series_id}/refresh-metadata")
            assert resp.status_code == 202, f"Expected 202 Accepted, got {resp.status_code}"
            mock_async.assert_called_once()
        finally:
            db.session.query(StandaloneSeries).filter_by(id=series_id).delete()
            db.session.commit()
