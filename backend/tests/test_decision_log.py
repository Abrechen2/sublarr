"""Tests for the decision log (decision_log.py + persistence + API).

Covers:
- Collector unit behaviour (contextvar lifecycle, no-op when inactive,
  provider facts, filter stages, selection, truncation).
- Filter-stage recording through the real _finalise_search_results pipeline.
- record_subtitle_download attaching the active snapshot to the download row.
- GET /history/<id>/decision and GET /wanted/<id>/decision routes.
"""

from __future__ import annotations

import json

import pytest

import decision_log
from providers.base import SubtitleFormat, SubtitleResult, VideoQuery


@pytest.fixture(autouse=True)
def _reset_decision_log():
    """Every test starts and ends without an active log."""
    decision_log.finish()
    yield
    decision_log.finish()


def _make_result(
    provider: str = "jimaku",
    subtitle_id: str = "sub-1",
    language: str = "de",
    fmt: SubtitleFormat = SubtitleFormat.ASS,
    score: int = 100,
    release_info: str = "",
) -> SubtitleResult:
    return SubtitleResult(
        provider_name=provider,
        subtitle_id=subtitle_id,
        language=language,
        format=fmt,
        filename=f"{subtitle_id}.{fmt.value}",
        score=score,
        release_info=release_info,
        hearing_impaired=False,
        forced=False,
        provider_data={},
    )


class TestCollector:
    def test_inactive_helpers_are_noops(self):
        # No active log — none of these may raise.
        decision_log.set_step("target_ass_direct")
        decision_log.search_started(["de"], SubtitleFormat.ASS)
        decision_log.provider_searched("jimaku", 5, 120.0)
        decision_log.filter_stage("language", 2, 3, [])
        decision_log.selected(_make_result())
        assert decision_log.active() is None
        assert decision_log.snapshot_json() is None

    def test_start_finish_lifecycle(self):
        log = decision_log.start({"id": 7, "file_path": "/x.mkv", "target_language": "de"})
        assert decision_log.active() is log
        decision_log.finish()
        assert decision_log.active() is None

    def test_search_and_provider_facts(self):
        decision_log.start({"id": 1})
        decision_log.set_step("target_ass_direct")
        decision_log.search_started(["de"], SubtitleFormat.ASS, 0)
        decision_log.provider_skipped("opensubtitles", "circuit_open")
        decision_log.provider_searched("jimaku", 2, 340.2)
        decision_log.provider_failed("subdl", "timeout")
        decision_log.search_finished(2, 1)

        d = decision_log.active().to_dict()
        assert len(d["searches"]) == 1
        search = d["searches"][0]
        assert search["step"] == "target_ass_direct"
        assert search["format"] == "ass"
        assert search["results_total"] == 2
        assert search["results_final"] == 1
        statuses = {p["name"]: p["status"] for p in search["providers"]}
        assert statuses == {"opensubtitles": "skipped", "jimaku": "ok", "subdl": "timeout"}
        assert search["providers"][1]["hits"] == 2
        assert search["providers"][1]["elapsed_ms"] == 340

    def test_filter_stage_records_samples_and_skips_empty(self):
        decision_log.start({"id": 1})
        decision_log.search_started(["de"], None, 0)
        rejected = [_make_result(language="en", score=10)]
        decision_log.filter_stage("language", 1, 4, rejected, wanted=["de"])
        decision_log.filter_stage("format", 0, 4, [])  # removed=0 -> not recorded

        search = decision_log.active().to_dict()["searches"][0]
        assert len(search["filters"]) == 1
        stage = search["filters"][0]
        assert stage["stage"] == "language"
        assert stage["removed"] == 1
        assert stage["remaining"] == 4
        assert stage["wanted"] == ["de"]
        assert stage["rejected"][0]["language"] == "en"

    def test_selected_and_outcome(self):
        decision_log.start({"id": 1})
        decision_log.set_step("target_ass_direct")
        decision_log.search_started(["de"], SubtitleFormat.ASS, 0)
        result = _make_result(score=97)
        result.score_breakdown = {"series": 50, "episode": 30, "format_bonus": 17}
        decision_log.download_attempt("jimaku", "sub-1", "selected")
        decision_log.selected(result)
        decision_log.set_outcome("found", output_path="/media/x.de.ass")

        d = decision_log.active().to_dict()
        assert d["final"]["status"] == "found"
        assert d["final"]["provider"] == "jimaku"
        assert d["final"]["score"] == 97
        assert d["final"]["score_breakdown"]["format_bonus"] == 17
        assert d["final"]["output_path"] == "/media/x.de.ass"
        assert d["searches"][0]["download_attempts"][0]["status"] == "selected"

    def test_oversize_payload_drops_rejected_samples(self):
        decision_log.start({"id": 1})
        decision_log.search_started(["de"], None, 0)
        big = [_make_result(subtitle_id=f"s{i}", release_info="x" * 120) for i in range(25)]
        # ~60 stages x 25 samples x ~250 bytes -> well past MAX_JSON_BYTES raw
        for i in range(60):
            decision_log.filter_stage(f"stage_{i}", 25, 0, big)
        raw = json.dumps(decision_log.active().to_dict(), default=str)
        assert len(raw) > decision_log.MAX_JSON_BYTES

        out = json.loads(decision_log.active().to_json())
        assert out.get("truncated") is True
        for search in out["searches"]:
            for stage in search["filters"]:
                assert "rejected" not in stage
        # Truncation must not mutate the live collector (repeatable snapshots).
        assert "rejected" in decision_log.active().searches[0]["filters"][0]

    def test_helpers_swallow_collector_errors(self):
        decision_log.start({"id": 1})
        # No search entry open — selected() still must not raise even when
        # handed a broken object.
        decision_log.selected(object())  # missing attrs -> AttributeError inside
        decision_log.filter_stage("x", 1, 0, [object()])


