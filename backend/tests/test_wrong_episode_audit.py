"""Find subtitles of another episode that were saved before the episode gate.

Prod (Clevatess): before the season checks of OpenSubtitles (1.14.6) and
AnimeTosho (1.14.2), S02E05/E06/E10/E12 were saved with their S01 namesakes.
Nothing revisits a saved subtitle, so those files stayed. The audit reads the
release each download won with and puts it through the search's own episode
gate; a contradiction is quarantined like a rejected sync: blocked for that
video, kept until a replacement is saved, searched again.
"""

import json
import os
from unittest.mock import patch

import pytest

from db.models.providers import SubtitleDownload
from db.providers import record_subtitle_download
from extensions import db
from services import suspect_sidecars
from services.wrong_episode_audit import requeue_findings, scan_wrong_episodes

ASS = (
    "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hallo\n"
)


@pytest.fixture
def library(app_ctx, tmp_path, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "media_path", str(tmp_path), raising=False)
    suspect_sidecars.invalidate_cache()
    with (
        patch("sonarr_client.get_sonarr_client", return_value=None),
        patch("radarr_client.get_radarr_client", return_value=None),
    ):
        yield tmp_path
    suspect_sidecars.invalidate_cache()


def _download(folder, name, release, *, source="provider", breakdown=None, fmt="ass"):
    video = folder / f"{name}.mkv"
    video.touch()
    (folder / f"{name}.de.{fmt}").write_text(ASS)
    record_subtitle_download(
        "opensubtitles",
        f"os-{name}",
        "de",
        fmt,
        str(video),
        96,
        source=source,
        score_breakdown=breakdown or {"year": 90, "episode": 30},
    )
    row = db.session.query(SubtitleDownload).filter_by(file_path=str(video)).one()
    row.decision_log_json = json.dumps(
        {"final": {"filename": f"{release}.srt", "release_info": release}}
    )
    db.session.commit()
    return str(video)


def test_finds_the_season_1_namesake_saved_for_season_2(library):
    video = _download(library, "Clevatess - S02E12", "Clevatess - S01E12 [CR WEB-DL 1080p]")
    _download(library, "Clevatess - S02E07", "Clevatess S02E07 1080p WEB")

    findings = scan_wrong_episodes()

    assert [f.video for f in findings] == [video]
    assert "S01E12" in findings[0].reason


def test_a_bare_number_without_absolute_is_not_flagged(library):
    # "- 12" may be season 2's twelfth; the audit flags only what the name contradicts.
    _download(library, "Clevatess - S02E12", "[SubsPlease] Clevatess - 12 (1080p)")
    assert scan_wrong_episodes() == []


def test_manual_downloads_are_not_audited(library):
    _download(library, "Clevatess - S02E12", "Clevatess - S01E12", source="manual")
    assert scan_wrong_episodes() == []


def test_a_hash_match_is_trusted(library):
    _download(library, "Clevatess - S02E12", "Clevatess - S01E12", breakdown={"hash": 359})
    assert scan_wrong_episodes() == []


def test_a_replaced_sidecar_is_judged_by_its_newest_download(library):
    video = _download(library, "Clevatess - S02E12", "Clevatess - S01E12")
    record_subtitle_download("subdl", "sd-1", "de", "ass", video, 300)
    row = db.session.query(SubtitleDownload).filter_by(file_path=video, provider_name="subdl").one()
    row.decision_log_json = json.dumps({"final": {"release_info": "Clevatess S02E12"}})
    db.session.commit()
    assert scan_wrong_episodes() == []


def test_requeue_quarantines_each_finding(library):
    from db.wanted import get_wanted_items_by_path
    from services.suspect_sidecars import blocks_result_for

    video = _download(library, "Clevatess - S02E12", "Clevatess - S01E12")
    findings = scan_wrong_episodes()

    assert requeue_findings(findings) == 1

    sidecar = video.replace(".mkv", ".de.ass")
    assert not os.path.exists(sidecar), "moved to the trash"
    assert blocks_result_for("opensubtitles", "os-Clevatess - S02E12", video)
    assert [i["status"] for i in get_wanted_items_by_path(video)] == ["wanted"]
    assert scan_wrong_episodes() == [], "a quarantined sidecar is not reported again"


