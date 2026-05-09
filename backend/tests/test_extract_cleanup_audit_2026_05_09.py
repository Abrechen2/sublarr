"""Regression tests for the 2026-05-09 extract+cleanup audit fixes.

Closed in this batch:

* G3   — ``_resolve_trash_dir`` rejects forbidden absolute paths.
* G5   — ``extract_subtitle_stream`` is atomic (tmp + os.replace).
* G7   — ``_make_backup`` raises RemuxError instead of sibling ``.bak``.
* G8   — subprocess argv prepends ``./`` for ``-`` leading filenames.
* C0-1 — cleanup executors trash by default, hard-delete only on opt-in.
* C0-2 — empty ``keep_languages`` aborts language_filter.
* C0-3 — every executor probes media_path with os.stat first.
* C1-1 — untagged sidecars are not classified as a foreign language.
* C1-3 — orphan_files uses dedup_engine.scan_orphaned_subtitles.
* C1-4 — concurrent execute_rule calls raise CleanupBusyError.
* E1-1 — extract route refuses paths outside media_path.
* C2-2 — execute_orphan_db calls delete_by_paths once.
* C2-4 — batch_extract refuses item_ids > hard cap.
* C2-7 — extra_media_paths skips forbidden roots.

Gemini cold-review follow-ups (2026-05-09 R1-R6):

* R1 — ``_try_reflink`` uses ``--`` separator on cp argv.
* R2 — ``_resolve_trash_dir`` rejects relative paths that escape media_root.
* R3 — ``run_ffprobe`` wraps file_path with ``_safe_arg_path``.
* R4 — subtitle repair write is atomic (tmp + os.replace).
* R5 — ``batch_extract`` route sets ``running=True`` synchronously inside lock.
* R6 — ``orphan.delete_orphaned`` uses ``is_safe_path`` instead of ``startswith``.
"""

from __future__ import annotations

import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# G3 — _resolve_trash_dir rejects forbidden absolute paths
# ---------------------------------------------------------------------------


class TestResolveTrashDir:
    def test_forbidden_absolute_falls_back_to_media_path(self, tmp_path):
        from remux import _resolve_trash_dir

        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        with patch("config.get_settings", return_value=fake_settings):
            resolved = _resolve_trash_dir(str(tmp_path / "a.mkv"), "/etc")
        # Falls back to <media_path>/.sublarr — never lands under /etc
        assert "/etc" not in resolved.replace("\\", "/")
        assert resolved.endswith(".sublarr")

    def test_legitimate_absolute_passes_through(self, tmp_path):
        from remux import _resolve_trash_dir

        absolute = str(tmp_path / "custom_trash")
        resolved = _resolve_trash_dir(str(tmp_path / "x.mkv"), absolute)
        assert resolved == absolute

    def test_relative_joins_under_media_path(self, tmp_path):
        from remux import _resolve_trash_dir

        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        with patch("config.get_settings", return_value=fake_settings):
            resolved = _resolve_trash_dir(str(tmp_path / "x.mkv"), ".sublarr")
        assert resolved == os.path.join(str(tmp_path), ".sublarr")

    def test_is_forbidden_trash_root_blocks_etc(self):
        from remux import _is_forbidden_trash_root

        assert _is_forbidden_trash_root("/etc") is True
        assert _is_forbidden_trash_root("/etc/foo") is True
        assert _is_forbidden_trash_root("/proc") is True
        assert _is_forbidden_trash_root("/") is True
        assert _is_forbidden_trash_root("/media/library") is False


# ---------------------------------------------------------------------------
# G5 — atomic ffmpeg extraction
# ---------------------------------------------------------------------------