class TestFinalisePipeline:
    """Filter stages are recorded by the real _finalise_search_results."""

    def _finalise(self, monkeypatch, results, query, **kwargs):
        from providers import ProviderManager

        monkeypatch.setattr("db.blacklist.is_blacklisted", lambda *a, **kw: False)
        manager = ProviderManager.__new__(ProviderManager)  # no heavy __init__
        return manager._finalise_search_results(
            results,
            query,
            kwargs.get("format_filter"),
            kwargs.get("min_score", 0),
            kwargs.get("must_contain"),
            kwargs.get("must_not_contain"),
        )

    def test_language_and_format_stages_recorded(self, app_ctx, monkeypatch):
        decision_log.start({"id": 1})
        decision_log.search_started(["de"], SubtitleFormat.ASS, 0)
        results = [
            _make_result(subtitle_id="de-ass", language="de", fmt=SubtitleFormat.ASS, score=90),
            _make_result(subtitle_id="en-ass", language="en", fmt=SubtitleFormat.ASS, score=80),
            _make_result(subtitle_id="de-srt", language="de", fmt=SubtitleFormat.SRT, score=70),
        ]
        query = VideoQuery(file_path="/test/movie.mkv", languages=["de"], forced_only=False)

        final = self._finalise(
            monkeypatch, results, query, format_filter=SubtitleFormat.ASS
        )

        assert [r.subtitle_id for r in final] == ["de-ass"]
        stages = {f["stage"]: f for f in decision_log.active().to_dict()["searches"][0]["filters"]}
        assert stages["language"]["removed"] == 1
        assert stages["language"]["rejected"][0]["language"] == "en"
        assert stages["format"]["removed"] == 1
        assert stages["format"]["rejected"][0]["format"] == "srt"

    def test_min_score_and_blacklist_stages_recorded(self, app_ctx, monkeypatch):
        decision_log.start({"id": 1})
        decision_log.search_started(["de"], None, 0)
        results = [
            _make_result(subtitle_id="good", score=200),
            _make_result(subtitle_id="weak", score=10),
            _make_result(subtitle_id="banned", score=300),
        ]
        query = VideoQuery(file_path="/test/movie.mkv", languages=["de"], forced_only=False)
        monkeypatch.setattr(
            "db.blacklist.is_blacklisted",
            lambda provider, sid: sid == "banned",
        )

        from providers import ProviderManager

        manager = ProviderManager.__new__(ProviderManager)
        final = manager._finalise_search_results(results, query, None, 50, None, None)

        assert [r.subtitle_id for r in final] == ["good"]
        stages = {f["stage"]: f for f in decision_log.active().to_dict()["searches"][0]["filters"]}
        assert stages["min_score"]["removed"] == 1
        assert stages["min_score"]["threshold"] == 50
        assert stages["blacklist"]["removed"] == 1
        assert stages["blacklist"]["rejected"][0]["filename"].startswith("banned")


