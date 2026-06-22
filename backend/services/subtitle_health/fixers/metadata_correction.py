"""Fix wrong language labels: mkvpropedit (embedded) or rename (sidecar)."""

from __future__ import annotations

import os
import re
import subprocess

_LANG3 = {"de": "ger", "en": "eng"}


def _run_mkvpropedit(video_path: str, track_selector: str, lang3: str) -> bool:
    from remux import _safe_arg_path

    cmd = [
        "mkvpropedit",
        _safe_arg_path(video_path),
        "--edit",
        track_selector,
        "--set",
        f"language={lang3}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0


def apply_embedded_lang(video_path: str, *, sub_index: int, new_lang: str, finding_id=None) -> dict:
    if not re.fullmatch(r"[a-z]{2,3}", new_lang or ""):
        return {"changed": False, "reason": "invalid new_lang"}

    from services.subtitle_health import store

    lang3 = _LANG3.get(new_lang, new_lang)
    # mkvpropedit selector is 1-based per track-type; map the subtitle sub_index.
    selector = f"track:s{sub_index + 1}"
    ok = _run_mkvpropedit(video_path, selector, lang3)
    if not ok:
        return {"changed": False, "reason": "mkvpropedit failed"}
    fix_id = store.record_fix(
        finding_id=finding_id,
        fixer="metadata_correction",
        action="metadata_correction",
        target_path=video_path,
        trashed_original_path=None,
        original_hash="",
        fixed_hash="",
        reversible=False,
    )
    return {"changed": True, "fix_id": fix_id}


def apply_sidecar_rename(path: str, *, new_lang: str, finding_id=None) -> dict:
    if not re.fullmatch(r"[a-z]{2,3}", new_lang or ""):
        return {"changed": False, "reason": "invalid new_lang"}

    from services.subtitle_health import store

    d = os.path.dirname(path)
    name = os.path.basename(path)
    stem, ext = os.path.splitext(name)
    base, _old_lang = os.path.splitext(stem)
    new_name = f"{base}.{new_lang}{ext}"
    new_path = os.path.join(d, new_name)
    if os.path.exists(new_path):
        return {"changed": False, "reason": "target name already exists"}
    if os.path.commonpath([os.path.realpath(new_path), os.path.realpath(d)]) != os.path.realpath(d):
        return {"changed": False, "reason": "unsafe target path"}
    os.rename(path, new_path)
    fix_id = store.record_fix(
        finding_id=finding_id,
        fixer="metadata_correction",
        action="metadata_correction",
        target_path=path,
        trashed_original_path=new_path,
        original_hash="",
        fixed_hash="",
        reversible=True,
    )
    return {"changed": True, "fix_id": fix_id, "new_path": new_path}