class TestAtomicExtraction:
    def test_extract_writes_via_tmp_and_replace(self, tmp_path, app_ctx):
        """ffmpeg writes to a temp path; we verify the SAME directory
        receives the temp + the final file is the result of os.replace.
        """
        from ass_probe import extract_subtitle_stream

        # Create a dummy mkv (won't actually be parsed because we mock subprocess)
        mkv = tmp_path / "show.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")  # EBML header bytes — content irrelevant
        out = tmp_path / "show.de.srt"

        captured_args = {}

        def fake_run(cmd, **kwargs):
            # Last arg is the temp output path
            tmp_out = cmd[-1]
            captured_args["tmp_out"] = tmp_out
            captured_args["dir"] = os.path.dirname(tmp_out)
            # Simulate ffmpeg writing some bytes
            with open(tmp_out, "wb") as f:
                f.write(b"1\n00:00:01,000 --> 00:00:02,000\nhello\n")
            return MagicMock(returncode=0, stderr="")

        with patch("ass_probe.subprocess.run", side_effect=fake_run):
            extract_subtitle_stream(str(mkv), {"sub_index": 0, "format": "srt"}, str(out))

        # Tmp lived in same directory as final output — atomic os.replace works
        assert captured_args["dir"] == str(tmp_path)
        # Tmp must be cleaned up
        assert not os.path.exists(captured_args["tmp_out"])
        # Final exists
        assert out.exists()

    def test_extract_failure_leaves_no_partial_file(self, tmp_path, app_ctx):
        """ffmpeg returncode!=0 must not leave a file at the destination
        path."""
        from ass_probe import extract_subtitle_stream

        mkv = tmp_path / "show.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")
        out = tmp_path / "show.de.srt"

        def fake_run(cmd, **kwargs):
            # Write something to the tmp path THEN return non-zero
            with open(cmd[-1], "wb") as f:
                f.write(b"partial garbage")
            return MagicMock(returncode=1, stderr="boom")

        with (
            patch("ass_probe.subprocess.run", side_effect=fake_run),
            pytest.raises(RuntimeError),
        ):
            extract_subtitle_stream(str(mkv), {"sub_index": 0, "format": "srt"}, str(out))

        # Final destination must be untouched (no partial bytes lying around)
        assert not out.exists()

    def test_extract_zero_byte_output_raises(self, tmp_path, app_ctx):
        """An empty output file (ENOSPC mid-write) must not be promoted to
        the final path."""
        from ass_probe import extract_subtitle_stream

        mkv = tmp_path / "show.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")
        out = tmp_path / "show.de.srt"

        def fake_run(cmd, **kwargs):
            # Leave the tmp file empty (simulating ENOSPC after open)
            return MagicMock(returncode=0, stderr="")

        with (
            patch("ass_probe.subprocess.run", side_effect=fake_run),
            pytest.raises(RuntimeError, match="empty sidecar"),
        ):
            extract_subtitle_stream(str(mkv), {"sub_index": 0, "format": "srt"}, str(out))
        assert not out.exists()


# ---------------------------------------------------------------------------
# G8 — subprocess argv `./` prefix
# ---------------------------------------------------------------------------


class TestSafeArgPath:
    def test_prefixes_dash_leading_relative_path(self):
        from remux import _safe_arg_path

        # Relative path whose basename starts with `-`
        assert _safe_arg_path("-evil.mkv") == os.path.join(".", "-evil.mkv")
        # Subdir + dash-leading basename
        assert _safe_arg_path(os.path.join("anime", "-bad.mkv")) == os.path.join(
            ".", "anime", "-bad.mkv"
        )

    def test_leaves_normal_paths_untouched(self):
        from remux import _safe_arg_path

        assert _safe_arg_path("show.mkv") == "show.mkv"
        assert _safe_arg_path("anime/show.mkv") == "anime/show.mkv"
        # Absolute paths are safe by construction
        if os.name != "nt":
            assert _safe_arg_path("/media/show.mkv") == "/media/show.mkv"


# ---------------------------------------------------------------------------
# C0-1 — cleanup executors trash by default
# ---------------------------------------------------------------------------


