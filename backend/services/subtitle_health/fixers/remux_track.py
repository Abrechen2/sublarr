"""Replace one bad subtitle stream in an MKV with a cleaned version.

Uses mkvmerge for the rewrite (never ffmpeg -- it drops attachments/chapters).
Track identity comes from ``mkvmerge -J``, not ffprobe. Manual-only.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile

from remux import _make_backup, _safe_arg_path
from services.subtitle_health.fixers.common import FixValidationError
from services.subtitle_health.fixers.repair_escapes import repair_bytes
from services.subtitle_health.raw_io import extract_track_raw

logger = logging.getLogger(__name__)

_TEXT_CODECS = frozenset({"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text"})

_LANG3 = {"de": "ger", "en": "eng", "ger": "ger", "eng": "eng"}


def _mkvmerge_identify(video_path: str) -> dict:
    out = subprocess.run(
        ["mkvmerge", "-J", _safe_arg_path(video_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return json.loads(out.stdout)


def _subtitle_track_ids(info: dict) -> list[int]:
    return [t["id"] for t in info.get("tracks", []) if t.get("type") == "subtitles"]


def _run_mkvmerge_replace(
    video_path: str,
    output_path: str,
    drop_track_id: int,
    clean_sidecar: str,
    lang3: str,
    title: str,
    default_flag: bool,
    forced_flag: bool,
) -> bool:
    cmd = [
        "mkvmerge",
        "-o",
        _safe_arg_path(output_path),
        "--subtitle-tracks",
        f"!{drop_track_id}",
        _safe_arg_path(video_path),
        "--language",
        f"0:{lang3}",
    ]
    if title:
        cmd += ["--track-name", f"0:{title}"]
    cmd += [
        "--default-track-flag",
        f"0:{'yes' if default_flag else 'no'}",
        "--forced-display-flag",
        f"0:{'yes' if forced_flag else 'no'}",
        _safe_arg_path(clean_sidecar),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    return result.returncode in (0, 1)


def _validate_remux(original_path: str, remuxed_path: str) -> None:
    before = _subtitle_track_ids(_mkvmerge_identify(original_path))
    after = _subtitle_track_ids(_mkvmerge_identify(remuxed_path))
    if len(before) != len(after):
        raise FixValidationError(f"subtitle track count changed {len(before)} -> {len(after)}")


def apply(
    video_path: str,
    *,
    sub_index: int,
    codec: str,
    lang: str,
    finding_id=None,
) -> dict:
    """Replace one subtitle stream in an MKV with a repaired version.

    Returns a manifest dict with ``changed`` bool and either ``status``
    (on success) or ``reason`` (on refusal/failure).
    """
    from services.subtitle_health import store

    if (codec or "").lower() not in _TEXT_CODECS:
        return {"changed": False, "reason": f"unsupported codec for remux: {codec}"}

    info = _mkvmerge_identify(video_path)
    sub_ids = _subtitle_track_ids(info)
    if sub_index >= len(sub_ids):
        return {"changed": False, "reason": "sub_index out of range"}

    drop_track_id = sub_ids[sub_index]
    track = next(t for t in info["tracks"] if t["id"] == drop_track_id)
    props = track.get("properties", {})
    lang3 = _LANG3.get((lang or "und").lower(), "und")
    title = props.get("track_name", "")
    default_flag = bool(props.get("default_track"))
    forced_flag = bool(props.get("forced_track"))

    raw = extract_track_raw(video_path, sub_index, codec)
    fixed = repair_bytes(raw, codec)

    fd, clean_sidecar = tempfile.mkstemp(suffix=".srt")
    os.close(fd)
    out_fd, out_path = tempfile.mkstemp(suffix=".mkv", dir=os.path.dirname(video_path) or ".")
    os.close(out_fd)
    try:
        with open(clean_sidecar, "wb") as fh:
            fh.write(fixed)

        ok = _run_mkvmerge_replace(
            video_path,
            out_path,
            drop_track_id,
            clean_sidecar,
            lang3,
            title,
            default_flag,
            forced_flag,
        )
        if not ok:
            return {"changed": False, "reason": "mkvmerge failed"}

        _validate_remux(video_path, out_path)
        backup = _make_backup(video_path, use_reflink=False)
        os.replace(out_path, video_path)
        out_path = ""

        fix_id = store.record_fix(
            finding_id=finding_id,
            fixer="remux_track",
            action="remux_track",
            target_path=video_path,
            trashed_original_path=backup,
            original_hash="",
            fixed_hash="",
            reversible=True,
        )
        return {"changed": True, "fix_id": fix_id, "status": "resolved"}
    finally:
        for p in (clean_sidecar, out_path):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass
