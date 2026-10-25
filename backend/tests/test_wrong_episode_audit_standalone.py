"""Wrong-episode audit for standalone series (gap 4).

Without Sonarr the audit had no absolute numbers or series titles, so a
standalone anime library produced the false findings Sonarr's metadata
clears ("One Piece - 892" for S21E01, "S03E40" for S03E01). Standalone series now feed the
gate the AniDB absolute number when the mapping knows it and their title;
for an anime series without one, a number past the episode's own may be its
absolute number and is left alone. Explicit contradictions are still found.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from db.models.providers import SubtitleDownload
from db.providers import record_subtitle_download
from extensions import db
from services import suspect_sidecars
from services.wrong_episode_audit import scan_wrong_episodes

ASS = (
    "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hallo\n"
)


@pytest.fixture
def standalone_library(app_ctx, tmp_path, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "media_path", str(tmp_path), raising=False)
    suspect_sidecars.invalidate_cache()
    with (
        patch("sonarr_client.get_sonarr_client", return_value=None),
        patch("radarr_client.get_radarr_client", return_value=None),
    ):
        yield tmp_path
    suspect_sidecars.invalidate_cache()


def _series(folder, title, *, is_anime, tvdb_id=None):
    from db.models.standalone import StandaloneSeries

    now = datetime.now(UTC)
    row = StandaloneSeries(
        title=title,
        folder_path=str(folder),
        is_anime=int(is_anime),
        tvdb_id=tvdb_id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _download(folder, name, release):
    video = folder / f"{name}.mkv"
    video.touch()
    (folder / f"{name}.de.ass").write_text(ASS)
    record_subtitle_download(
        "animetosho",
        f"at-{name}",
        "de",
        "ass",
        str(video),
        96,
        source="provider",
        score_breakdown={"series": 90, "episode": 30},
    )
    row = db.session.query(SubtitleDownload).filter_by(file_path=str(video)).one()
    row.decision_log_json = json.dumps(
        {"final": {"filename": f"{release}.ass", "release_info": release}}
    )
    db.session.commit()
    return str(video)


def _episode_rows(series_id, folder, season, count):
    """The scanner's episode ids for a season of ``count`` files."""
    from db.repositories.standalone_episodes import StandaloneEpisodeRepository

    repo = StandaloneEpisodeRepository()
    for n in range(1, count + 1):
        repo.upsert_episode(series_id, str(folder / f"x - S{season:02d}E{n:02d}.mkv"), season, n)


def test_bare_absolute_number_of_standalone_anime_is_left_alone(standalone_library):
    folder = standalone_library / "One Piece"
    folder.mkdir()
    _series(folder, "One Piece", is_anime=True)
    _download(folder, "One Piece - S21E01", "[SubsPlease] One Piece - 892 (1080p)")
    assert scan_wrong_episodes() == []


def test_absolute_style_episode_past_the_season_is_left_alone(standalone_library):
    folder = standalone_library / "My Hero Academia"
    folder.mkdir()
    sid = _series(folder, "My Hero Academia", is_anime=True)
    _episode_rows(sid, folder, 3, 25)
    _download(
        folder, "My Hero Academia - S03E01", "[Crunchyroll] My Hero Academia S03E40 Game Start"
    )
    assert scan_wrong_episodes() == []


def test_another_episode_inside_the_season_is_still_found(standalone_library):
    folder = standalone_library / "Show"
    folder.mkdir()
    sid = _series(folder, "Show", is_anime=True)
    _episode_rows(sid, folder, 2, 12)
    video = _download(folder, "Show - S02E05", "Show - S02E06 [1080p]")
    assert [f.video for f in scan_wrong_episodes()] == [video]


def test_explicit_season_contradiction_is_still_found(standalone_library):
    folder = standalone_library / "Clevatess"
    folder.mkdir()
    _series(folder, "Clevatess", is_anime=True)
    video = _download(folder, "Clevatess - S02E12", "Clevatess - S01E12 [CR WEB-DL 1080p]")
    assert [f.video for f in scan_wrong_episodes()] == [video]


def test_the_anidb_absolute_number_decides(standalone_library):
    """The AniDB mapping's absolute number clears the bare number, as Sonarr's does."""
    from db.repositories.anidb import AnidbRepository

    folder = standalone_library / "One Piece"
    folder.mkdir()
    # Not anime-flagged: only the mapping can clear it.
    _series(folder, "One Piece", is_anime=False, tvdb_id=81797)
    AnidbRepository().upsert_mapping(81797, 21, 1, 892)
    _download(folder, "One Piece - S21E01", "[SubsPlease] One Piece - 892 (1080p)")
    assert scan_wrong_episodes() == []


def test_non_anime_standalone_series_keeps_the_strict_rule(standalone_library):
    folder = standalone_library / "Show"
    folder.mkdir()
    _series(folder, "Show", is_anime=False)
    video = _download(folder, "Show - S21E01", "Show - 892")
    assert [f.video for f in scan_wrong_episodes()] == [video]
