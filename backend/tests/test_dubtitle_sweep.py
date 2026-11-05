"""Tests for the scheduled dubtitle-detection sweep (roadmap A4 / issue #146)."""

from __future__ import annotations

import services.dubtitle.sweep as sweep


class TestDubtitleScanTick:
    def test_noop_when_disabled(self, monkeypatch):
        monkeypatch.setattr(
            "config.get_settings", lambda: type("S", (), {"dubtitle_detection": False})()
        )
        out = sweep.dubtitle_scan_tick()
        assert out == {"enabled": False, "processed": 0, "skipped": 0}

    def test_detects_only_ambiguous_files(self, monkeypatch):
        monkeypatch.setattr(
            "config.get_settings", lambda: type("S", (), {"dubtitle_detection": True})()
        )
        monkeypatch.setattr("config.map_path", lambda p: p)
        monkeypatch.setattr(sweep, "_candidate_file_paths", lambda lim: ["/a.mkv", "/b.mkv"])
        monkeypatch.setattr(sweep.os.path, "exists", lambda p: True)
        # /a has 2 EN tracks (ambiguous → detect), /b has 1 (skip)
        monkeypatch.setattr(
            "ass_utils.get_media_streams",
            lambda p, use_cache=True: {"_n": 2 if p == "/a.mkv" else 1},
        )
        monkeypatch.setattr(
            "services.dubtitle.detector._english_subtitle_streams",
            lambda probe: [{}] * probe["_n"],
        )
        monkeypatch.setattr("services.dubtitle.get_cached_detection", lambda p: None)
        detected = []
        monkeypatch.setattr(
            "services.dubtitle.detect_dubtitle_cached",
            lambda p, **k: detected.append((p, k)) or {"dubtitle_sub_index": 1},
        )
        out = sweep.dubtitle_scan_tick()
        assert out["processed"] == 1
        assert out["skipped"] == 1
        assert detected == [("/a.mkv", {"automated": True, "probe_data": {"_n": 2}})]

    def test_stops_at_the_next_candidate_file_when_asked(self, monkeypatch):
        """The stop arrives during the first candidate's probe.

        The tick is driven for real; the next candidate must never reach
        ffprobe because the production loop checks cancellation before each
        candidate file.
        """
        import threading

        from services.scheduler import cancellation

        monkeypatch.setattr(
            "config.get_settings", lambda: type("S", (), {"dubtitle_detection": True})()
        )
        monkeypatch.setattr("config.map_path", lambda p: p)
        monkeypatch.setattr(sweep, "_candidate_file_paths", lambda lim: ["/a.mkv", "/b.mkv"])
        monkeypatch.setattr(sweep.os.path, "exists", lambda p: True)
        monkeypatch.setattr("services.dubtitle.get_cached_detection", lambda p: None)
        monkeypatch.setattr(
            "services.dubtitle.detector._english_subtitle_streams",
            lambda probe: [{}] * probe["_n"],
        )

        event = threading.Event()
        probed: list[str] = []
        detected: list[str] = []

        def fake_probe(path, use_cache=True):
            probed.append(path)
            event.set()  # the stop arrives while the first candidate is in flight
            return {"_n": 2}

        monkeypatch.setattr("ass_utils.get_media_streams", fake_probe)
        monkeypatch.setattr(
            "services.dubtitle.detect_dubtitle_cached",
            lambda p, **k: detected.append(p) or {"dubtitle_sub_index": 1},
        )

        token = cancellation.activate(event)
        try:
            out = sweep.dubtitle_scan_tick()
        finally:
            cancellation.deactivate(token)

        assert out["processed"] == 1
        assert probed == ["/a.mkv"], (
            f"the sweep kept probing after being asked to stop: probed {probed}"
        )
        assert detected == ["/a.mkv"]

    def test_skips_fresh_cache(self, monkeypatch):
        monkeypatch.setattr(
            "config.get_settings", lambda: type("S", (), {"dubtitle_detection": True})()
        )
        monkeypatch.setattr("config.map_path", lambda p: p)
        monkeypatch.setattr(sweep, "_candidate_file_paths", lambda lim: ["/a.mkv"])
        monkeypatch.setattr(sweep.os.path, "exists", lambda p: True)
        monkeypatch.setattr("services.dubtitle.get_cached_detection", lambda p: {"cached": True})
        probed = []
        monkeypatch.setattr(
            "ass_utils.get_media_streams", lambda p, use_cache=True: probed.append(p) or {}
        )
        out = sweep.dubtitle_scan_tick()
        assert out["processed"] == 0
        assert out["skipped"] == 1
        assert probed == []  # cache hit short-circuits before probing

    def test_registered_in_scheduler(self):
        from services.scheduler import _build_default_jobs

        spec = next((j for j in _build_default_jobs() if j.id == "dubtitle_scan"), None)
        assert spec is not None
        assert spec.func is sweep.dubtitle_scan_tick


class TestSweepWalksTheWholeLibrary:
    """Every run read the same first 1,600 paths, so a library past them was
    never looked at once those were cached."""

    def test_the_next_run_starts_after_the_last_path_examined(self, app_ctx, monkeypatch):
        from db.wanted import upsert_wanted_item

        for i, p in enumerate(("/a.mkv", "/b.mkv", "/c.mkv"), 1):
            upsert_wanted_item("episode", p, sonarr_episode_id=i, target_language="de")
        monkeypatch.setattr(sweep, "_cursor", "")

        assert sweep._candidate_file_paths(2) == ["/a.mkv", "/b.mkv"]
        sweep._cursor = "/b.mkv"
        assert sweep._candidate_file_paths(2) == ["/c.mkv"]

    def test_the_cursor_wraps_after_a_short_page(self, monkeypatch):
        monkeypatch.setattr(
            "config.get_settings", lambda: type("S", (), {"dubtitle_detection": True})()
        )
        monkeypatch.setattr("config.map_path", lambda p: p)
        monkeypatch.setattr(sweep, "_cursor", "/m.mkv")
        monkeypatch.setattr(sweep, "_candidate_file_paths", lambda lim: ["/x.mkv"])
        monkeypatch.setattr(sweep.os.path, "exists", lambda p: False)

        sweep.dubtitle_scan_tick()

        assert sweep._cursor == ""

    def test_the_cursor_stops_where_the_cap_stopped(self, monkeypatch):
        monkeypatch.setattr(
            "config.get_settings", lambda: type("S", (), {"dubtitle_detection": True})()
        )
        monkeypatch.setattr("config.map_path", lambda p: p)
        monkeypatch.setattr(sweep, "_cursor", "")
        monkeypatch.setattr(sweep, "_BATCH_CAP", 1)
        monkeypatch.setattr(
            sweep, "_candidate_file_paths", lambda lim: ["/a.mkv", "/b.mkv"] * (lim // 2)
        )
        monkeypatch.setattr(sweep.os.path, "exists", lambda p: True)
        monkeypatch.setattr("ass_utils.get_media_streams", lambda p, use_cache=True: {})
        monkeypatch.setattr(
            "services.dubtitle.detector._english_subtitle_streams", lambda probe: [{}, {}]
        )
        monkeypatch.setattr("services.dubtitle.get_cached_detection", lambda p: None)
        monkeypatch.setattr("services.dubtitle.detect_dubtitle_cached", lambda p, **k: {})

        sweep.dubtitle_scan_tick()

        assert sweep._cursor == "/a.mkv"
