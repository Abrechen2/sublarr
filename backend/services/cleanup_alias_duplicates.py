"""Cleanup rule ``alias_duplicates``: drop a sidecar spelled with an alias language code.

Prod case (2026-11): twelve episodes carried ``X.de.srt`` and ``X.deu.srt``
holding the same subtitle, so Emby listed two German tracks. The two names are
the same logical track (ISO 639-1 ``de`` vs ISO 639-2 ``deu``/``ger``), left
behind by older writers and by external tools.

The rule pairs sidecars of one video that share the canonical language, the
format and the kind (full / forced / sdh / hi / ...). When the alias-coded file
holds the same subtitle as the canonical-coded one it goes to the recoverable
sidecar trash and the canonical file stays. Different content keeps both; an
alias file without a canonical peer is never touched.

"Same subtitle" means the same translation of the same video: in both
directions at least ``MIN_CUE_MATCH`` of the cue texts find an equal text in the
other file whose start, after removing the median start offset of the matched
pairs, lies within ``MAX_START_DRIFT_MS``, and that median offset is itself at
most ``MAX_START_DRIFT_MS``. Prod pairs differ by a constant ~0.12 s shift and a
few split or added lines; a different translation shares no texts.
"""

from __future__ import annotations

import logging
import os
import re
import statistics
import uuid
from collections import defaultdict

from services.cleanup_executors import (
    VIDEO_EXTENSIONS,
    _classify_sidecar,
    _media_path_reachable,
    _subtitle_files,
)

logger = logging.getLogger(__name__)

#: Share of cues, per direction, that must find a matching text in the other file.
MIN_CUE_MATCH = 0.90

#: Largest accepted median start offset, and largest drift around it, in ms.
MAX_START_DRIFT_MS = 1000

#: Three-letter tags that name a regional variant rather than the language's
#: ISO 639-2 alias (``pob`` is Brazilian Portuguese): never an alias.
_NOT_ALIASES = frozenset({"pob"})

_BOM_ENCODINGS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


def _lang_token(path: str, modifier: str) -> str:
    """The raw language token of a classified sidecar path (lower-cased)."""
    parts = os.path.basename(os.path.splitext(path)[0]).split(".")
    return parts[-2 if modifier else -1].lower()


def _is_alias_token(token: str, canonical: str) -> bool:
    """True for an ISO 639-2 spelling (``deu``, ``ger``, ``eng``) of ``canonical``."""
    return (
        len(canonical) == 2
        and len(token) == 3
        and token.isalpha()
        and token != canonical
        and token not in _NOT_ALIASES
    )


def _decode(data: bytes) -> str:
    for bom, encoding in _BOM_ENCODINGS:
        if data.startswith(bom):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                break
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _cues(path: str) -> list[tuple[int, int, str]] | None:
    """Parsed ``(start_ms, end_ms, text)`` cues of ``path``; None when unreadable."""
    import pysubs2

    try:
        with open(path, "rb") as fh:
            text = _decode(fh.read()).replace("\r\n", "\n").replace("\r", "\n")
        subs = pysubs2.SSAFile.from_string(text)
    except (OSError, ValueError, pysubs2.exceptions.Pysubs2Error) as exc:
        logger.debug("alias_duplicates: cannot parse %s: %s", path, exc)
        return None
    return [
        (ev.start, ev.end, " ".join(ev.text.split()))
        for ev in subs
        if not ev.is_comment and ev.text.strip()
    ]


def _norm_text(text: str) -> str:
    """Cue text without ASS/HTML tags, line breaks and runs of whitespace."""
    text = text.replace("\\N", " ").replace("\\n", " ")
    return " ".join(re.sub(r"\{[^}]*\}|<[^>]*>", "", text).split())


def _match(cues_a: list[tuple[int, str]], cues_b: list[tuple[int, str]], offset: int | None):
    """Start offsets (b - a) of a one-to-one pairing of equal texts.

    With ``offset`` None every text pairs with its nearest start; otherwise a
    pair must lie within ``MAX_START_DRIFT_MS`` of ``offset``.
    """
    by_text: dict[str, list[int]] = defaultdict(list)
    for start, text in cues_b:
        by_text[text].append(start)
    deltas: list[int] = []
    for start, text in cues_a:
        starts = by_text.get(text)
        if not starts:
            continue
        target = start + (offset or 0)
        best = min(starts, key=lambda b: abs(b - target))
        if offset is not None and abs(best - target) > MAX_START_DRIFT_MS:
            continue
        starts.remove(best)
        deltas.append(best - start)
    return deltas


