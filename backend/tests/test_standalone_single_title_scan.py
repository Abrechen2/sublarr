"""WantedScanner.scan_series / scan_movie for standalone titles (gap 5).

They answered "sonarr_not_configured" / "radarr_not_configured"; a standalone
series or movie (negative id, or a positive id without the arr) now runs the
standalone scanner for that title. Sonarr/Radarr ids are unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def no_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)


def _series(app_ctx, tmp_path) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    now = datetime.now(UTC)
    row = StandaloneSeries(title="Show", folder_path=str(tmp_path), created_at=now, updated_at=now)
    db.session.add(row)
    db.session.commit()
    return row.id


def _movie(app_ctx, tmp_path) -> tuple[int, str]:
    from db.models.standalone import StandaloneMovie, WatchedFolder
    from extensions import db

    path = tmp_path / "Film (2020).mkv"
    path.write_bytes(b"\x00")
    now = datetime.now(UTC)
    db.session.add(WatchedFolder(path=str(tmp_path), created_at=now, updated_at=now))
    row = StandaloneMovie(title="Film", file_path=str(path), created_at=now, updated_at=now)
    db.session.add(row)
    db.session.commit()
    return row.id, str(path)


@pytest.mark.parametrize("sign", [-1, 1])
def test_scan_series_runs_the_standalone_scanner(app_ctx, no_arr, tmp_path, sign):
    from services.wanted_scanner import get_scanner

    sid = _series(app_ctx, tmp_path)
    fake = MagicMock()
    fake.scan_series.return_value = {"series_id": sid, "wanted_added": 2}
    with patch("standalone.scanner.get_scanner", return_value=fake):
        result = get_scanner().scan_series(sign * sid)

    fake.scan_series.assert_called_once_with(sid)
    assert result["wanted_added"] == 2
    assert result["series_id"] == sign * sid
    assert "error" not in result


def test_unknown_positive_series_without_sonarr_keeps_the_old_error(app_ctx, no_arr):
    from services.wanted_scanner import get_scanner

    assert get_scanner().scan_series(4242) == {"error": "sonarr_not_configured"}


def test_scan_movie_runs_the_standalone_scanner(app_ctx, no_arr, tmp_path):
    from services.wanted_scanner import get_scanner

    mid, path = _movie(app_ctx, tmp_path)
    fake = MagicMock()
    fake.process_single_file.return_value = {"type": "movie", "wanted": True}
    with patch("standalone.scanner.get_scanner", return_value=fake):
        result = get_scanner().scan_movie(-mid)

    fake.process_single_file.assert_called_once_with(path)
    assert result["movie_id"] == -mid
    assert "error" not in result


def test_unknown_standalone_movie_is_reported(app_ctx, no_arr):
    from services.wanted_scanner import get_scanner

    assert get_scanner().scan_movie(-999) == {"error": "movie_-999_not_found"}
