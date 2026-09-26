"""Owner decision 2026-09-26: a sync keeps a genuine sidecar genuine.

Auto-sync (and a manual sync) rewrites the sidecar in place after its
download was recorded. The real-sidecar check reads a sidecar written more
than a minute after its record as "replaced by a writer that keeps no
history" - correct for translations, wrong for a sync of the same file. So
every sync writer vouches for the sidecar BEFORE it rewrites it and, only if
it was genuine then, records a ``resync`` origin after a successful rewrite.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from services.foreign_tracks.sidecars import real_sidecar_languages

_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHallo\n"
_SYNCED = "1\n00:00:01,500 --> 00:00:02,500\nHallo\n"


def _record(video, lang="de", *, fmt="srt", age_s=600, source="provider", provider="subdl"):
    from db.models.providers import SubtitleDownload
    from extensions import db

    db.session.add(
        SubtitleDownload(
            provider_name=provider,
            subtitle_id="x",
            language=lang,
            format=fmt,
            file_path=str(video),
            score=100,
            source=source,
            downloaded_at=datetime.now(UTC) - timedelta(seconds=age_s),
        )
    )
    db.session.commit()


def _setup(tmp_path, name="Show - S01E01.de.srt", age_s=600):
    """A video and its sidecar, written ``age_s`` ago (when it was downloaded)."""
    video = tmp_path / "Show - S01E01.mkv"
    video.write_bytes(b"v")
    sidecar = tmp_path / name
    sidecar.write_text(_SRT, encoding="utf-8")
    stamp = time.time() - age_s
    os.utime(sidecar, (stamp, stamp))
    return str(video), str(sidecar)


def _rewrite(sidecar):
    with open(sidecar, "w", encoding="utf-8") as fh:
        fh.write(_SYNCED)


def _origins(video):
    from db.models.providers import SidecarOrigin
    from extensions import db

    return [o.origin for o in db.session.query(SidecarOrigin).filter_by(video_path=video).all()]


# --- the two primitives ------------------------------------------------------


def test_without_carrying_a_rewrite_makes_a_real_download_unknown(app_ctx, tmp_path):
    """The defect: the sync's rewrite alone costs the download its standing."""
    video, sidecar = _setup(tmp_path)
    _record(video)
    assert real_sidecar_languages(video, {"de"}) == {"de"}
    _rewrite(sidecar)
    assert real_sidecar_languages(video, {"de"}) == set()


def test_a_genuine_sidecar_stays_genuine_through_a_rewrite(app_ctx, tmp_path):
    from services.foreign_tracks.sidecars import carry_origin_after_rewrite, vouch_before_rewrite

    video, sidecar = _setup(tmp_path)
    _record(video)
    vouch = vouch_before_rewrite(sidecar)
    _rewrite(sidecar)
    carry_origin_after_rewrite(vouch)
    assert _origins(video) == ["resync"]
    assert real_sidecar_languages(video, {"de"}) == {"de"}


def test_an_unknown_sidecar_is_not_made_genuine_by_a_rewrite(app_ctx, tmp_path):
    from services.foreign_tracks.sidecars import carry_origin_after_rewrite, vouch_before_rewrite

    video, sidecar = _setup(tmp_path)
    vouch = vouch_before_rewrite(sidecar)
    _rewrite(sidecar)
    carry_origin_after_rewrite(vouch)
    assert vouch is None
    assert _origins(video) == []
    assert real_sidecar_languages(video, {"de"}) == set()


def test_a_machine_translation_is_not_carried(app_ctx, tmp_path):
    from services.foreign_tracks.sidecars import carry_origin_after_rewrite, vouch_before_rewrite

    video, sidecar = _setup(tmp_path)
    _record(video, source="machine_translation", provider="translation")
    vouch = vouch_before_rewrite(sidecar)
    _rewrite(sidecar)
    carry_origin_after_rewrite(vouch)
    assert _origins(video) == []
    assert real_sidecar_languages(video, {"de"}) == set()


def test_a_sidecar_that_was_not_rewritten_records_nothing(app_ctx, tmp_path):
    """A failed or no-op sync leaves the file alone - nothing to vouch for."""
    from services.foreign_tracks.sidecars import carry_origin_after_rewrite, vouch_before_rewrite

    video, sidecar = _setup(tmp_path)
    _record(video)
    carry_origin_after_rewrite(vouch_before_rewrite(sidecar))
    assert _origins(video) == []


def test_a_forced_sidecar_is_never_vouched(app_ctx, tmp_path):
    from services.foreign_tracks.sidecars import vouch_before_rewrite

    video, sidecar = _setup(tmp_path, name="Show - S01E01.de.forced.srt")
    _record(video)
    assert vouch_before_rewrite(sidecar) is None


def test_a_sidecar_without_a_video_is_never_vouched(app_ctx, tmp_path):
    from services.foreign_tracks.sidecars import vouch_before_rewrite

    sidecar = tmp_path / "Lonely.de.srt"
    sidecar.write_text(_SRT, encoding="utf-8")
    assert vouch_before_rewrite(str(sidecar)) is None


def test_a_newer_machine_translation_still_wins_over_a_resync(app_ctx, tmp_path):
    from services.foreign_tracks.sidecars import carry_origin_after_rewrite, vouch_before_rewrite

    video, sidecar = _setup(tmp_path)
    _record(video)
    vouch = vouch_before_rewrite(sidecar)
    _rewrite(sidecar)
    carry_origin_after_rewrite(vouch)
    _record(video, source="machine_translation", provider="translation", age_s=-5)
    assert real_sidecar_languages(video, {"de"}) == set()


