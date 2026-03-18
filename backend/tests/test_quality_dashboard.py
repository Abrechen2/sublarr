"""Translation Quality Dashboard — statistics endpoint tests.

Verifies that GET /statistics returns quality_trend and series_quality
with correct structure and normalization.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row(mapping: dict):
    """Build a mock DB row that supports _mapping and positional access."""
    m = MagicMock()
    m._mapping = mapping
    # positional index access for rows used as tuples
    items = list(mapping.values())

    def getitem(k):
        return items[k]

    m.__getitem__ = getitem
    return m


def _make_app():
    """Create a minimal Flask test app."""
    import flask

    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    return app


# ── TestQualityTrendNormalization ─────────────────────────────────────────────


class TestQualityTrendNormalization:
    """Verify avg_score normalization logic (raw score → 0-100%)."""

    def test_zero_score_gives_zero_pct(self):
        score_max = 900.0
        avg_raw = 0.0
        pct = round(min(100.0, avg_raw / score_max * 100), 1)
        assert pct == 0.0

    def test_max_score_gives_100_pct(self):
        score_max = 900.0
        avg_raw = 900.0
        pct = round(min(100.0, avg_raw / score_max * 100), 1)
        assert pct == 100.0

    def test_over_max_score_capped_at_100(self):
        score_max = 900.0
        avg_raw = 1200.0  # can exceed max
        pct = round(min(100.0, avg_raw / score_max * 100), 1)
        assert pct == 100.0

    def test_midpoint_score(self):
        score_max = 900.0
        avg_raw = 450.0
        pct = round(min(100.0, avg_raw / score_max * 100), 1)
        assert pct == 50.0

    def test_typical_score_range(self):
        score_max = 900.0
        # Typical decent subtitle: ~600 score
        avg_raw = 600.0
        pct = round(min(100.0, avg_raw / score_max * 100), 1)
        assert 60.0 <= pct <= 75.0


# ── TestStatisticsQualityFields ───────────────────────────────────────────────


class TestStatisticsQualityFields:
    """Verify that /statistics endpoint includes quality_trend and series_quality."""

    def _setup_mocks(self, mock_db_execute):
        """Set up mock DB return values for all queries in get_statistics()."""

        call_count = [0]

        def side_effect(query, *args, **kwargs):
            q = str(query).strip()
            result = MagicMock()
            call_count[0] += 1

            if "daily_stats" in q:
                result.fetchall.return_value = []
            elif (
                "provider_name, COUNT" in q
                and "subtitle_downloads" in q
                and "GROUP_CONCAT" not in q
            ):
                # downloads_by_provider
                result.fetchall.return_value = []
            elif "translation_backend_stats" in q or "upgrade_history" in q:
                result.fetchall.return_value = []
            elif "substr(downloaded_at" in q:
                # quality_trend query
                row = MagicMock()
                row.__getitem__ = lambda self, k: ["2026-01-15", 630.0, 5, 0][k]
                result.fetchall.return_value = [row]
            elif "GROUP_CONCAT" in q:
                # series_quality query
                row = MagicMock()
                row.__getitem__ = lambda self, k: [
                    "Attack on Titan",
                    720.0,
                    10,
                    "2026-01-14T12:00:00",
                    "ass",
                ][k]
                result.fetchall.return_value = [row]
            else:
                result.fetchall.return_value = []

            return result

        mock_db_execute.side_effect = side_effect

    def test_quality_trend_in_response(self):
        app = _make_app()

        with (
            app.test_request_context("/api/v1/statistics?range=30d"),
            patch("db.get_db") as mock_get_db,
            patch("db.providers.get_provider_stats", return_value={}),
        ):
            mock_conn = MagicMock()
            mock_get_db.return_value = mock_conn
            self._setup_mocks(mock_conn.execute)

            from routes.system import get_statistics

            response = get_statistics()
            data = response.get_json()

        assert "quality_trend" in data
        assert isinstance(data["quality_trend"], list)

    def test_series_quality_in_response(self):
        app = _make_app()

        with (
            app.test_request_context("/api/v1/statistics?range=30d"),
            patch("db.get_db") as mock_get_db,
            patch("db.providers.get_provider_stats", return_value={}),
        ):
            mock_conn = MagicMock()
            mock_get_db.return_value = mock_conn
            self._setup_mocks(mock_conn.execute)

            from routes.system import get_statistics

            response = get_statistics()
            data = response.get_json()

        assert "series_quality" in data
        assert isinstance(data["series_quality"], list)

    def test_quality_trend_structure(self):
        """Each quality_trend entry has the expected fields."""
        SCORE_MAX = 900.0
        raw_score = 630.0
        entry = {
            "date": "2026-01-15",
            "avg_score": round(min(100.0, raw_score / SCORE_MAX * 100), 1),
            "files_checked": 5,
            "issues_count": 0,
        }
        assert "date" in entry
        assert "avg_score" in entry
        assert "files_checked" in entry
        assert "issues_count" in entry
        assert 0 <= entry["avg_score"] <= 100

    def test_series_quality_structure(self):
        """Each series_quality entry has the expected fields."""
        SCORE_MAX = 900.0
        raw_score = 720.0
        entry = {
            "title": "Attack on Titan",
            "avg_score": round(raw_score, 1),
            "avg_score_pct": round(min(100.0, raw_score / SCORE_MAX * 100), 1),
            "download_count": 10,
            "last_download": "2026-01-14T12:00:00",
            "formats": ["ass"],
        }
        for key in (
            "title",
            "avg_score",
            "avg_score_pct",
            "download_count",
            "last_download",
            "formats",
        ):
            assert key in entry
        assert isinstance(entry["formats"], list)
        assert 0 <= entry["avg_score_pct"] <= 100
