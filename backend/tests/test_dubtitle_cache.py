"""Tests for dubtitle detection persistence/cache (roadmap A4 / issue #146)."""

from __future__ import annotations

import os

from services.dubtitle import cache as dub_cache


def _make_video(tmp_path):
    p = tmp_path / "ep.mkv"
    p.write_bytes(b"\x00" * 64)
    return str(p)


class TestDubtitleCacheRoundtrip:
    def test_store_then_get(self, app_ctx, tmp_path):
        video = _make_video(tmp_path)
        payload = {"dubtitle_sub_index": 2, "method": "tier1", "candidates": []}
        dub_cache.store_detection(video, payload)
        got = dub_cache.get_cached_detection(video)
        assert got is not None
        assert got["dubtitle_sub_index"] == 2
        assert got["method"] == "tier1"

    def test_miss_for_unknown_file(self, app_ctx, tmp_path):
        assert dub_cache.get_cached_detection(str(tmp_path / "nope.mkv")) is None

    def test_mtime_change_invalidates(self, app_ctx, tmp_path):
        video = _make_video(tmp_path)
        dub_cache.store_detection(video, {"dubtitle_sub_index": 0, "method": "tier1"})
        assert dub_cache.get_cached_detection(video) is not None
        # Bump mtime → cache stale → miss
        os.utime(video, (1, 1))
        assert dub_cache.get_cached_detection(video) is None

    def test_cached_wrapper_uses_cache(self, app_ctx, tmp_path, monkeypatch):
        video = _make_video(tmp_path)
        dub_cache.store_detection(video, {"dubtitle_sub_index": 1, "method": "tier1"})

        # detect_dubtitle must NOT be called on a fresh cache hit.
        import services.dubtitle.detector as det

        def _boom(*a, **k):
            raise AssertionError("detect_dubtitle should not run on cache hit")

        monkeypatch.setattr(det, "detect_dubtitle", _boom)
        out = dub_cache.detect_dubtitle_cached(video)
        assert out["dubtitle_sub_index"] == 1

    def test_force_bypasses_cache(self, app_ctx, tmp_path, monkeypatch):
        video = _make_video(tmp_path)
        dub_cache.store_detection(video, {"dubtitle_sub_index": 9, "method": "tier1"})

        from services.dubtitle.detector import DubtitleDetectionResult

        monkeypatch.setattr(
            "services.dubtitle.detector.detect_dubtitle",
            lambda *a, **k: DubtitleDetectionResult(method="tier1", dubtitle_sub_index=3),
        )
        out = dub_cache.detect_dubtitle_cached(video, force=True)
        assert out["dubtitle_sub_index"] == 3
        # and the forced result was persisted
        assert dub_cache.get_cached_detection(video)["dubtitle_sub_index"] == 3


class TestMigrationCreatesTable:
    def test_table_exists(self, app_ctx):
        from sqlalchemy import inspect

        from extensions import db

        assert "dubtitle_detections" in inspect(db.engine).get_table_names()