def test_an_absolute_style_s01_number_is_left_alone(library):
    # "S01E17" for S02E05 may be absolute episode 17; the audit does not know
    # Sonarr's absolute number, so it only flags what cannot be absolute.
    _download(library, "Show - S02E05", "Show - S01E17 [1080p]")
    assert scan_wrong_episodes() == []


def test_another_episode_of_the_same_season_is_flagged(library):
    video = _download(library, "Show - S02E05", "Show - S02E06 [1080p]")
    assert [f.video for f in scan_wrong_episodes()] == [video]


def test_requeue_rescans_each_series_once(app_ctx, tmp_path):
    from unittest.mock import MagicMock

    suspect_sidecars.invalidate_cache()
    _download(tmp_path, "Clevatess - S02E05", "Clevatess - S01E05")
    _download(tmp_path, "Clevatess - S02E12", "Clevatess - S01E12")
    sonarr = MagicMock()
    sonarr.get_series.return_value = [{"id": 1084, "path": str(tmp_path)}]
    scanner = MagicMock()
    scanner.scan_series.return_value = {"added": 2}
    with (
        patch("sonarr_client.get_sonarr_client", return_value=sonarr),
        patch("radarr_client.get_radarr_client", return_value=None),
        patch("config.map_path", side_effect=lambda p: p),
        patch("services.wanted_scanner.get_scanner", return_value=scanner),
    ):
        findings = scan_wrong_episodes()  # looks up Sonarr's numbering itself
        sonarr.get_series.reset_mock()
        assert requeue_findings(findings) == 2
    scanner.scan_series.assert_called_once_with(1084)
    sonarr.get_series.assert_called_once()


@pytest.fixture
def sonarr_library(app_ctx, tmp_path):
    """A Sonarr series holding tmp_path, with absolute numbers and titles."""
    from unittest.mock import MagicMock

    suspect_sidecars.invalidate_cache()
    sonarr = MagicMock()
    sonarr.get_series.return_value = [{"id": 7, "path": str(tmp_path)}]
    sonarr.get_episodes.return_value = [
        {
            "seasonNumber": 4,
            "episodeNumber": 1,
            "absoluteEpisodeNumber": 60,
            "title": "The Other Side of the Sea",
        },
        {"seasonNumber": 3, "episodeNumber": 1, "absoluteEpisodeNumber": 39, "title": "Game Start"},
        {
            "seasonNumber": 2,
            "episodeNumber": 5,
            "absoluteEpisodeNumber": 17,
            "title": "Battle With Oneself",
        },
    ]
    with (
        patch("sonarr_client.get_sonarr_client", return_value=sonarr),
        patch("radarr_client.get_radarr_client", return_value=None),
        patch("config.map_path", side_effect=lambda p: p),
    ):
        yield tmp_path, sonarr
    suspect_sidecars.invalidate_cache()


class TestProdFalseAlarms:
    """Prod 1.17.0-rc.4 flagged ~100 subtitles that were the right episode."""

    def test_an_absolute_number_from_sonarr_is_the_episode(self, sonarr_library):
        folder, _ = sonarr_library
        _download(folder, "Attack on Titan - S04E01", "Shingeki no Kyojin (The Final Season) - 60")
        assert scan_wrong_episodes() == []

    def test_the_sonarr_title_in_the_release_is_the_episode(self, sonarr_library):
        folder, _ = sonarr_library
        _download(
            folder, "My Hero Academia - S03E01", "[Crunchyroll] My Hero Academia S03E40 Game Start"
        )
        assert scan_wrong_episodes() == []

    def test_a_batch_range_holding_the_episode_is_not_flagged(self, library):
        _download(library, "Death Note - S01E24", "[Redc4t] Death Note - 13-24 [BD 720p] [Batch]")
        assert scan_wrong_episodes() == []

    def test_a_split_cour_bare_number_is_left_alone(self, library):
        # "Part 2 - 10" may be Sonarr's S03E21; only Sonarr's cour split knows.
        _download(
            library, "Dr. STONE - S03E21", "[Erai-raws] Dr Stone - New World Part 2 - 10 [1080p]"
        )
        assert scan_wrong_episodes() == []

    def test_clevatess_is_still_flagged_with_sonarr_metadata(self, sonarr_library):
        folder, sonarr = sonarr_library
        video = _download(folder, "Clevatess - S02E05", "Clevatess - S01E05 [CR WEB-DL 1080p]")
        assert [f.video for f in scan_wrong_episodes()] == [video]

    def test_sonarr_is_asked_once_per_series(self, sonarr_library):
        folder, sonarr = sonarr_library
        _download(folder, "Clevatess - S02E05", "Clevatess - S01E05")
        _download(folder, "Clevatess - S02E06", "Clevatess - S01E06")
        scan_wrong_episodes()
        sonarr.get_series.assert_called_once()
        sonarr.get_episodes.assert_called_once_with(7)