def same_subtitle(path_a: str, path_b: str) -> bool:
    """True when both files hold the same translation of the same video."""
    raw_a, raw_b = _cues(path_a), _cues(path_b)
    if not raw_a or not raw_b:
        return False
    cues_a = [(s, t) for s, _e, text in raw_a if (t := _norm_text(text))]
    cues_b = [(s, t) for s, _e, text in raw_b if (t := _norm_text(text))]
    if not cues_a or not cues_b:
        return False
    rough = _match(cues_a, cues_b, None)
    if not rough:
        return False
    offset = int(statistics.median(rough))
    if abs(offset) > MAX_START_DRIFT_MS:
        return False
    matched = len(_match(cues_a, cues_b, offset))
    return min(matched / len(cues_a), matched / len(cues_b)) >= MIN_CUE_MATCH


def _video_for(video_base: str) -> str | None:
    for ext in sorted(VIDEO_EXTENSIONS):
        candidate = video_base + ext
        if os.path.isfile(candidate):
            return candidate
    return None


def _find_alias_duplicates(media_path: str) -> list[tuple[str, str]]:
    """``(alias_path, canonical_path)`` pairs holding the same subtitle."""
    groups: dict[tuple, dict[str, list[str]]] = defaultdict(lambda: {"canonical": [], "alias": []})
    for path in _subtitle_files(media_path):
        classified = _classify_sidecar(path)
        if classified is None:
            continue
        video_base, canonical, modifier = classified
        token = _lang_token(path, modifier)
        key = (video_base, canonical, modifier, os.path.splitext(path)[1].lower())
        if token == canonical:
            groups[key]["canonical"].append(path)
        elif _is_alias_token(token, canonical):
            groups[key]["alias"].append(path)

    pairs: list[tuple[str, str]] = []
    for members in groups.values():
        if not members["canonical"]:
            continue  # an alias file alone is the only copy: leave it
        for alias in sorted(members["alias"]):
            for canonical_path in sorted(members["canonical"]):
                if same_subtitle(alias, canonical_path):
                    pairs.append((alias, canonical_path))
                    break
    return pairs


def execute_alias_duplicates(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Trash alias-coded sidecars that duplicate their canonical-coded sibling.

    Returns ``{"deleted", "bytes_freed", "batch_id"}``, or in a dry run
    ``{"would_delete", "examples"}``. ``config`` is unused: the rule has no
    options, and the trash is always the recoverable sidecar trash.
    """
    if not _media_path_reachable(media_path):
        return {"deleted": 0, "bytes_freed": 0, "aborted": "media_path unreachable"}

    pairs = _find_alias_duplicates(media_path)

    if dry_run:
        examples = []
        for alias, canonical_path in pairs[:20]:
            try:
                size = os.path.getsize(alias)
            except OSError:
                size = 0
            examples.append(
                {
                    "path": alias,
                    "size_bytes": size,
                    "reason": f"duplicate of {os.path.basename(canonical_path)}",
                }
            )
        return {"would_delete": len(pairs), "examples": examples}

    from services.sidecar_trash import get_batch_dir, trash_sidecar, write_manifest

    batch_id = uuid.uuid4().hex
    batch_dir = get_batch_dir(media_path, batch_id)
    manifest_files: list[dict] = []
    bytes_freed = 0
    changed: list[str] = []
    for alias, canonical_path in pairs:
        try:
            size = os.path.getsize(alias)
        except OSError:
            continue
        trashed, error = trash_sidecar(alias, media_path, batch_dir)
        if error:
            logger.warning("alias_duplicates: could not trash %s: %s", alias, error)
            continue
        manifest_files.append({"original": alias, "trashed": trashed})
        bytes_freed += size
        video_base = _classify_sidecar(canonical_path)[0]
        changed.append(_video_for(video_base) or canonical_path)
        logger.info(
            "Trashed (alias_duplicates): %s duplicates %s",
            alias,
            os.path.basename(canonical_path),
        )

    if manifest_files:
        try:
            write_manifest(batch_dir, batch_id, manifest_files)
        except OSError as exc:
            logger.warning("alias_duplicates: could not write trash manifest: %s", exc)
        from services.media_server_notify import notify_media_servers_batch

        notify_media_servers_batch(changed)

    return {
        "deleted": len(manifest_files),
        "bytes_freed": bytes_freed,
        "batch_id": batch_id if manifest_files else None,
    }
