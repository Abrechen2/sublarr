"""Filesystem scan of subtitle sidecars — routes-independent so the services
layer can use it without importing from ``routes.*`` (layering contract).

Moved out of ``routes.subtitles.helpers`` (which now re-exports it for its many
existing importers) so ``services.combine_service`` can call it directly.
"""

from __future__ import annotations

import glob as _glob
import logging
import os

from subtitle_filename import parse_combined_filename, parse_subtitle_filename

logger = logging.getLogger(__name__)


def _combined_base(path: str, combined: tuple[str, str]) -> str:
    """The video stem of ``<stem>.<l1>-<l2>.combined.<ext>``."""
    lang_tag, ext = combined
    name = os.path.basename(path)
    return name[: -len(f".{lang_tag}.combined.{ext}")]


def scan_subtitle_sidecars(video_path: str) -> list[dict]:
    """Scan filesystem for all subtitle sidecar files next to video_path.

    Returns a list of dicts with path, language, format, modifier (optional),
    size_bytes, modified_at. Backup files (``.bak``) are excluded — they are
    restore artefacts produced by ``subtitle_processor.apply_mods`` and are
    not playable subs. Modifier-suffixed files (``.hi``, ``.forced``,
    ``.sdh``, ``.cc``) keep their underlying language and surface the
    modifier in the response so the UI can render a small badge.
    """
    base, _ = os.path.splitext(video_path)
    # The glob is a prefix match: "Film.*" also finds "Film.Extended.en.srt",
    # the sidecar of "Film.Extended.mkv". Only a parsed base equal to this
    # video's stem belongs here (#61 A20: bulk sync paired it with Film.mkv).
    stem = os.path.basename(base)
    result = []
    try:
        for fpath in _glob.glob(_glob.escape(base) + ".*"):
            if fpath == video_path:
                continue
            parsed = parse_subtitle_filename(fpath)
            if parsed is not None and parsed.base != stem:
                continue
            if parsed is None:
                # Combined/bilingual files (<base>.<l1>-<l2>.combined.<ext>) do
                # not match the single-language parser (that keeps cleanup from
                # trashing them). Surface them here so they are editable in the
                # UI, tagged with ``combined`` and the joined language tag.
                combined = parse_combined_filename(fpath)
                if combined is not None and _combined_base(fpath, combined) == stem:
                    try:
                        stat = os.stat(fpath)
                    except OSError:
                        continue
                    lang_tag, ext = combined
                    result.append(
                        {
                            "path": fpath,
                            "language": lang_tag,
                            "format": ext,
                            "size_bytes": stat.st_size,
                            "modified_at": stat.st_mtime,
                            "combined": True,
                        }
                    )
                continue
            if parsed.is_backup:
                # .bak files belong to the backup-management UI, not the
                # active sidecar list.
                continue
            try:
                stat = os.stat(fpath)
            except OSError:
                continue
            entry: dict = {
                "path": fpath,
                "language": parsed.language,
                "format": parsed.extension,
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            }
            primary = parsed.primary_modifier
            if primary is not None:
                entry["modifier"] = primary
            result.append(entry)
    except Exception as exc:
        logger.warning("scan_subtitle_sidecars failed for %s: %s", video_path, exc)
    return result