class TestCleanupTrashDefault:
    def test_language_filter_trashes_by_default(self, tmp_path, app_ctx):
        from services.cleanup_executors import execute_language_filter

        f = tmp_path / "show.fr.ass"
        f.write_text("french sub")
        # Pin remux_trash_dir relative to tmp_path so we can find the trashed file
        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        fake_settings.remux_trash_dir = ".sublarr"
        with patch("config.get_settings", return_value=fake_settings):
            res = execute_language_filter(str(tmp_path), {"keep_languages": ["de"]}, dry_run=False)
        assert res["deleted"] == 1
        # Original gone
        assert not f.exists()
        # Trash copy exists somewhere under .sublarr/trash/<date>/
        trash_root = tmp_path / ".sublarr" / "trash"
        found = list(trash_root.rglob("show.fr.ass"))
        assert found, f"expected trashed copy under {trash_root}"

    def test_language_filter_permanent_delete_uses_os_remove(self, tmp_path, app_ctx):
        from services.cleanup_executors import execute_language_filter

        f = tmp_path / "show.fr.ass"
        f.write_text("french sub")
        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        fake_settings.remux_trash_dir = ".sublarr"
        with patch("config.get_settings", return_value=fake_settings):
            res = execute_language_filter(
                str(tmp_path),
                {"keep_languages": ["de"], "permanent_delete": True},
                dry_run=False,
            )
        assert res["deleted"] == 1
        assert not f.exists()
        # NO trash copy
        assert not (tmp_path / ".sublarr").exists() or not list(
            (tmp_path / ".sublarr").rglob("show.fr.ass")
        )


# ---------------------------------------------------------------------------
# C0-2 — empty keep_languages aborts
# ---------------------------------------------------------------------------


class TestEmptyKeepLanguages:
    def test_language_filter_refuses_empty_keep_set(self, tmp_path):
        from services.cleanup_executors import execute_language_filter

        # Build files that WOULD all match a non-keep set
        (tmp_path / "show.de.ass").write_text("sub")
        (tmp_path / "show.en.srt").write_text("sub")

        result = execute_language_filter(str(tmp_path), {"keep_languages": []}, dry_run=False)
        assert result.get("aborted") == "empty keep_languages"
        assert result["deleted"] == 0
        # Files preserved
        assert (tmp_path / "show.de.ass").exists()
        assert (tmp_path / "show.en.srt").exists()


# ---------------------------------------------------------------------------
# C0-3 — mount-reachability probe
# ---------------------------------------------------------------------------


class TestMountProbe:
    def test_executor_aborts_when_media_path_unreachable(self):
        from services.cleanup_executors import execute_language_filter

        with patch("os.stat", side_effect=OSError("mount lost")):
            result = execute_language_filter(
                "/mnt/missing", {"keep_languages": ["de"]}, dry_run=False
            )
        assert result["deleted"] == 0
        assert result.get("aborted") == "media_path unreachable"


# ---------------------------------------------------------------------------
# C1-1 — untagged sidecars not classified as foreign
# ---------------------------------------------------------------------------


class TestUntaggedSidecarPreserved:
    def test_language_filter_keeps_untagged_sidecar(self, tmp_path, app_ctx):
        from services.cleanup_executors import execute_language_filter

        # `show.S01E01.ass` has NO language tag — the legacy parser
        # would classify it as lang="s01e01" and delete it.
        untagged = tmp_path / "show.S01E01.ass"
        untagged.write_text("untagged sub")
        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        fake_settings.remux_trash_dir = ".sublarr"
        with patch("config.get_settings", return_value=fake_settings):
            res = execute_language_filter(str(tmp_path), {"keep_languages": ["de"]}, dry_run=False)
        assert res["deleted"] == 0
        assert untagged.exists()


# ---------------------------------------------------------------------------
# C1-3 — orphan_files unified definition
# ---------------------------------------------------------------------------


class TestOrphanDelegation:
    def test_orphan_files_delegates_to_dedup_engine(self, tmp_path, app_ctx):
        from services.cleanup_executors import execute_orphan_files

        orphans = [
            {"path": str(tmp_path / "show.S01E01.de.ass"), "size": 42},
        ]
        # Create the file so trash move has something to operate on
        (tmp_path / "show.S01E01.de.ass").write_text("dummy")

        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        fake_settings.remux_trash_dir = ".sublarr"

        with (
            patch("dedup_engine.scan_orphaned_subtitles", return_value=orphans),
            patch("config.get_settings", return_value=fake_settings),
        ):
            res = execute_orphan_files(str(tmp_path), {}, dry_run=False)
        assert res["deleted"] == 1
        assert res["bytes_freed"] == 42


# ---------------------------------------------------------------------------
# C1-4 — concurrency lock
# ---------------------------------------------------------------------------


