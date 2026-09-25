"""An upgrade may not destroy the real subtitle it was meant to improve.

Prod 1.14.5, four days of logs (2026-09-21..25):

* 783 "Upgrade approved — SRT->ASS format upgrade", 730 of them to a LOWER
  score. OpenSubtitles results carry no format until they are downloaded, the
  ASS step lets UNKNOWN through, and Step 1 then judged the download as "ass"
  by fiat — a real SRT was deleted and replaced by another (worse) SRT, again
  on every scan, because the file was still an SRT afterwards.
* ``os.remove(old_srt)`` ran before ``save_subtitle``. When the save failed
  (animetosho, "Subtitle too large: 5815 KB > 5120 KB") the episode was left
  with no subtitle at all — Danganronpa S01E01/E02 lost their ``.en.srt``.
* A rejected upgrade returned without a backoff, so the item was re-searched
  with a full provider fan-out on every tick.
* Paths that bypass the Step-1 guard (sidecar translate, the automation drain,
  standalone items whose flag is not set) still machine-translated beside a
  real target subtitle — against the owner's rule that a self-made
  translation is always the last resort.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from providers.base import SubtitleFormat

_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo\n"
_ASS = b"[Script Info]\nScriptType: v4.00+\n"


def _touch(path, content=_SRT):
    path.write_bytes(content)
    return str(path)


def _ctx(video, *, content=_ASS, fmt=SubtitleFormat.ASS, save=None, upgrade=True):
    result = SimpleNamespace(
        content=content,
        score=300,
        provider_name="opensubtitles",
        subtitle_id="x1",
        format=fmt,
        score_breakdown={},
        language="de",
    )
    manager = MagicMock()
    manager.search_and_download_best.return_value = result

    def _save(res, output_path, series_id=None):
        with open(output_path, "wb") as fh:
            fh.write(res.content)
        return output_path

    manager.save_subtitle.side_effect = save or _save
    settings = MagicMock(
        upgrade_prefer_ass=True,
        upgrade_min_score_delta=0,
        upgrade_window_days=0,
        upgrade_protect_user_modified=True,
    )
    return {
        "item": {"id": 7, "sonarr_series_id": None},
        "item_id": 7,
        "item_lang": "de",
        "settings": settings,
        "manager": manager,
        "query": MagicMock(),
        "_pf": {"must_contain": [], "must_not_contain": []},
        "file_path": str(video),
        "is_upgrade": upgrade,
        "current_score": 150,
        "dry_run": False,
    }


@pytest.fixture
def fx():
    from wanted_search import process as proc

    with (
        patch.object(proc, "should_upgrade", return_value=(True, "ass beats srt")) as judge,
        patch.object(proc, "record_upgrade") as upgrade,
        patch.object(proc, "record_subtitle_download"),
        patch.object(proc, "delete_wanted_item"),
        patch.object(proc, "update_wanted_status"),
        patch.object(proc, "verify_dubtitle_on_keep", return_value=True),
        patch.object(proc, "_try_auto_sync"),
        patch("nfo_export.maybe_write_nfo"),
        patch("services.subtitle_restore.backup_before_replace"),
        patch("db.quality.is_user_modified", return_value=False) as guard,
        patch("db.quality.clear_user_modified"),
        patch("db.providers.get_latest_download_id", return_value=None),
        patch("services.wanted_search_runner.record_search_outcome") as outcome,
    ):
        yield SimpleNamespace(judge=judge, upgrade=upgrade, guard=guard, outcome=outcome)


class TestFormatIsCheckedAfterDownload:
    @pytest.mark.parametrize("fmt", [SubtitleFormat.SRT, SubtitleFormat.UNKNOWN])
    def test_an_srt_download_is_no_srt_to_ass_upgrade(self, tmp_path, fx, fmt):
        from wanted_search import process as proc

        video = tmp_path / "Show - S01E06.mkv"
        _touch(tmp_path / "Show - S01E06.de.srt", b"1\n00:00:01,000 --> 00:00:02,000\nEcht\n")
        ctx = _ctx(video, content=_SRT, fmt=fmt)

        assert proc._try_target_ass_direct(ctx) is None
        assert (tmp_path / "Show - S01E06.de.srt").read_bytes().endswith(b"Echt\n")
        assert not ctx["manager"].save_subtitle.called
        assert not fx.upgrade.called

    def test_a_real_ass_still_upgrades(self, tmp_path, fx):
        from wanted_search import process as proc

        video = tmp_path / "Show - S01E06.mkv"
        _touch(tmp_path / "Show - S01E06.de.srt")

        out = proc._try_target_ass_direct(_ctx(video, fmt=SubtitleFormat.UNKNOWN))

        assert out["status"] == "found"
        assert (tmp_path / "Show - S01E06.de.ass").exists()
        assert not (tmp_path / "Show - S01E06.de.srt").exists()


class TestOldSubtitleOutlivesAFailedSave:
    def test_a_failed_save_keeps_the_old_srt(self, tmp_path, fx):
        from wanted_search import process as proc

        def boom(*_a, **_kw):
            raise RuntimeError("Subtitle too large: 5815 KB > 5120 KB limit")

        video = tmp_path / "Danganronpa - S01E01.mkv"
        _touch(tmp_path / "Danganronpa - S01E01.de.srt")

        assert proc._try_target_ass_direct(_ctx(video, save=boom)) is None
        assert (tmp_path / "Danganronpa - S01E01.de.srt").exists(), "the real subtitle is gone"
        assert not fx.upgrade.called, "no upgrade happened, none may be recorded"


class TestRejectedUpgradeBacksOff:
    def test_score_rejection_books_a_miss(self, tmp_path, fx):
        from wanted_search import process as proc

        fx.judge.return_value = (False, "score delta too small")
        video = tmp_path / "Show - S01E01.mkv"
        _touch(tmp_path / "Show - S01E01.de.srt")

        out = proc._try_target_ass_direct(_ctx(video))

        assert out["status"] == "skipped"
        fx.outcome.assert_called_once_with(7, kind="no_result")

    def test_user_modified_rejection_books_a_miss(self, tmp_path, fx):
        from wanted_search import process as proc

        fx.guard.return_value = True
        video = tmp_path / "Show - S01E01.mkv"
        _touch(tmp_path / "Show - S01E01.de.srt")

        out = proc._try_target_ass_direct(_ctx(video))

        assert out["status"] == "skipped"
        fx.outcome.assert_called_once_with(7, kind="no_result")


class TestNoMachineTranslationBesideARealSubtitle:
    def _fallback_ctx(self, video):
        return {
            "item": {"id": 9, "sonarr_series_id": None},
            "item_id": 9,
            "item_lang": "de",
            "auto_translate": True,
            "file_path": str(video),
        }

    @pytest.mark.parametrize("name", ["Show - S01E01.de.srt", "Show - S01E01.ger.srt"])
    def test_translate_fallback_refuses_when_a_target_subtitle_exists(self, tmp_path, name):
        from wanted_search import process as proc

        video = tmp_path / "Show - S01E01.mkv"
        _touch(tmp_path / name)
        with (
            patch("translator.translate_file") as translate,
            patch.object(proc, "update_wanted_status"),
            patch("services.wanted_search_runner.record_search_outcome") as outcome,
        ):
            out = proc._fallback_translate_file(self._fallback_ctx(video))

        assert not translate.called
        assert out["status"] == "not_found"
        outcome.assert_called_once_with(9, kind="no_result")

    def test_a_real_target_subtitle_on_disk_stops_after_step_one(self, tmp_path):
        """Standalone rows carry existing_sub='srt' but no upgrade flag."""
        from wanted_search import process as proc

        video = tmp_path / "Show - S01E01.mkv"
        _touch(tmp_path / "Show - S01E01.de.srt")
        ctx = {
            "item": {"id": 42, "sonarr_series_id": None},
            "item_id": 42,
            "item_lang": "de",
            "file_path": str(video),
            "settings": MagicMock(wanted_skip_srt_on_no_ass=False),
            "auto_translate": True,
            "ass_had_results": False,
            "dry_run": False,
            "allow_translate_fallback": True,
            "is_upgrade": False,
        }
        with (
            patch.object(proc, "_try_target_ass_direct", return_value=None),
            patch.object(proc, "_try_source_ass_translation") as s2,
            patch.object(proc, "_try_target_srt_direct") as s3,
            patch.object(proc, "_fallback_translate_file") as s5,
            patch.object(proc, "update_wanted_status"),
            patch("services.wanted_search_runner.record_search_outcome"),
        ):
            out = proc._run_search_steps(ctx)

        assert out["status"] == "not_found"
        assert not (s2.called or s3.called or s5.called)


def test_mt_reseek_still_searches_past_step_one(tmp_path):
    """mt_reseek's on-disk target IS the machine translation it re-seeks against."""
    from wanted_search import process as proc

    video = tmp_path / "Show - S01E01.mkv"
    _touch(tmp_path / "Show - S01E01.de.srt")
    ctx = {
        "item": {"id": 42, "sonarr_series_id": None},
        "item_id": 42,
        "item_lang": "de",
        "file_path": str(video),
        "settings": MagicMock(wanted_skip_srt_on_no_ass=False),
        "auto_translate": False,
        "ass_had_results": False,
        "dry_run": True,
        "allow_translate_fallback": True,
        "is_upgrade": False,
        "target_on_disk_is_mt": True,
    }
    with (
        patch.object(proc, "_try_target_ass_direct", return_value=None),
        patch.object(proc, "_try_target_srt_direct", return_value={"status": "found"}) as s3,
    ):
        out = proc._run_search_steps(ctx)

    assert s3.called and out["status"] == "found"
