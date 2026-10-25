"""Series-wide bulk actions in standalone mode see every episode file.

The standalone branches of the series subtitle batch-delete, batch track
extraction and batch processing listed files from ``wanted_items``. That
table only holds episodes still missing a subtitle, so the episodes that
actually had subtitles were never touched. They now enumerate the series
folder, falling back to ``wanted_items`` while it is unreachable.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


@pytest.fixture
def no_sonarr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)


def _series(folder: str) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    now = datetime.now(UTC)
    row = StandaloneSeries(title="Show", folder_path=folder, created_at=now, updated_at=now)
    db.session.add(row)
    db.session.commit()
    return row.id


def _wanted(series_id: int, file_path: str) -> None:
    from db.models.core import WantedItem
    from extensions import db

    now = datetime.now(UTC)
    db.session.add(
        WantedItem(
            item_type="episode",
            title="x",
            file_path=file_path,
            standalone_series_id=series_id,
            target_language="de",
            status="wanted",
            added_at=now,
            updated_at=now,
        )
    )
    db.session.commit()


def _episodes(tmp_path):
    folder = tmp_path / "show"
    folder.mkdir()
    ep1 = folder / "Show - S01E01.mkv"
    ep2 = folder / "Show - S01E02.mkv"
    ep1.write_bytes(b"\x00")
    ep2.write_bytes(b"\x00")
    (folder / "Show - S01E01.de.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n")
    return folder, str(ep1), str(ep2)


def test_video_paths_include_episodes_without_wanted_rows(app_ctx, tmp_path):
    from routes.library.series import standalone_series_video_paths

    folder, ep1, ep2 = _episodes(tmp_path)
    sid = _series(str(folder))
    _wanted(sid, ep2)  # only E02 still misses a subtitle

    assert standalone_series_video_paths(sid) == [ep1, ep2]


def test_video_paths_fall_back_to_wanted_rows_when_folder_is_gone(app_ctx, tmp_path):
    from routes.library.series import standalone_series_video_paths

    folder = tmp_path / "unmounted"
    sid = _series(str(folder))
    _wanted(sid, str(folder / "Show - S01E03.mkv"))
    # A recorded path outside the series folder is not used (symlink/escape guard).
    _wanted(sid, "/elsewhere/Show - S01E04.mkv")

    assert standalone_series_video_paths(sid) == [str(folder / "Show - S01E03.mkv")]


def test_video_paths_unknown_series_is_none(app_ctx):
    from routes.library.series import standalone_series_video_paths

    assert standalone_series_video_paths(4242) is None


def test_batch_delete_reaches_the_subtitled_episode(client, no_sonarr, tmp_path):
    folder, ep1, ep2 = _episodes(tmp_path)
    with client.application.app_context():
        sid = _series(str(folder))
        _wanted(sid, ep2)

    resp = client.post(
        f"/api/v1/library/series/{sid}/subtitles/batch-delete", json={"languages": ["de"]}
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["deleted"] == 1
    assert not (folder / "Show - S01E01.de.srt").exists()


def test_batch_delete_unknown_standalone_series_is_404(client, no_sonarr):
    resp = client.post("/api/v1/library/series/4242/subtitles/batch-delete", json={})
    assert resp.status_code == 404
    assert "Sonarr" not in resp.get_json()["error"]