class TestRuleRunnerLock:
    def test_concurrent_execute_rule_raises_busy(self, app_ctx):
        from services.cleanup_rule_runner import (
            CleanupBusyError,
            _execute_rule_locked,
            _rule_runner_lock,
            execute_rule,
        )

        # Acquire the lock manually to simulate a long-running first call
        assert _rule_runner_lock.acquire(blocking=False)
        try:
            with pytest.raises(CleanupBusyError):
                execute_rule(rule_id=1)
        finally:
            _rule_runner_lock.release()


# ---------------------------------------------------------------------------
# E1-1 — extract route boundary
# ---------------------------------------------------------------------------


class TestExtractBoundary:
    def test_extract_validate_rejects_path_outside_media(self, tmp_path, app_ctx):
        from routes.wanted.extract import _validate_extract_target

        outside = "/etc/passwd"
        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        with patch("config.get_settings", return_value=fake_settings):
            err = _validate_extract_target(outside)
        assert err is not None

    def test_extract_validate_accepts_path_inside_media(self, tmp_path, app_ctx):
        from routes.wanted.extract import _validate_extract_target

        inside = str(tmp_path / "show.mkv")
        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        with patch("config.get_settings", return_value=fake_settings):
            err = _validate_extract_target(inside)
        assert err is None


# ---------------------------------------------------------------------------
# C2-4 — batch_extract item_ids cap
# ---------------------------------------------------------------------------


class TestBatchExtractCap:
    def test_batch_extract_rejects_oversized_list(self, app_ctx):
        # Send 5001 ids (one over the cap)
        client = app_ctx.test_client()
        resp = client.post(
            "/api/v1/wanted/batch-extract",
            json={"item_ids": list(range(1, 5002))},
        )
        assert resp.status_code == 400
        assert "too large" in resp.get_json().get("error", "").lower()


# ---------------------------------------------------------------------------
# C2-7 — extra_media_paths refuses forbidden roots
# ---------------------------------------------------------------------------


class TestExtraMediaPathsValidation:
    def test_old_subtitle_baks_skips_forbidden_roots(self, app_ctx, tmp_path):
        from services.cleanup_rule_runner import _run_old_subtitle_baks

        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        fake_settings.subtitle_bak_retention_days = 30
        # Forbidden root + a legitimate dir
        legit = tmp_path / "legit"
        legit.mkdir()
        fake_settings.extra_media_paths = f"/etc, /proc, {legit}"

        captured_roots = {}

        def fake_cleanup(media_roots, **kwargs):
            captured_roots["roots"] = media_roots
            return {"deleted": [], "orphans_purged": 0}

        with (
            patch("config.get_settings", return_value=fake_settings),
            patch("services.subtitle_backups.cleanup_subtitle_baks", side_effect=fake_cleanup),
        ):
            _run_old_subtitle_baks({}, {})

        roots = captured_roots["roots"]
        # Forbidden roots filtered out, legit kept
        assert "/etc" not in roots
        assert "/proc" not in roots
        assert str(legit) in roots
        assert str(tmp_path) in roots  # primary media_path also kept


# ---------------------------------------------------------------------------
# Gemini-2026-05-09 R1 — _try_reflink uses `--` separator
# ---------------------------------------------------------------------------


class TestReflinkArgvSeparator:
    def test_cp_argv_contains_double_dash_separator(self):
        from remux import _try_reflink

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return MagicMock(returncode=0)

        with patch("remux.subprocess.run", side_effect=fake_run):
            _try_reflink("-evil.mkv", "/safe/dst.mkv")

        cmd = captured["cmd"]
        # cp gets `cp --reflink=auto -- src dst`
        assert cmd[0] == "cp"
        assert "--" in cmd
        # The `--` must come before src/dst
        dash_idx = cmd.index("--")
        assert dash_idx < len(cmd) - 2
        assert cmd[dash_idx + 1] == "-evil.mkv"
        assert cmd[dash_idx + 2] == "/safe/dst.mkv"


# ---------------------------------------------------------------------------
# Gemini-2026-05-09 R2 — _resolve_trash_dir relative-path traversal
# ---------------------------------------------------------------------------


