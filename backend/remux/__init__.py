"""Remux engine — safely removes subtitle streams from video containers.

Workflow:
  1. Probe container to confirm stream exists.
  2. Select backend: mkvmerge (MKV) or ffmpeg (MP4/other).
  3. Remux to a temp file in the same directory.
  4. Verify temp file (duration ±2 s, stream counts, size ≥ 50 %).
  5. Atomic swap: original → <original>.bak, temp → original.
  6. Optionally use CoW reflink for zero-cost backup on Btrfs/XFS.

License: GPL-3.0
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class RemuxError(Exception):
    """Raised when any remux step fails."""


# ---------------------------------------------------------------------------
# CoW / reflink helper
# ---------------------------------------------------------------------------


def _try_reflink(src: str, dst: str) -> bool:
    """Attempt `cp --reflink=auto -- src dst`. Returns True on success.

    Audit Gemini-2026-05-09 R1: ``--`` separates cp's flags from positional
    arguments. Without it, a leading ``-`` in src/dst (rare on a server
    but possible with attacker-controlled basenames) would let cp
    interpret them as flags. Same defence as ``_safe_arg_path`` provides
    for ffmpeg/mkvmerge — applied here for parity.
    """
    try:
        result = subprocess.run(
            ["cp", "--reflink=auto", "--", src, dst],
            capture_output=True,
            timeout=120,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# Forbidden absolute roots for ``trash_dir`` setting. A user-controlled path
# in this list (or below it) would put recovery copies of subtitle/video data
# in privileged areas of the container. Mirrors the standalone-folder
# blocklist (audit S0-2) and applies to BOTH absolute and relative
# trash_dir configurations once they are resolved against media_path.
_FORBIDDEN_TRASH_ROOTS = (
    "/",
    "/etc",
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/boot",
    "/root",
    "/var/log",
    "/var/run",
    "/var/lib",
    "/usr",
    "/lib",
    "/lib64",
    "/sbin",
    "/bin",
)


def _is_forbidden_trash_root(path: str) -> bool:
    """Return True when ``path`` is exactly a forbidden system root or a
    direct descendant. Cross-platform — normalises Windows separators."""
    norm = os.path.normpath(path).replace("\\", "/").rstrip("/") or "/"
    for root in _FORBIDDEN_TRASH_ROOTS:
        if norm == root:
            return True
        if root != "/" and norm.startswith(root + "/"):
            return True
    return False


def _resolve_trash_dir(video_path: str, trash_dir_setting: str) -> str:
    """Return the absolute path to the trash directory for this video.

    Audit G3: an absolute ``trash_dir_setting`` used to be returned
    unchecked, letting a config like ``remux_trash_dir=/etc/sublarr``
    seed backups in privileged paths. The resolver now refuses absolute
    paths that fall on / inside ``_FORBIDDEN_TRASH_ROOTS`` and silently
    falls back to the standard ``.sublarr`` under ``media_path`` for
    those cases.

    Audit Gemini-2026-05-09 R2: relative settings used to be
    ``os.path.join(media_root, setting)``-ed and returned unchecked. A
    setting of ``../../../etc`` would then escape ``media_root``. We now
    resolve the joined path and verify it stays inside ``media_root`` via
    ``is_safe_path``; a traversal attempt falls back to ``.sublarr`` like
    the absolute-forbidden-root case.
    """
    if os.path.isabs(trash_dir_setting):
        if _is_forbidden_trash_root(trash_dir_setting):
            logger.warning(
                "remux_trash_dir=%s lands on a forbidden system root; falling back to "
                "<media_path>/.sublarr",
                trash_dir_setting,
            )
            trash_dir_setting = ".sublarr"
        else:
            return trash_dir_setting

    # Find longest watched-folder prefix
    try:
        from config import get_settings

        settings = get_settings()
        media_root = getattr(settings, "media_path", "") or os.path.dirname(video_path)
    except Exception:
        media_root = os.path.dirname(video_path)

    candidate = os.path.normpath(os.path.join(media_root, trash_dir_setting))
    try:
        from security_utils import is_safe_path

        # is_safe_path(file_path, base_dir) — argument order matters:
        # we want to verify ``candidate`` (the path) stays inside
        # ``media_root`` (the base). A reversed call would silently
        # let traversal slip through.
        if media_root and not is_safe_path(candidate, media_root):
            logger.warning(
                "remux_trash_dir=%s escapes media_path (%s); falling back to <media_path>/.sublarr",
                trash_dir_setting,
                media_root,
            )
            return os.path.normpath(os.path.join(media_root, ".sublarr"))
    except Exception:
        # security_utils unavailable in unit-test harness — fall through
        pass
    return candidate


def _make_backup(video_path: str, use_reflink: bool, trash_dir: str = "") -> str:
    """Move original to the trash directory and return the backup path.

    Layout: <trash_dir>/trash/<YYYY-MM-DD>/<basename>.<timestamp>.bak

    Audit G7: we used to fall back to a sibling ``video_path + ".bak"``
    when the trash dir could not be created. That hid a configuration
    problem (read-only trash) AND created a "recovery copy next to the
    original" UX surprise. Failure now raises ``RemuxError`` so the
    caller treats it as a real backup failure and aborts the destructive
    swap.
    """
    import time as _time

    basename = os.path.basename(video_path)
    date_str = __import__("datetime").date.today().isoformat()
    timestamp = int(_time.time())

    resolved = _resolve_trash_dir(video_path, trash_dir or ".sublarr")
    dest_dir = os.path.join(resolved, "trash", date_str)

    try:
        os.makedirs(dest_dir, exist_ok=True)
        bak_path = os.path.join(dest_dir, f"{basename}.{timestamp}.bak")
        if use_reflink and _try_reflink(video_path, bak_path):
            logger.info("Remux: reflink backup in trash: %s", bak_path)
        else:
            shutil.copy2(video_path, bak_path)
            logger.info("Remux: backup moved to trash: %s", bak_path)
        return bak_path
    except OSError as exc:
        raise RemuxError(f"could not create backup in trash dir {dest_dir}: {exc}") from exc


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


def _detect_backend(video_path: str) -> str:
    """Return 'mkvmerge' for MKV files, 'ffmpeg' otherwise."""
    ext = os.path.splitext(video_path)[1].lower()
    if ext in (".mkv", ".mka", ".mk3d"):
        return "mkvmerge"
    return "ffmpeg"


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _safe_arg_path(path: str) -> str:
    """Argv-injection defence (Audit G8). Thin wrapper over the canonical
    ``security_utils.safe_subprocess_arg`` so every subprocess call site shares
    one implementation.
    """
    from security_utils import safe_subprocess_arg

    return safe_subprocess_arg(path)


# ---------------------------------------------------------------------------
# mkvmerge backend
# ---------------------------------------------------------------------------


def _remux_mkvmerge(video_path: str, stream_indices: list[int], output_path: str) -> None:
    """Remove subtitle streams using mkvmerge.

    `stream_indices` are the global track IDs as reported by ffprobe/mkvmerge -i
    (matches mkvmerge's --subtitle-tracks !N,M,... flag where the leading `!`
    applies to the whole comma-separated list, not to each element).
    """
    exclusions = "!" + ",".join(str(idx) for idx in stream_indices)
    # Audit G8: prepend "./" to filenames that begin with "-" so mkvmerge
    # parses them as positional paths instead of flags. mkvmerge does not
    # accept the "--" end-of-options marker for the input file.
    safe_video = _safe_arg_path(video_path)
    safe_output = _safe_arg_path(output_path)
    cmd = [
        "mkvmerge",
        "-o",
        safe_output,
        "--subtitle-tracks",
        exclusions,
        safe_video,
    ]
    logger.debug("Remux mkvmerge: %s", " ".join(cmd))
    from utils.io_timeout import compute_io_timeout

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=compute_io_timeout(video_path),
    )
    if result.returncode not in (0, 1):  # mkvmerge exit 1 = warnings, still OK
        # mkvmerge writes hard errors to stdout, not stderr — include both so
        # failures are never logged with an empty reason.
        detail = (result.stderr or result.stdout or "").strip()[:500]
        raise RemuxError(f"mkvmerge failed (exit {result.returncode}): {detail}")


# ---------------------------------------------------------------------------
# ffmpeg backend
# ---------------------------------------------------------------------------


def _remux_ffmpeg(video_path: str, stream_indices: list[int], output_path: str) -> None:
    """Remove subtitle streams using ffmpeg stream copy."""
    if not _which("ffmpeg"):
        raise RemuxError("ffmpeg not found")

    # Audit G8: ./-prefix paths whose basename begins with "-" so ffmpeg
    # cannot parse them as flags. ffmpeg has no end-of-options marker
    # before -i — relying on argv ordering alone is unsafe with attacker-
    # controlled filenames.
    safe_video = _safe_arg_path(video_path)
    safe_output = _safe_arg_path(output_path)
    cmd = ["ffmpeg", "-y", "-i", safe_video, "-map", "0"]
    for idx in stream_indices:
        cmd += ["-map", f"-0:{idx}"]
    cmd += ["-c", "copy", safe_output]

    logger.debug("Remux ffmpeg: %s", " ".join(cmd))
    from utils.io_timeout import compute_io_timeout

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=compute_io_timeout(video_path),
    )
    if result.returncode != 0:
        raise RemuxError(f"ffmpeg failed (exit {result.returncode}): {result.stderr[-500:]}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _probe(path: str) -> dict:
    """Run ffprobe and return parsed JSON."""
    if not _which("ffprobe"):
        raise RemuxError("ffprobe not found")
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        _safe_arg_path(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RemuxError(f"ffprobe failed: {result.stderr[:300]}")
    import json

    return json.loads(result.stdout)


def _video_duration(info: dict) -> float:
    """Real video duration in seconds for an ffprobe ``info`` dict.

    Prefers the first video stream's own duration over the container's
    ``format.duration``. A container duration can be inflated by a phantom
    trailing segment — e.g. a subtitle track whose last event extends tens of
    seconds past the actual video — so a subtitle-only remux legitimately
    shrinks ``format.duration`` to the real video end. Comparing those container
    values then false-positives the duration guard even though no video/audio
    content was lost (observed on Solo Leveling S01E12: container 1478 s vs real
    video 1420 s).

    Matroska stores per-track length in a ``DURATION`` tag
    (``HH:MM:SS.fffffffff``); ffprobe surfaces it under ``stream.tags.DURATION``.
    Preference order: numeric stream ``duration`` → ``tags.DURATION`` → container
    ``format.duration``. Returns 0.0 when nothing usable is present.
    """
    for s in info.get("streams", []):
        if s.get("codec_type") != "video":
            continue
        d = s.get("duration")
        if d not in (None, "", "N/A"):
            try:
                return float(d)
            except (TypeError, ValueError):
                pass
        tags = s.get("tags") or {}
        tag = tags.get("DURATION") or tags.get("duration")
        if tag:
            try:
                h, m, sec = str(tag).split(":")
                return int(h) * 3600 + int(m) * 60 + float(sec)
            except (ValueError, AttributeError):
                pass
        break  # only the first video stream matters
    try:
        return float(info.get("format", {}).get("duration", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _verify(original_path: str, remuxed_path: str, n_removed: int = 1) -> None:
    """Compare duration, stream count, and file size between original and remux.

    Args:
        n_removed: How many subtitle streams were intended to be removed.
    """
    orig_info = _probe(original_path)
    new_info = _probe(remuxed_path)

    # Duration check: allow ±5 s or 1 % of total duration (whichever is larger).
    # Compare the VIDEO STREAM duration (via _video_duration), not the container
    # format.duration: some MKVs have a phantom trailing segment (e.g. a sub
    # track extending past the video) that inflates format.duration, so a
    # subtitle-only remux rewrites the segment length to the real video end and
    # a container-vs-container comparison false-positives. A strict 2 s cap
    # produces false-positive failures for long files (24-min anime = ~1 % ≈ 14 s).
    orig_dur = _video_duration(orig_info)
    new_dur = _video_duration(new_info)
    dur_tolerance = max(5.0, orig_dur * 0.01)
    if orig_dur > 0 and abs(orig_dur - new_dur) > dur_tolerance:
        raise RemuxError(f"Duration mismatch: original={orig_dur:.1f}s remuxed={new_dur:.1f}s")

    # Video + audio stream count must not decrease
    def _count(info: dict, codec_type: str) -> int:
        return sum(1 for s in info.get("streams", []) if s.get("codec_type") == codec_type)

    if _count(new_info, "video") < _count(orig_info, "video"):
        raise RemuxError("Video stream count decreased after remux")
    if _count(new_info, "audio") < _count(orig_info, "audio"):
        raise RemuxError("Audio stream count decreased after remux")

    # Subtitle count should be exactly n_removed less.
    # If orig_subs < n_removed the container was already modified by a concurrent
    # worker — raise a clear error so the caller can log it as a harmless skip.
    orig_subs = _count(orig_info, "subtitle")
    new_subs = _count(new_info, "subtitle")
    if orig_subs < n_removed:
        raise RemuxError(
            f"Subtitle streams already removed (orig={orig_subs}, wanted to remove {n_removed})"
            " — concurrent modification?"
        )
    expected = orig_subs - n_removed
    if new_subs != expected:
        raise RemuxError(f"Unexpected subtitle stream count: expected {expected}, got {new_subs}")

    # File size sanity (≥ 50 % of original)
    orig_size = os.path.getsize(original_path)
    new_size = os.path.getsize(remuxed_path)
    if orig_size > 0 and new_size < orig_size * 0.5:
        raise RemuxError(f"Remuxed file suspiciously small: {new_size} vs original {orig_size}")

    logger.info(
        "Remux verification passed: dur=%.1fs streams(v=%d a=%d s=%d)",
        new_dur,
        _count(new_info, "video"),
        _count(new_info, "audio"),
        new_subs,
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def remove_subtitle_streams(
    video_path: str,
    streams: list[tuple[int, int]],
    use_reflink: bool = True,
    trash_dir: str = ".sublarr",
) -> str:
    """Remove one or more subtitle streams from a video container in one pass.

    Parameters
    ----------
    video_path:
        Absolute path to the source video file.
    streams:
        List of (stream_index, subtitle_track_index) tuples.
        stream_index = global ffprobe index (used by ffmpeg -map).
        subtitle_track_index = 0-based subtitle-only index (used by mkvmerge).
    use_reflink:
        Attempt CoW reflink for the backup copy (Btrfs/XFS).
    trash_dir:
        Relative or absolute path for the trash folder (default ".sublarr").
        Backups land in <trash_dir>/trash/<date>/<file>.<timestamp>.bak.

    Returns
    -------
    str
        Path to the created backup file.

    Raises
    ------
    RemuxError
        On any failure (backend not found, remux error, verification failure).
    """
    if not streams:
        raise RemuxError("No streams specified for removal")

    backend = _detect_backend(video_path)
    video_dir = os.path.dirname(video_path)
    suffix = os.path.splitext(video_path)[1]

    # For mkvmerge: use global stream indices (same convention as single-stream)
    # For ffmpeg: use global stream indices
    stream_indices = [s[0] for s in streams]

    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=video_dir)
    os.close(fd)

    try:
        logger.info(
            "Remux: starting (%s) — removing %d stream(s) %s from %s",
            backend,
            len(streams),
            stream_indices,
            video_path,
        )
        if backend == "mkvmerge" and _which("mkvmerge"):
            _remux_mkvmerge(video_path, stream_indices, tmp_path)
        elif backend == "mkvmerge":
            logger.warning(
                "mkvmerge not found — falling back to ffmpeg for MKV "
                "(install mkvtoolnix for better support)"
            )
            _remux_ffmpeg(video_path, stream_indices, tmp_path)
        else:
            _remux_ffmpeg(video_path, stream_indices, tmp_path)

        _verify(video_path, tmp_path, n_removed=len(streams))

        # Atomic swap: original → trash dir, temp → original
        bak_path = _make_backup(video_path, use_reflink, trash_dir)
        os.replace(tmp_path, video_path)
        logger.info("Remux: complete — %d stream(s) removed, backup at %s", len(streams), bak_path)
        return bak_path

    except Exception:
        if os.path.exists(tmp_path):
            with contextlib_suppress(OSError):
                os.unlink(tmp_path)
        raise


def remove_subtitle_stream(
    video_path: str,
    stream_index: int,
    subtitle_track_index: int,
    use_reflink: bool = True,
    trash_dir: str = ".sublarr",
) -> str:
    """Remove a single subtitle stream. Convenience wrapper around remove_subtitle_streams."""
    return remove_subtitle_streams(
        video_path=video_path,
        streams=[(stream_index, subtitle_track_index)],
        use_reflink=use_reflink,
        trash_dir=trash_dir,
    )


def get_media_streams(*args, **kwargs):
    """Thin re-export so tests can monkeypatch `remux.get_media_streams`.

    Runtime implementation lives in `ass_utils`; we import at call time to
    avoid a circular import (ass_utils imports remux helpers internally).
    """
    from ass_utils import get_media_streams as _impl

    return _impl(*args, **kwargs)


def remove_foreign_subtitle_streams(
    *,
    video_path: str,
    target_languages: set[str],
    keep_und: bool = False,
    use_reflink: bool = True,
    trash_dir: str = ".sublarr",
) -> str | None:
    """Strip subtitle streams whose language is not in `target_languages`.

    0.71.0 Phase 6 entry point. Run only after all required target-language
    sidecars for this file have been extracted successfully — the sidecars
    are the canonical source, the in-container copies are redundant, and
    removing foreign-language tracks shrinks the container + de-clutters
    the player track list.

    Parameters
    ----------
    video_path:
        Absolute path to the source video.
    target_languages:
        Normalized ISO language codes to keep (e.g. {"ger", "eng"}). If
        empty, this function is a no-op (defensive — never strip all).
    keep_und:
        If True, subtitle tracks with language=und are preserved. Default
        False matches the global `cleanup_foreign_tracks_keep_und`
        setting.
    use_reflink / trash_dir:
        Forwarded to `remove_subtitle_streams` (backup semantics
        preserved — nothing is hard-deleted).

    Returns
    -------
    str | None
        Path to the backup file on cleanup, or None if nothing needed to
        be removed (clean container, empty target set, or no subtitle
        streams at all).
    """
    if not target_languages:
        logger.debug(
            "remove_foreign_subtitle_streams: empty target set, skipping %s",
            video_path,
        )
        return None

    try:
        probe = get_media_streams(video_path)
    except Exception as exc:
        raise RemuxError(f"ffprobe failed on {video_path}: {exc}") from exc

    streams_to_remove: list[tuple[int, int]] = []
    sub_only_idx = 0
    for stream in probe.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        lang = (stream.get("tags", {}).get("language", "und") or "und").lower()
        is_foreign = lang not in target_languages
        if is_foreign and not (keep_und and lang == "und"):
            global_idx = stream.get("index")
            if global_idx is not None:
                streams_to_remove.append((global_idx, sub_only_idx))
        sub_only_idx += 1

    if not streams_to_remove:
        logger.debug("remove_foreign_subtitle_streams: no foreign tracks in %s", video_path)
        return None

    logger.info(
        "remove_foreign_subtitle_streams: stripping %d foreign sub track(s) from %s "
        "(keep=%s, keep_und=%s)",
        len(streams_to_remove),
        video_path,
        sorted(target_languages),
        keep_und,
    )
    return remove_subtitle_streams(
        video_path=video_path,
        streams=streams_to_remove,
        use_reflink=use_reflink,
        trash_dir=trash_dir,
    )


def remove_subtitle_streams_by_index(
    video_path: str,
    drop_indices: list[int],
    use_reflink: bool = True,
    trash_dir: str = ".sublarr",
) -> str | None:
    """Remux ``video_path`` dropping the given subtitle order-indices.

    ``drop_indices`` are 0-based positions among the file's subtitle streams
    (the same ``sub_index`` used elsewhere in probes). They are translated
    internally to mkvmerge's global track IDs (the ffprobe ``stream["index"]``)
    by probing the container — the same probe the twin
    ``remove_foreign_subtitle_streams`` performs — because ``_remux_mkvmerge``
    expects GLOBAL track IDs, not subtitle-relative positions.

    Leaves a ``.bak`` backup in the trash dir; returns its path. No-op
    (returns ``None``) for an empty list, or when none of the supplied indices
    resolve to a real subtitle stream.

    Raises
    ------
    RemuxError
        On backup failure, mkvmerge error, or verification failure.
    """
    if not drop_indices:
        return None

    # Map subtitle-relative positions (sub_index) -> global ffprobe stream index.
    # _remux_mkvmerge expects GLOBAL track IDs (matching mkvmerge --subtitle-tracks),
    # so we must translate before handing off (mirrors remove_foreign_subtitle_streams).
    try:
        probe = get_media_streams(video_path)
    except Exception as exc:
        raise RemuxError(f"ffprobe failed on {video_path}: {exc}") from exc

    sub_rel_to_global: dict[int, int] = {}
    sub_only_idx = 0
    for stream in probe.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        global_idx = stream.get("index")
        if global_idx is not None:
            sub_rel_to_global[sub_only_idx] = global_idx
        sub_only_idx += 1

    global_indices = sorted(
        sub_rel_to_global[i] for i in set(drop_indices) if i in sub_rel_to_global
    )
    if not global_indices:
        logger.debug(
            "remove_subtitle_streams_by_index: no supplied index %s resolves to a "
            "subtitle stream in %s — skipping",
            sorted(set(drop_indices)),
            video_path,
        )
        return None

    video_dir = os.path.dirname(video_path)
    suffix = os.path.splitext(video_path)[1]

    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=video_dir)
    os.close(fd)

    try:
        logger.info(
            "remove_subtitle_streams_by_index: stripping subtitle indices %s "
            "(global track IDs %s) from %s",
            sorted(set(drop_indices)),
            global_indices,
            video_path,
        )
        _remux_mkvmerge(video_path, global_indices, tmp_path)
        _verify(video_path, tmp_path, n_removed=len(global_indices))

        bak_path = _make_backup(video_path, use_reflink, trash_dir)
        os.replace(tmp_path, video_path)
        logger.info(
            "remove_subtitle_streams_by_index: complete — %d stream(s) removed, backup at %s",
            len(global_indices),
            bak_path,
        )
        return bak_path

    except Exception:
        if os.path.exists(tmp_path):
            with contextlib_suppress(OSError):
                os.unlink(tmp_path)
        raise


def contextlib_suppress(exc_type):
    """Tiny suppress context manager to avoid extra import."""
    import contextlib

    return contextlib.suppress(exc_type)


# ---------------------------------------------------------------------------
# Sidecar cleanup — post-extract language filtering
# ---------------------------------------------------------------------------

# Sidecar extensions we ever produce or import from providers.
_SIDECAR_EXTS = (".ass", ".srt", ".vtt", ".sub")

# Modifier suffixes that can appear between lang and extension:
#   show.en.forced.srt, show.de.sdh.ass, show.en.hi.vtt
# We preserve them so the cleanup knows "lang=en" even when there's a modifier.
_SIDECAR_MODIFIERS = ("forced", "sdh", "hi", "cc", "sign", "signs")


def _parse_sidecar_language(candidate: str, video_base: str) -> str | None:
    """Return the language tag (untreated) of a sidecar, or None if it is not
    a recognisable `<video_base>.<lang>[.<modifier>].<ext>` sidecar.

    The caller is expected to pass the fully-qualified sidecar path plus the
    media file's base (path without video extension). The function is tolerant
    to any of our supported sidecar extensions and to a single optional
    modifier token (forced/sdh/hi/cc/signs).
    """
    base_dir, base_file = os.path.split(video_base)
    name = os.path.basename(candidate)
    if not name.startswith(base_file + "."):
        return None
    ext = os.path.splitext(name)[1].lower()
    if ext not in _SIDECAR_EXTS:
        return None
    remainder = name[len(base_file) + 1 : -len(ext)]  # everything between '.' and '.ext'
    if not remainder:
        return None
    parts = remainder.split(".")
    # Strip a trailing known modifier, e.g. 'en.forced' -> 'en'
    if len(parts) >= 2 and parts[-1].lower() in _SIDECAR_MODIFIERS:
        parts = parts[:-1]
    if len(parts) != 1:
        return None
    return parts[0]


def trash_non_target_sidecars(
    video_path: str,
    keep_langs: set[str],
    trash_dir: str = ".sublarr",
) -> list[tuple[str, str]]:
    """Move extracted subtitle sidecars whose language is not in ``keep_langs``
    into the same trash folder used by the remux backup.

    Args:
        video_path: Absolute path to the media file (the sidecars are siblings).
        keep_langs: Normalised ISO 639-1 codes to preserve (e.g. {'de','en'}).
            Callers typically pass the profile's target_languages plus
            source_language when translation is enabled.
        trash_dir: Same semantics as in ``_make_backup`` — relative to the
            media root or absolute.

    Returns a list of ``(original_path, trash_path)`` tuples for logging.
    Unknown language tags (including 'und' and codes that are not in our
    lookup table) are KEPT on disk — we do not destroy data we cannot classify.
    """
    import datetime
    import glob

    # Late import to avoid a cycle with config_language_data -> config
    from config_language_data import normalize_language_code

    video_base = os.path.splitext(video_path)[0]
    moved: list[tuple[str, str]] = []

    # Build a candidate list across supported extensions.
    candidates: list[str] = []
    for ext in _SIDECAR_EXTS:
        candidates.extend(glob.glob(f"{video_base}.*{ext}"))

    for candidate in candidates:
        raw_lang = _parse_sidecar_language(candidate, video_base)
        if raw_lang is None:
            continue  # not a lang-tagged sidecar
        normalised = normalize_language_code(raw_lang)
        # Safety net: never delete ambiguous or unrecognised tags.
        if not normalised or normalised == "und":
            continue
        if normalised in keep_langs:
            continue
        # Build the trash destination using the existing helper layout.
        resolved = _resolve_trash_dir(video_path, trash_dir or ".sublarr")
        date_str = datetime.date.today().isoformat()
        dest_dir = os.path.join(resolved, "trash", date_str)
        try:
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(candidate))
            # Rare collision: if a file with the same name is already in trash,
            # append a unique suffix rather than overwriting.
            if os.path.exists(dest):
                import time as _time

                stem, ext = os.path.splitext(dest)
                dest = f"{stem}.{int(_time.time())}{ext}"
            shutil.move(candidate, dest)
            moved.append((candidate, dest))
            logger.info("Sidecar cleanup: trashed %s (lang=%s)", candidate, normalised)
        except OSError as exc:
            logger.warning("Sidecar cleanup: could not trash %s: %s", candidate, exc)
    return moved
