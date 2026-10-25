"""A downloaded subtitle the sync rejects as another episode gets replaced.

Prod 2026-10 (Clevatess): ffsubsync measured shifts beyond the ±45 s sanity
threshold on subtitles of other episodes. The sync left the file alone and the
automation row went terminal, and because a target ASS was on disk the wanted
scanner never queued the episode again — the wrong subtitle stayed for good.

Now such a sidecar, when Sublarr downloaded it from a provider, is
blacklisted (provider + subtitle id), marked suspect and requeued for a fresh
search. The file goes to the subtitle trash.
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest

from db.blacklist import is_blacklisted
from db.providers import record_subtitle_download
from db.wanted import get_wanted_items_by_path
from services import suspect_sidecars
from services.suspect_sidecars import (
    existing_ignoring_suspects,
    is_suspect_sidecar,
    quarantine_wrong_sidecar,
    retire_suspect_siblings,
)

ASS = (
    "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hallo\n"
)
SRT = "1\n00:00:01,000 --> 00:00:02,000\nHallo\n"
FULL_ASS = (
    "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
    "100,100,0,0,1,2,2,2,10,10,10,1\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Korrekte neue Folge\n"
)


@pytest.fixture
def kept_on_disk():
    """Quarantine as if the trash refused the file: it stays, flagged."""
    with patch("services.suspect_sidecars._trash", return_value=[]):
        yield


@pytest.fixture
def episode(app_ctx, tmp_path):
    """A downloaded sidecar whose quarantine leaves it on disk.

    That is a file the trash refused: the flag's guards are what still keep it
    from counting. tests/test_quarantine_lifecycle.py covers the move itself.
    """
    video = tmp_path / "Clevatess - S01E01.mkv"
    video.touch()
    sidecar = tmp_path / "Clevatess - S01E01.de.ass"
    sidecar.write_text(ASS)
    suspect_sidecars.invalidate_cache()
    with patch("services.suspect_sidecars._trash", return_value=[]):
        yield str(video), str(sidecar)
    suspect_sidecars.invalidate_cache()


def _record(video: str, *, source: str = "provider", fmt: str = "ass", sid: str = "at-123"):
    record_subtitle_download("animetosho", sid, "de", fmt, video, 300, source=source)


@pytest.fixture
def no_arr():
    with (
        patch("sonarr_client.get_sonarr_client", return_value=None),
        patch("radarr_client.get_radarr_client", return_value=None),
    ):
        yield


class TestQuarantine:
    def test_provider_download_is_blacklisted_flagged_and_requeued(self, episode, no_arr):
        video, sidecar = episode
        _record(video)

        assert quarantine_wrong_sidecar(sidecar, video, "shift 52000ms") is True

        assert is_blacklisted("animetosho", "at-123")
        assert is_suspect_sidecar(sidecar)
        assert os.path.isfile(sidecar), "kept: the trash refused it"
        items = get_wanted_items_by_path(video)
        assert [(i["target_language"], i["status"]) for i in items] == [("de", "wanted")]

    def test_manual_upload_is_left_alone(self, episode, no_arr):
        video, sidecar = episode
        _record(video, source="manual")

        assert quarantine_wrong_sidecar(sidecar, video, "shift") is False

        assert not is_blacklisted("animetosho", "at-123")
        assert not is_suspect_sidecar(sidecar)
        assert get_wanted_items_by_path(video) == []

    def test_a_record_for_another_format_does_not_vouch(self, episode, no_arr):
        video, sidecar = episode
        _record(video, fmt="srt")

        assert quarantine_wrong_sidecar(sidecar, video, "shift") is False
        assert not is_blacklisted("animetosho", "at-123")

    def test_a_hand_edited_sidecar_is_left_alone(self, episode, no_arr):
        from db.quality import mark_user_modified

        video, sidecar = episode
        _record(video)
        mark_user_modified(sidecar)

        assert quarantine_wrong_sidecar(sidecar, video, "shift") is False
        assert not is_blacklisted("animetosho", "at-123")

    def test_no_download_record_is_left_alone(self, episode, no_arr):
        video, sidecar = episode
        assert quarantine_wrong_sidecar(sidecar, video, "shift") is False

    def test_requeue_clears_the_old_backoff(self, episode, no_arr):
        # VM 191: an item in slow mode kept its 30-day retry_after after the
        # requeue, so the new search waited out the old failure.
        from datetime import UTC, datetime, timedelta

        from db.models.core import WantedItem
        from db.wanted import upsert_wanted_item
        from extensions import db

        video, sidecar = episode
        _record(video)
        upsert_wanted_item(
            item_type="episode",
            file_path=video,
            title="Clevatess",
            season_episode="S01E01",
            target_language="de",
        )
        row = db.session.query(WantedItem).filter_by(file_path=video).one()
        row.retry_after = datetime.now(UTC) + timedelta(days=30)
        row.search_count = 30
        row.error_count = 12
        row.failure_kind = "no_result_slow"
        db.session.commit()

        assert quarantine_wrong_sidecar(sidecar, video, "shift") is True

        db.session.refresh(row)
        assert (row.retry_after, row.search_count, row.error_count, row.failure_kind) == (
            None,
            0,
            0,
            None,
        )

    def test_requeue_keeps_the_standalone_series_link(self, episode, no_arr, tmp_path):
        """Standalone mode: the requeue upsert overwrote an existing row's
        standalone_series_id with NULL, so the episode left its series page."""
        from datetime import UTC, datetime

        from db.models.standalone import StandaloneSeries
        from db.wanted import upsert_wanted_item
        from extensions import db

        video, sidecar = episode
        _record(video)
        now = datetime.now(UTC)
        series = StandaloneSeries(
            title="Clevatess", folder_path=str(tmp_path), created_at=now, updated_at=now
        )
        db.session.add(series)
        db.session.commit()
        upsert_wanted_item(
            item_type="episode",
            file_path=video,
            title="Clevatess -- S01E01",
            season_episode="S01E01",
            target_language="de",
            instance_name="standalone",
            standalone_series_id=series.id,
            status="ignored",
        )

        assert quarantine_wrong_sidecar(sidecar, video, "shift") is True

        items = get_wanted_items_by_path(video)
        assert [(i["standalone_series_id"], i["instance_name"]) for i in items] == [
            (series.id, "standalone")
        ]

    def test_requeue_links_a_standalone_movie_by_its_file(self, app_ctx, tmp_path, no_arr):
        from datetime import UTC, datetime

        from db.models.standalone import StandaloneMovie
        from extensions import db

        video = tmp_path / "Film (2020).mkv"
        video.touch()
        now = datetime.now(UTC)
        movie = StandaloneMovie(title="Film", file_path=str(video), created_at=now, updated_at=now)
        db.session.add(movie)
        db.session.commit()

        suspect_sidecars._plain_wanted_row(str(video), "de")

        items = get_wanted_items_by_path(str(video))
        assert [(i["standalone_movie_id"], i["item_type"]) for i in items] == [(movie.id, "movie")]

    def test_requeue_rescans_the_sonarr_series(self, episode):
        video, sidecar = episode
        _record(video)
        sonarr = MagicMock()
        sonarr.get_series.return_value = [
            {"id": 7, "path": "/elsewhere"},
            {"id": 9, "path": os.path.dirname(video)},
        ]
        scanner = MagicMock()
        scanner.scan_series.return_value = {"added": 1, "updated": 0}
        with (
            patch("sonarr_client.get_sonarr_client", return_value=sonarr),
            patch("radarr_client.get_radarr_client", return_value=None),
            patch("services.wanted_scanner.get_scanner", return_value=scanner),
        ):
            assert quarantine_wrong_sidecar(sidecar, video, "shift") is True
        scanner.scan_series.assert_called_once_with(9)


class TestSuspectState:
    def test_a_replaced_sidecar_is_no_longer_suspect(self, episode, no_arr):
        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        with open(sidecar, "w") as fh:
            fh.write(ASS.replace("Hallo", "Die richtige Folge"))

        assert not is_suspect_sidecar(sidecar)

    def test_a_replacement_saved_right_away_is_not_suspect(self, episode, no_arr, monkeypatch):
        # VM 191 (RC 1.17.0-rc.1): a replacement saved within the 60 s grace
        # after the flag stayed suspect for good, since its mtime never moves on.
        from providers.base import SubtitleFormat, SubtitleResult
        from providers.download_manager import save_subtitle

        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        monkeypatch.setattr("security_utils.is_safe_path", lambda *a, **kw: True)
        replacement = SubtitleResult(
            provider_name="opensubtitles",
            subtitle_id="os-new",
            language="de",
            format=SubtitleFormat.ASS,
            content=FULL_ASS.encode(),
        )

        save_subtitle(replacement, sidecar)
        suspect_sidecars.invalidate_cache()

        assert not is_suspect_sidecar(sidecar)
        assert existing_ignoring_suspects(video, "de", "ass") == "ass"

    def test_touching_the_flagged_file_does_not_clear_it(self, episode, no_arr):
        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        later = time.time() + 600
        os.utime(sidecar, (later, later))

        assert is_suspect_sidecar(sidecar), "same bytes, same wrong subtitle"

    def test_the_same_wrong_file_restored_is_suspect_again(self, episode, no_arr):
        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        with open(sidecar, "w") as fh:
            fh.write(ASS.replace("Hallo", "Ersatz"))
        assert not is_suspect_sidecar(sidecar)

        with open(sidecar, "w") as fh:
            fh.write(ASS)

        assert is_suspect_sidecar(sidecar)

    @staticmethod
    def _swap_in(sidecar: str, text: str) -> None:
        """Move a new file onto the path, keeping size and mtime (``cp -p``, rsync -t)."""
        stat = os.stat(sidecar)
        staged = sidecar + ".restore"
        with open(staged, "w") as fh:
            fh.write(text)
        os.utime(staged, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        os.replace(staged, sidecar)
        suspect_sidecars.invalidate_cache()

    def test_a_wrong_file_swapped_in_with_kept_metadata_is_suspect(self, episode, no_arr):
        # VM 191 (rc.2): the digest was cached by path, mtime and size, so a
        # same-sized file moved in with the old mtime kept the old verdict.
        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        right = ASS.replace("Hallo", "Hello")  # same length as the wrong text
        self._swap_in(sidecar, right)
        assert not is_suspect_sidecar(sidecar)

        self._swap_in(sidecar, ASS)

        assert is_suspect_sidecar(sidecar)

    def test_a_right_file_swapped_in_with_kept_metadata_is_not_suspect(self, episode, no_arr):
        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        assert is_suspect_sidecar(sidecar)

        self._swap_in(sidecar, ASS.replace("Hallo", "Hello"))

        assert not is_suspect_sidecar(sidecar)

    def test_bytes_count_even_when_every_stat_field_is_unchanged(
        self, episode, no_arr, monkeypatch
    ):
        # VM 191 (rc.3): an in-place rewrite inside one timestamp tick, with the
        # mtime set back, leaves inode, size, mtime and ctime as they were.
        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        frozen = os.stat(sidecar)
        monkeypatch.setattr(suspect_sidecars.os, "fstat", lambda _fd: frozen)
        monkeypatch.setattr(suspect_sidecars.os, "stat", lambda *_a, **_kw: frozen)

        with open(sidecar, "w") as fh:
            fh.write(ASS.replace("Hallo", "Hello"))
        assert not is_suspect_sidecar(sidecar)

        with open(sidecar, "w") as fh:
            fh.write(ASS)
        assert is_suspect_sidecar(sidecar)

    def test_a_repeat_quarantine_flags_the_file_on_disk_now(self, episode, no_arr):
        # VM 191: flagging a path a second time returned True but left the old
        # flag, so the file on disk now was never suspect.
        from datetime import UTC, datetime, timedelta

        from db.models.core import BlacklistEntry
        from extensions import db

        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        # The first flag is old; the file has been replaced since.
        entry = db.session.query(BlacklistEntry).one()
        entry.added_at = datetime.now(UTC) - timedelta(minutes=10)
        entry.file_path = entry.file_path.partition("\t")[0]
        db.session.commit()
        with open(sidecar, "w") as fh:
            fh.write(ASS.replace("Hallo", "Auch falsch"))
        _record(video)

        assert quarantine_wrong_sidecar(sidecar, video, "rejected again") is True

        assert is_suspect_sidecar(sidecar)

    def test_two_providers_wrong_files_under_one_name_are_both_suspect(self, episode, no_arr):
        # Provider A's wrong file is quarantined, provider B's replacement under
        # the same name is wrong too: whichever row loads last must not hide the other.
        video, sidecar = episode
        _record(video, sid="at-123")
        quarantine_wrong_sidecar(sidecar, video, "shift")
        with open(sidecar, "w") as fh:
            fh.write(ASS.replace("Hallo", "Auch falsch"))
        record_subtitle_download("opensubtitles", "os-9", "de", "ass", video, 300)
        assert quarantine_wrong_sidecar(sidecar, video, "shift") is True

        assert is_suspect_sidecar(sidecar)
        with open(sidecar, "w") as fh:
            fh.write(ASS)
        assert is_suspect_sidecar(sidecar), "provider A's bytes are back"

    def test_a_flag_from_before_digests_is_judged_by_mtime(self, episode, no_arr):
        from db.models.core import BlacklistEntry
        from extensions import db

        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        entry = db.session.query(BlacklistEntry).one()
        entry.file_path = sidecar  # the pre-1.17.0 form: a bare path
        db.session.commit()
        suspect_sidecars.invalidate_cache()
        assert is_suspect_sidecar(sidecar)

        later = time.time() + 600
        os.utime(sidecar, (later, later))
        assert not is_suspect_sidecar(sidecar)

    def test_existing_ignores_a_suspect_ass(self, episode, no_arr):
        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")

        assert existing_ignoring_suspects(video, "de", "ass") is None

    def test_existing_falls_back_to_a_genuine_srt(self, episode, no_arr):
        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        srt = os.path.splitext(sidecar)[0] + ".srt"
        with open(srt, "w") as fh:
            fh.write(SRT)

        assert existing_ignoring_suspects(video, "de", "ass") == "srt"

    def test_without_suspects_existing_is_unchanged(self, episode):
        video, _ = episode
        assert existing_ignoring_suspects(video, "de", "ass") == "ass"
        assert existing_ignoring_suspects(video, "de", None) is None

    def test_wanted_scanner_does_not_let_a_suspect_ass_suppress_the_item(self, episode, no_arr):
        from services.wanted_item_scanner import _check_language_for_item

        video, sidecar = episode
        settings = MagicMock(upgrade_enabled=True)
        assert _check_language_for_item(video, "de", None, settings) is None

        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")

        result = _check_language_for_item(video, "de", None, settings)
        assert result is not None
        assert result["existing_sub"] == ""
        assert result["upgrade_candidate"] is False

    def test_search_does_not_skip_on_a_suspect_ass(self, episode, no_arr):
        from wanted_search.process import _check_existing_sidecar

        video, sidecar = episode
        settings = MagicMock(upgrade_enabled=True)
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        item_id = get_wanted_items_by_path(video)[0]["id"]

        assert _check_existing_sidecar({"file_path": video}, item_id, "de", settings) is None


class TestReplacement:
    def test_a_new_srt_retires_the_suspect_ass(self, episode, no_arr):
        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        new_srt = os.path.splitext(sidecar)[0] + ".srt"
        with open(new_srt, "w") as fh:
            fh.write(SRT)

        retire_suspect_siblings(new_srt, "de")

        assert not os.path.exists(sidecar)
        assert os.path.isfile(new_srt)

    def test_a_genuine_sibling_is_kept(self, episode):
        video, sidecar = episode
        new_srt = os.path.splitext(sidecar)[0] + ".srt"
        with open(new_srt, "w") as fh:
            fh.write(SRT)

        retire_suspect_siblings(new_srt, "de")

        assert os.path.isfile(sidecar)

    def test_save_subtitle_retires_the_suspect(self, episode, no_arr, monkeypatch):
        from providers.base import SubtitleFormat, SubtitleResult
        from providers.download_manager import save_subtitle

        video, sidecar = episode
        _record(video)
        quarantine_wrong_sidecar(sidecar, video, "shift")
        monkeypatch.setattr("security_utils.is_safe_path", lambda *a, **kw: True)
        result = SubtitleResult(
            provider_name="opensubtitles",
            subtitle_id="os-1",
            language="de",
            format=SubtitleFormat.SRT,
            content=SRT.encode(),
        )

        saved = save_subtitle(result, os.path.splitext(sidecar)[0] + ".srt")

        assert os.path.isfile(saved)
        assert not os.path.exists(sidecar)


class TestAutoSyncRunner:
    def _runner(self):
        from services.subtitle_automation_runner import SubtitleAutomationRunner

        return SubtitleAutomationRunner(repo=MagicMock())

    def test_a_rejected_shift_quarantines_the_sidecar(self):
        from services.video_sync import SyncShiftRejectedError

        err = SyncShiftRejectedError("shift 52000ms exceeds 45000ms", 52000)
        with (
            patch("services.video_sync.sync_with_ffsubsync", side_effect=err),
            patch("services.suspect_sidecars.quarantine_wrong_sidecar") as quarantine,
            pytest.raises(SyncShiftRejectedError),
        ):
            self._runner()._auto_sync("/m/ep.de.ass", "/m/ep.mkv")
        quarantine.assert_called_once()
        assert quarantine.call_args.args[:2] == ("/m/ep.de.ass", "/m/ep.mkv")

    def test_a_length_mismatch_quarantines_the_sidecar(self):
        from services.video_sync import SubtitleLengthMismatchError

        err = SubtitleLengthMismatchError("subtitle ends at 2738 s")
        with (
            patch("services.video_sync.sync_with_ffsubsync", side_effect=err),
            patch("services.suspect_sidecars.quarantine_wrong_sidecar") as quarantine,
            pytest.raises(SubtitleLengthMismatchError),
        ):
            self._runner()._auto_sync("/m/ep.de.ass", "/m/ep.mkv")
        quarantine.assert_called_once()

    def test_a_framerate_rejection_does_not(self):
        from services.video_sync import SyncSanityThresholdError

        err = SyncSanityThresholdError("framerate scale factor 1.043")
        with (
            patch("services.video_sync.sync_with_ffsubsync", side_effect=err),
            patch("services.suspect_sidecars.quarantine_wrong_sidecar") as quarantine,
            pytest.raises(SyncSanityThresholdError),
        ):
            self._runner()._auto_sync("/m/ep.de.ass", "/m/ep.mkv")
        quarantine.assert_not_called()


@pytest.mark.usefixtures("kept_on_disk")
class TestSuspectBlacklistIsPerVideo:
    """A subtitle wrong for S02E05 is the right one for S01E05.

    Prod (Clevatess): OpenSubtitles 11835856 is S01E05's subtitle and was saved
    for S02E05 too. Blocking it everywhere would keep it from S01E05, where it
    belongs; it is blocked for the video it did not fit.
    """

    def _quarantine(self, tmp_path, name, sid="os-11835856"):
        video = tmp_path / f"{name}.mkv"
        video.touch()
        sidecar = tmp_path / f"{name}.de.ass"
        sidecar.write_text(ASS)
        record_subtitle_download("opensubtitles", sid, "de", "ass", str(video), 96)
        assert quarantine_wrong_sidecar(str(sidecar), str(video), "shift 46600ms")
        return str(video)

    def test_blocked_only_for_the_video_it_did_not_fit(self, app_ctx, tmp_path, no_arr):
        from services.suspect_sidecars import blocks_result_for

        suspect_sidecars.invalidate_cache()
        wrong = self._quarantine(tmp_path, "Clevatess - S02E05")
        right = str(tmp_path / "Clevatess - S01E05.mkv")
        assert blocks_result_for("opensubtitles", "os-11835856", wrong) is True
        assert blocks_result_for("opensubtitles", "os-11835856", right) is False

    def test_a_second_video_it_did_not_fit_is_added(self, app_ctx, tmp_path, no_arr):
        from services.suspect_sidecars import blocks_result_for

        suspect_sidecars.invalidate_cache()
        first = self._quarantine(tmp_path, "Clevatess - S02E05")
        second = self._quarantine(tmp_path, "Clevatess - S03E05")
        assert blocks_result_for("opensubtitles", "os-11835856", first) is True
        assert blocks_result_for("opensubtitles", "os-11835856", second) is True
        assert is_suspect_sidecar(str(tmp_path / "Clevatess - S02E05.de.ass"))
        assert is_suspect_sidecar(str(tmp_path / "Clevatess - S03E05.de.ass"))

    def test_a_user_blacklist_entry_still_blocks_everywhere(self, app_ctx, tmp_path):
        from db.blacklist import add_blacklist_entry
        from services.suspect_sidecars import blocks_result_for

        suspect_sidecars.invalidate_cache()
        add_blacklist_entry("opensubtitles", "os-1", reason="bad translation")
        assert blocks_result_for("opensubtitles", "os-1", str(tmp_path / "any.mkv")) is True
        assert blocks_result_for("opensubtitles", "os-2", str(tmp_path / "any.mkv")) is False

    def test_the_user_blacklisting_it_blocks_it_everywhere(self, app_ctx, tmp_path, no_arr):
        # VM 191: POST /blacklist on a suspect entry answered 201 and changed
        # nothing; the subtitle stayed allowed for every other video.
        from services.suspect_sidecars import blocks_result_for

        suspect_sidecars.invalidate_cache()
        wrong = self._quarantine(tmp_path, "Clevatess - S02E05")
        response = app_ctx.test_client().post(
            "/api/v1/blacklist",
            json={"provider_name": "opensubtitles", "subtitle_id": "os-11835856", "reason": "bad"},
        )
        assert response.status_code == 201
        suspect_sidecars.invalidate_cache()

        other = str(tmp_path / "Clevatess - S01E05.mkv")
        assert blocks_result_for("opensubtitles", "os-11835856", other) is True
        assert blocks_result_for("opensubtitles", "os-11835856", wrong) is True
        assert is_suspect_sidecar(str(tmp_path / "Clevatess - S02E05.de.ass"))

    def test_search_filter_keeps_it_for_the_right_episode(self, app_ctx, tmp_path, no_arr):
        from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
        from providers.search_coordinator.scoring import _blacklisted

        suspect_sidecars.invalidate_cache()
        self._quarantine(tmp_path, "Clevatess - S02E05")
        result = SubtitleResult(
            provider_name="opensubtitles",
            subtitle_id="os-11835856",
            language="de",
            format=SubtitleFormat.ASS,
        )
        right = VideoQuery(file_path=str(tmp_path / "Clevatess - S01E05.mkv"))
        wrong = VideoQuery(file_path=str(tmp_path / "Clevatess - S02E05.mkv"))
        assert _blacklisted(result, right) is False
        assert _blacklisted(result, wrong) is True


def test_blacklist_api_lists_suspect_paths_without_flag_times(app_ctx, tmp_path, no_arr):
    from db.blacklist import get_blacklist_entries

    suspect_sidecars.invalidate_cache()
    for name in ("Clevatess - S02E05", "Clevatess - S03E05"):
        video = tmp_path / f"{name}.mkv"
        video.touch()
        (tmp_path / f"{name}.de.ass").write_text(ASS)
        record_subtitle_download("opensubtitles", "os-9", "de", "ass", str(video), 96)
        quarantine_wrong_sidecar(str(tmp_path / f"{name}.de.ass"), str(video), "shift")
    (entry,) = get_blacklist_entries()["data"]
    assert entry["file_path"] == (
        f"{tmp_path / 'Clevatess - S02E05.de.ass'}, {tmp_path / 'Clevatess - S03E05.de.ass'}"
    )