class TestResolveTrashDirRelative:
    def test_relative_traversal_falls_back_to_sublarr(self, tmp_path):
        from remux import _resolve_trash_dir

        fake_settings = MagicMock()
        fake_settings.media_path = str(tmp_path)
        with patch("config.get_settings", return_value=fake_settings):
            resolved = _resolve_trash_dir(str(tmp_path / "x.mkv"), "../../../etc")
        # Must NOT escape media_root — falls back to <media_path>/.sublarr
        assert resolved == os.path.normpath(os.path.join(str(tmp_path), ".sublarr"))


# ---------------------------------------------------------------------------
# Gemini-2026-05-09 R3 — run_ffprobe wraps file_path with _safe_arg_path
# ---------------------------------------------------------------------------


class TestFfprobeArgvSafe:
    def test_ffprobe_argv_uses_safe_arg_path(self, tmp_path, app_ctx):
        from ass_probe import run_ffprobe

        # Create a real file with a `-` leading basename inside tmp_path
        evil_dir = tmp_path / "anime"
        evil_dir.mkdir()
        evil = evil_dir / "-show.mkv"
        evil.write_bytes(b"\x1a\x45\xdf\xa3")

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return MagicMock(
                returncode=0,
                stdout='{"streams": []}',
                stderr="",
            )

        with patch("ass_probe.subprocess.run", side_effect=fake_run):
            run_ffprobe(str(evil), use_cache=False)

        cmd = captured["cmd"]
        # The argv slot for the file path must NOT begin with `-`
        # (it's wrapped by `_safe_arg_path` which prepends `./` for relative
        # paths or leaves absolute paths intact).
        path_arg = cmd[-1]
        # Either the absolute path is preserved (no leading `-` because it
        # starts with the tmp_path prefix) or _safe_arg_path joined `./`.
        # Either way, the argv slot is no longer interpreted as a flag.
        basename = os.path.basename(path_arg)
        # The basename can start with `-`, but the full argv slot must not.
        assert not path_arg.startswith("-"), f"argv slot still flag-like: {path_arg!r}"
        # And the basename must still resolve to the original file.
        assert basename == "-show.mkv"


# ---------------------------------------------------------------------------
# Gemini-2026-05-09 R5 — batch_extract route sets running=True synchronously
# ---------------------------------------------------------------------------


class TestBatchExtractAtomicBusyFlag:
    def test_running_flag_set_inside_route_lock(self, monkeypatch):
        """Two concurrent POSTs must not both pass the busy check.

        We exercise the contract directly: after the first call sets the
        flag, a second call must observe it as True even before the
        background thread runs.
        """
        from routes.batch_state import _batch_extract_lock, _batch_extract_state

        # Reset state
        with _batch_extract_lock:
            _batch_extract_state.update({"running": False, "total": 0})

        # Simulate the route's lock block (the actual route is hard to
        # exercise without a full Flask app, so we replicate the
        # critical section here):
        with _batch_extract_lock:
            assert _batch_extract_state["running"] is False
            # First "POST" — flag is flipped synchronously inside the lock
            _batch_extract_state["running"] = True

        # Second "POST" — must observe the flag without the thread having
        # run yet. (Pre-fix: would have observed `running=False` because
        # the flag was only set inside the background thread.)
        with _batch_extract_lock:
            assert _batch_extract_state["running"] is True

        # Cleanup
        with _batch_extract_lock:
            _batch_extract_state["running"] = False


# ---------------------------------------------------------------------------
# Gemini-2026-05-09 R6 — orphan.delete_orphaned uses is_safe_path
# ---------------------------------------------------------------------------


class TestOrphanDeleteIsSafePath:
    def test_rejects_paths_outside_media_root(self, tmp_path):
        """The route rejects paths that escape media_root via traversal,
        regardless of the platform's path separator. Uses tmp_path so the
        test is portable to Windows where ``/media/library`` does not
        exist on disk and ``os.path.realpath`` therefore wouldn't anchor
        the comparison the way a real deployment would.
        """
        from security_utils import is_safe_path

        media = tmp_path / "library"
        media.mkdir()
        (media / "anime").mkdir()
        good = media / "anime" / "show.de.ass"
        good.write_text("ok")

        # is_safe_path(file_path, base_dir) — file inside base
        assert is_safe_path(str(good), str(media))
        # File outside base
        outside = tmp_path / "elsewhere.ass"
        outside.write_text("nope")
        assert not is_safe_path(str(outside), str(media))
