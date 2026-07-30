"""Tests for services.health_overview + GET /api/v1/health/library
and the sync-rate fields added to /api/v1/statistics/subtitles."""

from datetime import UTC, datetime


def _add_wanted(app, title, status="wanted", failure_kind=None, item_type="episode", **kw):
    from db.models.core import WantedItem
    from extensions import db

    with app.app_context():
        now = datetime.now(UTC)
        item = WantedItem(
            item_type=item_type,
            title=title,
            file_path=kw.get("file_path", f"/media/{title}/{title}-{status}.mkv"),
            status=status,
            failure_kind=failure_kind,
            season_episode=kw.get("season_episode", "S01E01"),
            target_language="de",
            error=kw.get("error", ""),
            search_count=kw.get("search_count", 0),
            added_at=now,
            updated_at=now,
        )
        db.session.add(item)
        db.session.commit()
        return item.id


def _add_provider_stats(app, name, searches=0, hits=0, auto_disabled=False):
    from db.models.providers import ProviderStats
    from extensions import db

    with app.app_context():
        row = ProviderStats(
            provider_name=name,
            total_searches=searches,
            successful_searches=hits,
            auto_disabled=1 if auto_disabled else 0,
            updated_at=datetime.now(UTC),
        )
        db.session.add(row)
        db.session.commit()


def _add_breaker(app, name, state="open", failures=5):
    from db.models.circuit_breaker import CircuitBreakerState
    from extensions import db

    with app.app_context():
        db.session.add(
            CircuitBreakerState(
                name=name,
                state=state,
                failure_count=failures,
                updated_at=datetime.now(UTC),
            )
        )
        db.session.commit()


class TestLibraryHealthService:
    def test_empty_library(self, app_ctx):
        from services.health_overview import get_library_health

        result = get_library_health()
        assert result["totals"]["wanted"] == 0
        assert result["totals"]["problems"] == 0
        assert result["series"] == []
        assert result["problems"] == []

    def test_series_aggregation_and_problem_items(self, client):
        app = client.application
        _add_wanted(app, "Show A", status="wanted", file_path="/m/a1.mkv")
        _add_wanted(app, "Show A", status="failed", error="File not found", file_path="/m/a2.mkv")
        _add_wanted(app, "Show A", failure_kind="unsourceable", file_path="/m/a3.mkv")
        _add_wanted(app, "Show B", status="wanted", file_path="/m/b1.mkv")
        _add_wanted(app, "Show C", status="ignored", file_path="/m/c1.mkv")

        resp = client.get("/api/v1/health/library")
        assert resp.status_code == 200
        body = resp.get_json()

        assert body["totals"]["wanted"] == 4  # ignored excluded
        assert body["totals"]["problems"] == 2
        assert body["totals"]["unmatched"] == 1

        by_title = {s["title"]: s for s in body["series"]}
        assert by_title["Show A"]["missing"] == 3
        assert by_title["Show A"]["problems"] == 2
        assert by_title["Show B"]["missing"] == 1
        assert "Show C" not in by_title

        kinds = {p["failure_kind"] for p in body["problems"]}
        assert "unsourceable" in kinds
        assert all(p["status"] != "ignored" for p in body["problems"])

    def test_provider_health_merges_breaker_and_stats(self, client):
        app = client.application
        _add_provider_stats(app, "goodprov", searches=100, hits=60)
        _add_provider_stats(app, "deadprov", searches=50, hits=1)
        _add_breaker(app, "brokenprov", state="open", failures=7)

        resp = client.get("/api/v1/health/library")
        assert resp.status_code == 200
        providers = {p["provider"]: p for p in resp.get_json()["providers"]}

        assert providers["goodprov"]["degraded"] is False
        assert providers["deadprov"]["degraded"] is True  # 2% hit rate over 50 searches
        assert providers["brokenprov"]["degraded"] is True
        assert providers["brokenprov"]["breaker_state"] == "open"
        assert providers["brokenprov"]["breaker_failures"] == 7
        # Degraded providers sort first.
        listed = [p["provider"] for p in resp.get_json()["providers"]]
        assert listed.index("goodprov") > max(
            listed.index("deadprov"), listed.index("brokenprov")
        )


class TestSyncRateInSubtitlesStats:
    def _add_sync_run(self, app, status, engine="ffsubsync"):
        from db.models.core import SyncJobRun
        from extensions import db

        with app.app_context():
            db.session.add(
                SyncJobRun(
                    engine=engine,
                    status=status,
                    offset_ms=100,
                    duration_ms=1000,
                    subtitle_path="/m/a.de.srt",
                    video_path="/m/a.mkv",
                    created_at=datetime.now(UTC),
                )
            )
            db.session.commit()

    def test_sync_rate_none_without_runs(self, client):
        resp = client.get("/api/v1/statistics/subtitles")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["sync_runs"] == 0
        assert body["sync_rate"] is None

    def test_sync_rate_computed(self, client):
        app = client.application
        self._add_sync_run(app, "ok")
        self._add_sync_run(app, "ok")
        self._add_sync_run(app, "ok")
        self._add_sync_run(app, "failed")

        resp = client.get("/api/v1/statistics/subtitles")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["sync_runs"] == 4
        assert body["sync_ok"] == 3
        assert body["sync_rate"] == 0.75
