"""Dispatch a fix action against a persisted finding."""

from __future__ import annotations

import logging
import os

from services.subtitle_health import store

logger = logging.getLogger(__name__)

_SIDECAR_CODEC_BY_EXT = {".ass": "ass", ".ssa": "ass", ".vtt": "webvtt"}


def _sidecar_codec(path: str) -> str:
    return _SIDECAR_CODEC_BY_EXT.get(os.path.splitext(path)[1].lower(), "srt")


def apply_fix(finding_id: int, action: str, opts: dict | None = None) -> dict:
    opts = opts or {}
    finding = store.get_finding(finding_id)
    if not finding:
        return {"changed": False, "reason": "finding not found"}

    path = finding["target_path"]
    kind = finding["target_kind"]
    lang = finding.get("lang", "und")
    sub_index = finding.get("stream_index")

    try:
        if action == "repair_escapes":
            from services.subtitle_health.fixers import repair_escapes

            res = repair_escapes.apply_to_sidecar(path, _sidecar_codec(path), finding_id=finding_id)
        elif action == "reencode":
            from services.subtitle_health.fixers import reencode

            res = reencode.apply_to_sidecar(path, finding_id=finding_id)
        elif action == "trash_sidecar":
            from services.subtitle_health.fixers import trash_sidecar

            res = trash_sidecar.apply(path, finding_id=finding_id)
        elif action == "quarantine_sidecar":
            from services.subtitle_health.fixers import quarantine_sidecar

            res = quarantine_sidecar.apply(path, finding_id=finding_id)
        elif action == "extract_clean_sidecar":
            from services.subtitle_health.fixers import extract_clean_sidecar

            res = extract_clean_sidecar.apply(
                path,
                sub_index=sub_index,
                codec=opts.get("codec", "subrip"),
                lang=lang,
                finding_id=finding_id,
            )
        elif action == "remux_track":
            from services.subtitle_health.fixers import remux_track

            res = remux_track.apply(
                path,
                sub_index=sub_index,
                codec=opts.get("codec", "subrip"),
                lang=lang,
                finding_id=finding_id,
            )
        elif action == "metadata_correction":
            import re

            new_lang = opts.get("new_lang") or ""
            if not re.fullmatch(r"[a-z]{2,3}", new_lang):
                return {"changed": False, "reason": "valid new_lang required"}
            from services.subtitle_health.fixers import metadata_correction

            if kind == "embedded":
                res = metadata_correction.apply_embedded_lang(
                    path, sub_index=sub_index, new_lang=new_lang, finding_id=finding_id
                )
            else:
                res = metadata_correction.apply_sidecar_rename(
                    path, new_lang=new_lang, finding_id=finding_id
                )
        else:
            return {"changed": False, "reason": f"unknown action: {action}"}
    except Exception as exc:
        logger.exception("subtitle_health: fix %s failed for finding %s", action, finding_id)
        return {"changed": False, "reason": f"fix failed: {exc}"}

    if res.get("changed"):
        store.mark_finding(
            finding_id,
            "mitigated" if res.get("status") == "mitigated_by_sidecar" else "resolved",
        )
    return res