def test_an_alias_named_sidecar_is_carried(app_ctx, tmp_path):
    from services.foreign_tracks.sidecars import carry_origin_after_rewrite, vouch_before_rewrite

    video, sidecar = _setup(tmp_path, name="Show - S01E01.ger.srt")
    _record(video)
    vouch = vouch_before_rewrite(sidecar)
    _rewrite(sidecar)
    carry_origin_after_rewrite(vouch)
    assert real_sidecar_languages(video, {"de"}) == {"de"}


# --- every sync writer carries it ---------------------------------------------


class _Proc:
    returncode = 0
    stdout = "offset 0.5 s applied"
    stderr = ""


def _fake_run(cmd, *a, **kw):
    # Every writer passes its output file as the last argument: the legacy
    # wrappers a temp file they then copy over the sidecar, the engines the
    # sidecar itself.
    _rewrite(cmd[-1])
    return _Proc()


@pytest.mark.parametrize(
    "writer", ["legacy_ffsubsync", "legacy_alass", "orchestrator_ffsubsync", "orchestrator_alass"]
)
def test_every_sync_writer_keeps_a_download_genuine(app_ctx, tmp_path, monkeypatch, writer):
    video, sidecar = _setup(tmp_path)
    _record(video)
    reference = str(tmp_path / "ref.en.srt")
    with open(reference, "w", encoding="utf-8") as fh:
        fh.write(_SRT)

    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("subprocess.run", _fake_run)
    with (
        patch("services.video_sync.run_trigger"),
        patch("services.sync_engines.ffsubsync_engine._fire_after_sync_trigger"),
        patch("services.sync_engines.alass_engine._fire_after_sync_trigger"),
    ):
        if writer == "legacy_ffsubsync":
            from services.video_sync import sync_with_ffsubsync

            sync_with_ffsubsync(sidecar, video)
        elif writer == "legacy_alass":
            from services.video_sync import sync_with_alass

            sync_with_alass(sidecar, reference)
        elif writer == "orchestrator_ffsubsync":
            from services.sync_engines.ffsubsync_engine import FfsubsyncEngine
            from services.sync_engines.orchestrator import SyncOrchestrator

            with patch("services.sync_engines.orchestrator.write_sync_job_run"):
                assert SyncOrchestrator([FfsubsyncEngine()]).sync(sidecar, video).ok
        else:
            from services.sync_engines.alass_engine import AlassEngine
            from services.sync_engines.orchestrator import SyncOrchestrator

            with patch("services.sync_engines.orchestrator.write_sync_job_run"):
                assert SyncOrchestrator([AlassEngine()]).sync(sidecar, reference).ok

    with open(sidecar, encoding="utf-8") as fh:
        assert fh.read() == _SYNCED, "the fake sync must really have rewritten the sidecar"
    assert real_sidecar_languages(video, {"de"}) == {"de"}


def test_a_rejected_mis_shift_is_not_carried(app_ctx, tmp_path, monkeypatch):
    """The engine rewrites in place, then the orchestrator rejects the offset:
    the rewritten file must not read as genuine."""
    from services.sync_engines.base import SyncResult
    from services.sync_engines.orchestrator import SyncOrchestrator

    video, sidecar = _setup(tmp_path)
    _record(video)

    class _Wild:
        name = "wild"

        def is_available(self):
            return True

        def sync(self, subtitle_path, video_path):
            _rewrite(subtitle_path)
            return SyncResult(engine="wild", ok=True, offset_ms=900_000, duration_ms=1)

    with patch("services.sync_engines.orchestrator.write_sync_job_run"):
        assert not SyncOrchestrator([_Wild()], sanity_threshold_ms=60_000).sync(sidecar, video).ok
    assert _origins(video) == []
    assert real_sidecar_languages(video, {"de"}) == set()


# --- restores never inherit a record's standing --------------------------------


def _bak_with(sidecar, text):
    from subtitle_filename import bak_path_for

    bak = bak_path_for(sidecar)
    os.makedirs(os.path.dirname(bak), exist_ok=True)
    with open(bak, "w", encoding="utf-8") as fh:
        fh.write(text)
    # A .bak made at download time carries that moment as its mtime.
    stamp = time.time() - 600
    os.utime(bak, (stamp, stamp))
    return bak


def test_a_restored_backup_is_not_genuine(app_ctx, tmp_path):
    """The .bak of the first download over a machine translation IS the
    translation. Restoring it keeps the .bak's mtime, which sits inside the
    download record's window — without a marker it read as the download."""
    from services.subtitle_restore import restore_from_bak

    video, sidecar = _setup(tmp_path)
    _record(video)
    _bak_with(sidecar, "1\n00:00:01,000 --> 00:00:02,000\nMaschine\n")
    restore_from_bak(sidecar)
    assert "restored" in _origins(video)
    assert real_sidecar_languages(video, {"de"}) == set()


def test_a_restored_mt_sidecar_is_not_genuine(app_ctx, tmp_path):
    from services import mt_sidecars

    video, sidecar = _setup(tmp_path)
    trashed = str(tmp_path / "trash.srt")
    os.replace(sidecar, trashed)
    _record(video)
    mt_sidecars.restore([(sidecar, trashed)])
    assert _origins(video) == ["restored"]
    assert real_sidecar_languages(video, {"de"}) == set()


def test_mark_restored_ignores_a_file_without_a_video(app_ctx, tmp_path):
    from services.foreign_tracks.sidecars import mark_restored

    lonely = tmp_path / "Lonely.de.srt"
    lonely.write_text(_SRT, encoding="utf-8")
    mark_restored(str(lonely))  # must not raise
