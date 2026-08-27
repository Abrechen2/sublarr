"""The sync backup is the same single-slot undo as everywhere else.

Two production defects pinned here, found 2026-08-27 on Cardinal:

1. ``video_sync._make_backup`` overwrote an existing ``.bak`` on every sync
   run. The bak is a single-slot undo of the *original* text (see
   tests/test_processing_bak_is_never_overwritten.py for the incident that
   rule comes from) — a sync run must not replace it with already-processed
   content.

2. The overwrite used ``shutil.copy2`` onto bak files created in the
   PUID=1000 era while the app now runs as uid 99. ``copy2`` writes the
   content (other-write bit was set), then dies in ``copystat``/``utime``
   with ``[Errno 1] Operation not permitted`` — 53 auto_sync queue items
   failed daily for weeks, corrupting their own bak on every attempt.
   ``atomic_copyfile`` sidesteps dst ownership entirely: a temp file next to
   dst plus ``os.replace`` needs only directory write permission.
"""

import os
import shutil
import stat

import pytest

# ── utils.atomic_write.atomic_copyfile ───────────────────────────────────────


class TestAtomicCopyfile:
    def test_copies_content_to_new_file(self, tmp_path):
        from utils.atomic_write import atomic_copyfile

        src = tmp_path / "src.srt"
        src.write_text("hello", encoding="utf-8")
        dst = tmp_path / "dst.srt"

        atomic_copyfile(str(src), str(dst))

        assert dst.read_text(encoding="utf-8") == "hello"

    def test_replaces_dst_it_could_not_open_for_write(self, tmp_path):
        """A read-only dst breaks copy2 but not the atomic path.

        Stand-in for the real incident (dst owned by another uid): both cases
        make ``open(dst, "wb")``/``utime(dst)`` fail while the directory
        rename is still allowed.
        """
        from utils.atomic_write import atomic_copyfile

        src = tmp_path / "src.srt"
        src.write_text("new content", encoding="utf-8")
        dst = tmp_path / "dst.srt"
        dst.write_text("old content", encoding="utf-8")
        os.chmod(dst, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444

        with pytest.raises(PermissionError):
            shutil.copy2(str(src), str(dst))  # documents why copy2 is banned

        atomic_copyfile(str(src), str(dst))

        assert dst.read_text(encoding="utf-8") == "new content"

    def test_missing_src_raises_and_leaves_no_tmp(self, tmp_path):
        from utils.atomic_write import atomic_copyfile

        dst = tmp_path / "dst.srt"
        with pytest.raises(FileNotFoundError):
            atomic_copyfile(str(tmp_path / "missing.srt"), str(dst))

        assert not dst.exists()
        assert [p.name for p in tmp_path.iterdir()] == []

    def test_result_is_world_readable(self, tmp_path):
        """mkstemp creates 0600; the sidecar/bak must end up media-server readable."""
        from utils.atomic_write import atomic_copyfile

        src = tmp_path / "src.srt"
        src.write_text("x", encoding="utf-8")
        dst = tmp_path / "dst.srt"

        atomic_copyfile(str(src), str(dst))

        assert os.stat(dst).st_mode & stat.S_IROTH


# ── subtitle_restore.create_or_get_bak ───────────────────────────────────────


class TestCreateOrGetBak:
    def test_returns_existing_bak_untouched(self, tmp_path):
        from services.subtitle_restore import create_or_get_bak
        from subtitle_filename import bak_path_for

        active = tmp_path / "Show - S01E01.de.srt"
        active.write_text("current, already synced", encoding="utf-8")
        existing = bak_path_for(str(active))
        os.makedirs(os.path.dirname(existing), exist_ok=True)
        with open(existing, "w", encoding="utf-8") as f:
            f.write("pristine original")

        assert create_or_get_bak(str(active)) == existing
        assert open(existing, encoding="utf-8").read() == "pristine original"

    def test_legacy_bak_counts_as_existing(self, tmp_path):
        """A pre-migration sibling .bak must not be shadowed by a fresh one."""
        from services.subtitle_restore import create_or_get_bak
        from subtitle_filename import legacy_bak_path_for

        active = tmp_path / "Show - S01E01.de.srt"
        active.write_text("mangled by pipeline", encoding="utf-8")
        legacy = legacy_bak_path_for(str(active))
        os.makedirs(os.path.dirname(legacy), exist_ok=True)
        with open(legacy, "w", encoding="utf-8") as f:
            f.write("pristine original")

        assert create_or_get_bak(str(active)) == legacy
        assert open(legacy, encoding="utf-8").read() == "pristine original"

    def test_creates_bak_when_missing(self, tmp_path):
        from services.subtitle_restore import create_or_get_bak
        from subtitle_filename import bak_path_for

        active = tmp_path / "Show - S01E01.de.srt"
        active.write_text("original text", encoding="utf-8")

        bak = create_or_get_bak(str(active))

        assert bak == bak_path_for(str(active))
        assert open(bak, encoding="utf-8").read() == "original text"

    def test_missing_active_raises(self, tmp_path):
        from services.subtitle_restore import create_or_get_bak

        with pytest.raises(OSError):
            create_or_get_bak(str(tmp_path / "missing.de.srt"))


# ── video_sync._make_backup goes through the single-slot path ────────────────


class TestVideoSyncMakeBackup:
    def test_existing_bak_survives_a_sync_backup(self, tmp_path):
        from services.video_sync import _make_backup
        from subtitle_filename import bak_path_for

        active = tmp_path / "Show - S01E01.de.srt"
        active.write_text("shifted by ffsubsync", encoding="utf-8")
        existing = bak_path_for(str(active))
        os.makedirs(os.path.dirname(existing), exist_ok=True)
        with open(existing, "w", encoding="utf-8") as f:
            f.write("pristine original")

        assert _make_backup(str(active)) == existing
        assert open(existing, encoding="utf-8").read() == "pristine original"

    def test_creates_bak_when_missing(self, tmp_path):
        from services.video_sync import _make_backup

        active = tmp_path / "Show - S01E01.de.srt"
        active.write_text("original text", encoding="utf-8")

        bak = _make_backup(str(active))

        assert open(bak, encoding="utf-8").read() == "original text"


# ── the sync engines share the same semantics ────────────────────────────────


@pytest.mark.parametrize("engine_module", ["ffsubsync_engine", "alass_engine"])
def test_engine_backup_preserves_existing_bak(tmp_path, engine_module, monkeypatch):
    """Both engine backup steps must reuse the single-slot primitive.

    Import-level check plus behaviour: the engines' backup helper must leave
    an existing bak untouched.
    """
    import importlib

    mod = importlib.import_module(f"services.sync_engines.{engine_module}")
    from subtitle_filename import bak_path_for

    active = tmp_path / "Show - S01E01.de.srt"
    active.write_text("about to be shifted", encoding="utf-8")
    existing = bak_path_for(str(active))
    os.makedirs(os.path.dirname(existing), exist_ok=True)
    with open(existing, "w", encoding="utf-8") as f:
        f.write("pristine original")

    mod._backup_before_sync(str(active))

    assert open(existing, encoding="utf-8").read() == "pristine original"