class TestPersistence:
    def test_record_subtitle_download_attaches_snapshot(self, app_ctx):
        from db.providers import get_download_decision_log, record_subtitle_download
        from db.repositories.providers import ProviderRepository

        decision_log.start({"id": 5, "file_path": "/media/show.mkv"})
        decision_log.set_step("target_ass_direct")
        decision_log.search_started(["de"], SubtitleFormat.ASS, 0)
        decision_log.provider_searched("jimaku", 3, 100.0)
        decision_log.selected(_make_result(score=97))

        row_id = ProviderRepository().record_subtitle_download(
            "jimaku", "sub-1", "de", "ass", "/media/show.mkv", 97,
            decision_log_json=decision_log.snapshot_json(),
        )
        assert isinstance(row_id, int)
        raw = get_download_decision_log(row_id)
        payload = json.loads(raw)
        assert payload["final"]["provider"] == "jimaku"
        assert payload["searches"][0]["providers"][0]["name"] == "jimaku"

        # The facade attaches the snapshot automatically from the contextvar.
        record_subtitle_download("jimaku", "sub-2", "de", "ass", "/media/show2.mkv", 88)
        from db.providers import get_latest_download_id

        auto_id = get_latest_download_id("/media/show2.mkv")
        assert json.loads(get_download_decision_log(auto_id))["final"]["provider"] == "jimaku"

    def test_record_without_active_log_stores_null(self, app_ctx):
        from db.providers import (
            get_download_decision_log,
            get_latest_download_id,
            record_subtitle_download,
        )

        record_subtitle_download("manual", "up-1", "de", "srt", "/media/manual.mkv", 0)
        row_id = get_latest_download_id("/media/manual.mkv")
        assert get_download_decision_log(row_id) is None

    def test_history_list_exposes_flag_not_blob(self, app_ctx):
        from db.library import get_download_history
        from db.repositories.providers import ProviderRepository

        ProviderRepository().record_subtitle_download(
            "jimaku", "sub-1", "de", "ass", "/media/a.mkv", 97,
            decision_log_json='{"version": 1}',
        )
        ProviderRepository().record_subtitle_download(
            "subdl", "sub-2", "de", "srt", "/media/b.mkv", 44,
        )
        rows = {r["file_path"]: r for r in get_download_history()["data"]}
        assert rows["/media/a.mkv"]["has_decision_log"] is True
        assert rows["/media/b.mkv"]["has_decision_log"] is False
        assert "decision_log_json" not in rows["/media/a.mkv"]


class TestRoutes:
    def test_history_decision_route(self, client):
        from db.repositories.providers import ProviderRepository

        with client.application.app_context():
            row_id = ProviderRepository().record_subtitle_download(
                "jimaku", "sub-1", "de", "ass", "/media/a.mkv", 97,
                decision_log_json=json.dumps({"version": 1, "final": {"provider": "jimaku"}}),
            )
        resp = client.get(f"/api/v1/history/{row_id}/decision")
        assert resp.status_code == 200
        assert resp.get_json()["final"]["provider"] == "jimaku"

        resp = client.get("/api/v1/history/999999/decision")
        assert resp.status_code == 404

    def test_wanted_decision_route(self, client):
        from db.wanted import set_decision_log, upsert_wanted_item

        with client.application.app_context():
            item_id, _ = upsert_wanted_item(
                item_type="episode",
                title="Test Show",
                file_path="/media/test.mkv",
            )

        resp = client.get(f"/api/v1/wanted/{item_id}/decision")
        assert resp.status_code == 404

        with client.application.app_context():
            set_decision_log(
                item_id, json.dumps({"version": 1, "final": {"status": "not_found"}})
            )
        resp = client.get(f"/api/v1/wanted/{item_id}/decision")
        assert resp.status_code == 200
        assert resp.get_json()["final"]["status"] == "not_found"

        # List responses expose the flag, never the blob
        listed = client.get("/api/v1/wanted").get_json()["data"][0]
        assert listed["has_decision_log"] is True
        assert "last_decision_log_json" not in listed
