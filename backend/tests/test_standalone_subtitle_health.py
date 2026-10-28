"""Subtitle-health series scan and nightly sweep cover standalone series (gap 3).

Both used to return early without Sonarr. Findings are keyed by episode id,
so standalone episodes are scanned under their stable negative id, which
cannot collide with a Sonarr episode id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest


class _Result:
    def __init__(self, episode_id):
        self.episode_id = episode_id
        self.issues = []

    def to_dict(self):
        return {"episode_id": self.episode_id, "issues": []}


@pytest.fixture
def no_sonarr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("services.subtitle_health.series_scan.get_sonarr_client", lambda: None)
    monkeypatch.setattr("services.subtitle_health.sweep.get_sonarr_client", lambda: None)


@pytest.fixture
def show(app_ctx, tmp_path):
    from db.models.standalone import StandaloneSeries
    from extensions import db

    folder = tmp_path / "Show"
    (folder / "Season 1").mkdir(parents=True)
    paths = []
    for n in (1, 2):
        p = folder / "Season 1" / f"Show - S01E0{n}.mkv"
        p.write_bytes(b"\x00")
        paths.append(str(p))
    now = datetime.now(UTC)
    row = StandaloneSeries(title="Show", folder_path=str(folder), created_at=now, updated_at=now)
    db.session.add(row)
    db.session.commit()
    return row.id, paths


def _scan_calls(mock):
    return sorted((c.kwargs["episode_id"], c.kwargs["video_path"]) for c in mock.call_args_list)


def test_series_scan_of_a_standalone_series(no_sonarr, show):
    from services.media_ids import standalone_key
    from services.standalone_library import series_episode_files
    from services.subtitle_health.series_scan import run_series_scan

    sid, paths = show
    with patch(
        "services.subtitle_health.series_scan.scan_episode",
        side_effect=lambda **kw: _Result(kw["episode_id"]),
    ) as scan:
        summary = run_series_scan(standalone_key(sid))

    ids = {e.file_path: e.wire_id for e in series_episode_files(sid)}
    assert _scan_calls(scan) == sorted((ids[p], p) for p in paths)
    assert summary["episodes_scanned"] == 2
    assert summary["series_id"] == -sid
    assert "error" not in summary


def test_series_scan_legacy_positive_id_without_sonarr(no_sonarr, show):
    from services.subtitle_health.series_scan import run_series_scan

    sid, _ = show
    with patch(
        "services.subtitle_health.series_scan.scan_episode",
        side_effect=lambda **kw: _Result(kw["episode_id"]),
    ):
        summary = run_series_scan(sid)
    assert summary["episodes_scanned"] == 2


def test_unknown_standalone_series_reports_an_error(no_sonarr, app_ctx):
    from services.subtitle_health.series_scan import run_series_scan

    summary = run_series_scan(-999)
    assert summary["episodes_scanned"] == 0
    assert summary["error"]


def test_sweep_covers_standalone_episodes(no_sonarr, show, monkeypatch):
    from services.subtitle_health import sweep

    monkeypatch.setattr(sweep, "_sweep_enabled", lambda: True)
    monkeypatch.setattr(sweep, "_auto_fix_enabled", lambda: True)
    sid, paths = show
    with (
        patch.object(
            sweep, "scan_episode", side_effect=lambda **kw: _Result(kw["episode_id"])
        ) as scan,
        patch.object(sweep.store, "get_findings_for_episode", return_value=[]) as findings,
    ):
        sweep.subtitle_health_sweep_tick()

    scanned = _scan_calls(scan)
    # Walk order follows the episode ids, not the file names.
    assert sorted(p for _, p in scanned) == sorted(paths)
    assert all(ep_id < 0 for ep_id, _ in scanned)
    assert sorted(c.args[0] for c in findings.call_args_list) == sorted(i for i, _ in scanned)
