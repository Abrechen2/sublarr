"""The automatic processing pipeline for one subtitle (HI removal, fixes, credits).

Run after a provider download, a translation and an embedded extraction, with
the global settings or a series' own overrides. Moved here from
``routes/subtitle_processor.py`` (2026-10-30) so services can call it without
importing the routes layer; the old names stay importable there.
"""

from __future__ import annotations

import json
import logging
import os

import config

logger = logging.getLogger(__name__)


def get_settings():
    # Looked up on every call so patch("config.get_settings") reaches it.
    return config.get_settings()


def _build_pipeline_mods(cfg: dict):
    """Convert a resolved config dict into an ordered list of ModConfig objects."""
    from subtitle_processor import ModConfig, ModName

    mods = []
    if cfg.get("common_fixes"):
        raw = get_settings().auto_process_common_fixes_config_json.strip()
        try:
            options = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            logger.warning("[batch-process] invalid common_fixes JSON config, using defaults")
            options = {}
        mods.append(ModConfig(mod=ModName.COMMON_FIXES, options=options))
    if cfg.get("hi_removal"):
        mods.append(ModConfig(mod=ModName.HI_REMOVAL))
    if cfg.get("credit_removal"):
        mods.append(ModConfig(mod=ModName.CREDIT_REMOVAL))
    return mods


def _is_processing_exempt_sidecar(subtitle_path: str) -> bool:
    """True for sidecars the auto-mods must never rewrite.

    - Modifier variants (``.hi``, ``.sdh``, ``.cc``, ``.forced``): running
      HI-removal over a ``.hi`` file destroys the whole point of that
      variant (its non-HI twin usually sits right next to it).
    - Combined bilingual files (``.de-en.combined.ass``): composed
      artefacts, not processing fodder.
    """
    try:
        from subtitle_filename import parse_combined_filename, parse_subtitle_filename

        if parse_combined_filename(subtitle_path) is not None:
            return True
        parsed = parse_subtitle_filename(subtitle_path)
        if parsed is not None and parsed.primary_modifier in ("hi", "sdh", "cc", "forced"):
            return True
    except Exception:
        logger.debug("[pipeline] sidecar classification failed for %s", subtitle_path)
    return False


def _run_pipeline_for_path(subtitle_path: str, series_id: int | None) -> None:
    """Run the configured processing pipeline for one subtitle file.

    Called post-download (synchronously for fast ops) or from batch.
    No-ops if no processing mods are enabled.
    """
    ext = os.path.splitext(subtitle_path)[1].lower()
    if ext not in (".srt", ".ass", ".ssa"):
        return
    if _is_processing_exempt_sidecar(subtitle_path):
        return

    from db.models.core import SeriesSettings
    from subtitle_processor import apply_mods, resolve_config

    s = get_settings()
    global_cfg = {
        "common_fixes": s.auto_process_common_fixes,
        "hi_removal": s.auto_process_hi_removal,
        "credit_removal": s.auto_process_credit_removal,
    }

    from services.standalone_owner_keys import get_row

    series_cfg = None
    if series_id is not None:
        row = get_row(SeriesSettings, series_id)
        if row and row.processing_config:
            try:
                series_cfg = json.loads(row.processing_config)
            except json.JSONDecodeError:
                logger.warning(
                    "[pipeline] malformed processing_config for series %s, using global config",
                    series_id,
                )

    resolved = resolve_config(global_cfg, series_cfg)
    mods = _build_pipeline_mods(resolved)
    if not mods:
        return

    try:
        apply_mods(subtitle_path, mods)
        logger.debug("[pipeline] processed %s", subtitle_path)
    except Exception as exc:
        logger.warning("[pipeline] failed for %s: %s", subtitle_path, exc)