def test_sonarr_never_turns_a_bare_number_into_a_finding(sonarr_library):
    # A sequel numbers its season in the title ("Psycho-Pass 2 - 01" for S02E01,
    # absolute 23); Sonarr's absolute alone cannot tell it from season 1's first.
    folder, sonarr = sonarr_library
    sonarr.get_episodes.return_value = [
        {"seasonNumber": 2, "episodeNumber": 1, "absoluteEpisodeNumber": 23, "title": "Scales"}
    ]
    _download(folder, "Psycho-Pass - S02E01", "[Erai-raws] Psycho-Pass 2 - 01 ~ 11 [1080p]")
    assert scan_wrong_episodes() == []


def test_sonarrs_absolute_confirms_an_explicit_contradiction(sonarr_library):
    # S01E17 for S16E10 may look like absolute numbering without Sonarr; Sonarr
    # says S16E10 is absolute 266, so it is season 1's seventeenth.
    folder, sonarr = sonarr_library
    sonarr.get_episodes.return_value = [
        {"seasonNumber": 16, "episodeNumber": 10, "absoluteEpisodeNumber": 266, "title": "Wild"}
    ]
    video = _download(folder, "American Dad! - S16E10", "American Dad S01E17 Rough Trade")
    assert [f.video for f in scan_wrong_episodes()] == [video]


def test_a_title_sonarr_scopes_to_another_season_is_a_finding(sonarr_library):
    # Prod replay: "Dr Stone - Science Future - 10" (Sonarr scene season 4)
    # saved for S03E10. The bare number alone proves nothing; the title does.
    folder, sonarr = sonarr_library
    sonarr.get_series.return_value = [
        {
            "id": 7,
            "path": str(folder),
            "alternateTitles": [
                {"title": "Dr. Stone: New World", "sceneSeasonNumber": 3},
                {"title": "Dr. Stone: Science Future", "sceneSeasonNumber": 4},
            ],
        }
    ]
    sonarr.get_episodes.return_value = [
        {
            "seasonNumber": 3,
            "episodeNumber": 10,
            "absoluteEpisodeNumber": 34,
            "title": "SCIENCE WARS",
        }
    ]
    video = _download(
        folder, "Dr. STONE - S03E10", "[Erai-raws] Dr Stone - Science Future - 10 [1080p]"
    )
    findings = scan_wrong_episodes()
    assert [f.video for f in findings] == [video]
    assert "season 4 by its title" in findings[0].reason


def test_a_title_scoped_to_the_videos_season_is_not_a_finding(sonarr_library):
    folder, sonarr = sonarr_library
    sonarr.get_series.return_value = [
        {
            "id": 7,
            "path": str(folder),
            "alternateTitles": [
                {"title": "Strike Witches - Road to Berlin", "sceneSeasonNumber": 3}
            ],
        }
    ]
    sonarr.get_episodes.return_value = [
        {"seasonNumber": 3, "episodeNumber": 5, "absoluteEpisodeNumber": 33, "title": "Queen"}
    ]
    _download(folder, "Strike Witches - S03E05", "[Golumpa] Strike Witches - Road to Berlin - 05")
    assert scan_wrong_episodes() == []


def test_the_bare_series_title_scoped_to_season_one_proves_nothing(sonarr_library):
    # Sonarr lists the series' own title as scene season 1 (Railgun, K-ON!). With
    # the title itself voting "every season", "Show - 01" for S02E01 is not a
    # season-1 finding by its title.
    folder, sonarr = sonarr_library
    sonarr.get_series.return_value = [
        {
            "id": 7,
            "title": "Show",
            "path": str(folder),
            "alternateTitles": [{"title": "Show", "sceneSeasonNumber": 1}],
        }
    ]
    sonarr.get_episodes.return_value = [
        {"seasonNumber": 2, "episodeNumber": 1, "absoluteEpisodeNumber": 13, "title": "X"}
    ]
    _download(folder, "Show - S02E01", "[Group] Show - 01 [1080p]")
    assert scan_wrong_episodes() == []
