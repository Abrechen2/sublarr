"""Shared embedded-subtitle extraction pipeline.

Single source of truth for the "extract every text-based subtitle stream
from a video container, then trash sidecars whose language is not in the
caller's keep-set" workflow. Two call sites:

  - routes/wanted/extract.py::_extract_embedded_sub
        (auto path — drained by services.subtitle_automation_runner every
        ~2 minutes and also reachable via the per-item REST endpoint)

  - routes/wanted/batch_probe.py::_process_probe_result
        (UI-driven Batch-Probe action)

Before this module both paths diverged: the auto path picked one "best"
stream and ignored the rest, while the UI path extracted everything and
did the non-target cleanup. Users with a Sonarr-managed library expected
"extract + only keep wanted languages" to be active everywhere — see
the user request that motivated this refactor.

Trash semantics: the cleanup is recoverable. Both the container-removal
backup (`remove_subtitle_streams`) and the sidecar trash
(`trash_non_target_sidecars`) write into ``remux_trash_dir`` (default
``.sublarr/trash`` under each media root) so nothing is hard-deleted.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from flask import current_app

from config import get_settings
from db.activity import log_activity
from db.models.activity import EVENT_EXTRACT
from events import emit_event
from remux import RemuxError, remove_subtitle_streams, trash_non_target_sidecars
from services.background_tasks import submit_background
from services.cleanup_executors import _trash_path  # module-level so tests can patch it

logger = logging.getLogger(__name__)

# ISO-639 shape for container language tags (mirrors routes/tracks._LANG_RE).
_LANG_TAG_RE = re.compile(r"^[a-z]{2,3}(-[a-z]{2,4})?$")


# ---------------------------------------------------------------------------
# Public dataclass returned by extract_and_cleanup
# ---------------------------------------------------------------------------


@dataclass
class ExtractResult:
    """Outcome of a full extract-and-cleanup pass.

    ``primary_*`` fields describe the sidecar that the caller would treat
    as the "main" output (e.g. for DB updates). They prefer a target-lang
    sidecar over any other language; if the file lacked a target-lang
    track entirely they fall back to the first extracted track.
    ``primary_*`` is None when nothing was extracted (e.g. only image
    subtitle streams in the container — those are skipped).
    """

    any_extracted: bool
    extracted: list[dict]  # [{language, format, sub_index, output_path}, ...]
    primary_output_path: str | None
    primary_format: str | None
    primary_language: str | None
    sidecars_trashed: int


# ---------------------------------------------------------------------------
# Stream classification
# ---------------------------------------------------------------------------


def collect_subtitle_streams(probe_data: dict) -> list[dict]:
    """Return text-based subtitle streams from an ffprobe output dict.

    The result lists each stream once with both ``sub_index`` (0-based
    counter over subtitle streams only — used for sidecar naming) and
    ``stream_index`` (the global ffprobe index, required for
    container-removal). Image-based formats (PGS, VobSub) are skipped
    because mkvmerge cannot losslessly extract them as text sidecars.

    Honours ``Settings.embedded_allow_sdh`` — when False, SDH/CC/HI
    streams are dropped entirely so the cleanup pass never even sees
    them.
    """
    from ass_probe import is_sdh_stream

    allow_sdh = True
    try:
        allow_sdh = bool(getattr(get_settings(), "embedded_allow_sdh", True))
    except Exception:
        logger.debug("embedded_allow_sdh unavailable; assuming True")

    sub_streams: list[dict] = []
    sub_index = 0
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        codec = stream.get("codec_name", "").lower()
        if codec in ("ass", "ssa"):
            fmt = "ass"
        elif codec in ("subrip", "srt", "mov_text", "webvtt", "text", "microdvd"):
            fmt = "srt"
        else:
            sub_index += 1
            continue  # PGS, VobSub, etc.
        sdh = is_sdh_stream(stream)
        if sdh and not allow_sdh:
            sub_index += 1
            continue
        lang = (stream.get("tags", {}).get("language", "und") or "und").lower()
        # The tag is interpolated into the sidecar output path — reject
        # anything that does not look like an ISO-639 code (path-traversal
        # defence, same rule as routes/tracks._safe_language).
        if not _LANG_TAG_RE.match(lang):
            lang = "und"
        sub_streams.append(
            {
                "sub_index": sub_index,
                "stream_index": stream.get("index"),
                "format": fmt,
                "language": lang,
                "is_sdh": sdh,
            }
        )
        sub_index += 1
    return sub_streams


# ---------------------------------------------------------------------------
# Per-stream extract
# ---------------------------------------------------------------------------


def extract_streams(
    file_path: str,
    sub_streams: list[dict],
    *,
    log_label: str = "extractor",
) -> tuple[bool, list[tuple[int, int]], list[dict]]:
    """Extract ``sub_streams`` from ``file_path`` to sidecar files.

    Returns a tuple ``(any_extracted, streams_to_remove, extracted)``:
        any_extracted        True when at least one sidecar exists on disk
                             after this call (either freshly written or
                             pre-existing from an earlier run).
        streams_to_remove    list of (global_stream_index, sub_index)
                             tuples to feed back into
                             ``remove_streams_from_container``. Contains
                             ONLY streams that were freshly extracted in
                             this pass — a stream whose sidecar already
                             existed, or that was skipped as a duplicate,
                             is never a removal candidate (issue #159:
                             repeat runs kept remuxing, and duplicate
                             (lang, fmt) tracks — e.g. anime "Full" +
                             "Signs" both tagged eng — were removed
                             without ever being extracted).
        extracted            list of dicts {language, format, sub_index,
                             output_path} describing every sidecar that
                             ended up on disk — used by callers to decide
                             which one is "primary".

    Duplicate (lang, fmt) combinations are collapsed: only the first
    occurrence is extracted; the rest stay in the container untouched.
    """
    from ass_utils import extract_subtitle_stream, get_subtitle_stream_output_path

    any_extracted = False
    streams_to_remove: list[tuple[int, int]] = []
    extracted: list[dict] = []
    seen_lang_fmt: set[tuple[str, str]] = set()

    for stream_info in sub_streams:
        lang_fmt = (stream_info["language"], stream_info["format"])
        out = get_subtitle_stream_output_path(file_path, stream_info)

        if os.path.exists(out):
            # Sidecar already on disk from an earlier run — nothing was
            # extracted now, so the stream must NOT become a removal
            # candidate (a repeat run would otherwise remux the container
            # again and again).
            any_extracted = True
            if lang_fmt not in seen_lang_fmt:
                extracted.append(
                    {
                        "language": stream_info["language"],
                        "format": stream_info["format"],
                        "sub_index": stream_info["sub_index"],
                        "output_path": out,
                    }
                )
                seen_lang_fmt.add(lang_fmt)
            continue

        if lang_fmt in seen_lang_fmt:
            # Duplicate (lang, fmt): this stream's content is NOT in the
            # sidecar written for the first occurrence (distinct tracks —
            # e.g. "Full Dialogue" vs "Signs & Songs" — collapse to the
            # same output path). It stays in the container.
            continue

        try:
            extract_subtitle_stream(file_path, stream_info, out)
            logger.info(
                "[%s]: extracted %s → %s",
                log_label,
                stream_info["language"],
                out,
            )
            any_extracted = True
            seen_lang_fmt.add(lang_fmt)
            extracted.append(
                {
                    "language": stream_info["language"],
                    "format": stream_info["format"],
                    "sub_index": stream_info["sub_index"],
                    "output_path": out,
                }
            )
            if stream_info.get("stream_index") is not None:
                streams_to_remove.append((stream_info["stream_index"], stream_info["sub_index"]))
        except Exception as sub_exc:
            logger.warning(
                "[%s]: stream %d extract failed: %s",
                log_label,
                stream_info["sub_index"],
                sub_exc,
            )

    return any_extracted, streams_to_remove, extracted


# ---------------------------------------------------------------------------
# Container cleanup
# ---------------------------------------------------------------------------


def filter_streams_safe_to_remove(
    sub_streams: list[dict],
    streams_to_remove: list[tuple[int, int]],
    keep_langs: set[str],
) -> list[tuple[int, int]]:
    """Drop removal candidates whose language must be kept.

    Defence in depth for the container rewrite (issue #159: the eng target
    stream was remuxed out along with everything else):

      - A stream whose ``normalize_language_code(language)`` is in
        ``keep_langs`` is never removed.
      - Unknown/``und`` tags are treated as KEEP (cannot prove they are
        disposable).
      - An empty ``keep_langs`` removes NOTHING — mirrors the
        "empty target set → no-op" guard in
        ``remux.remove_foreign_subtitle_streams``: never strip blind.
    """
    if not streams_to_remove:
        return []
    if not keep_langs:
        return []

    from config_language_data import _REVERSE_LANGUAGE_TAGS, normalize_language_code

    lang_by_stream_index = {
        s.get("stream_index"): (s.get("language") or "und") for s in sub_streams
    }
    safe: list[tuple[int, int]] = []
    for stream_index, sub_index in streams_to_remove:
        raw = (lang_by_stream_index.get(stream_index) or "und").lower()
        if raw not in _REVERSE_LANGUAGE_TAGS:
            # Unknown or und tag — cannot prove it is disposable, keep it.
            continue
        if normalize_language_code(raw) in keep_langs:
            continue
        safe.append((stream_index, sub_index))
    return safe


def remove_streams_from_container(
    file_path: str,
    streams_to_remove: list[tuple[int, int]],
    *,
    log_label: str = "extractor",
) -> None:
    """Remove all extracted subtitle streams from the video container.

    Uses ``remux.remove_subtitle_streams`` which writes a backup into the
    configured ``remux_trash_dir`` before rewriting the container, so the
    operation is reversible if the caller (or the user via the trash UI)
    needs to roll back.
    """
    if not streams_to_remove:
        return
    try:
        settings = get_settings()
        bak = remove_subtitle_streams(
            video_path=file_path,
            streams=streams_to_remove,
            use_reflink=getattr(settings, "remux_use_reflink", True),
            trash_dir=getattr(settings, "remux_trash_dir", ".sublarr"),
        )
        if bak is None:
            # Hardlink policy refused the rewrite (already logged in remux).
            return
        logger.info(
            "[%s]: removed %d stream(s) from container (backup: %s)",
            log_label,
            len(streams_to_remove),
            bak,
        )
    except (RemuxError, Exception) as remux_exc:
        logger.warning(
            "[%s]: container removal failed: %s",
            log_label,
            remux_exc,
        )


# ---------------------------------------------------------------------------
# Sidecar trash (non-target)
# ---------------------------------------------------------------------------


def trash_unwanted_sidecars(
    file_path: str,
    keep_langs: set[str],
    *,
    log_label: str = "extractor",
) -> int:
    """Move sidecars whose language is not in ``keep_langs`` into the trash.

    Returns the number of files moved. ``trash_non_target_sidecars``
    refuses to delete ambiguous tags (``und``, anything not in the lookup
    table) so the caller does not need to defend against false positives.
    Errors are caught and logged — sidecar cleanup must never break
    extraction.
    """
    if not keep_langs:
        return 0
    try:
        settings = get_settings()
        trashed = trash_non_target_sidecars(
            video_path=file_path,
            keep_langs=keep_langs,
            trash_dir=getattr(settings, "remux_trash_dir", ".sublarr"),
        )
        if trashed:
            logger.info(
                "[%s]: trashed %d non-target sidecar(s) (keep=%s)",
                log_label,
                len(trashed),
                sorted(keep_langs),
            )
        return len(trashed)
    except Exception as cleanup_exc:
        logger.warning(
            "[%s]: sidecar cleanup failed: %s",
            log_label,
            cleanup_exc,
        )
        return 0


# ---------------------------------------------------------------------------
# Going-forward signs purge
# ---------------------------------------------------------------------------


def purge_signs_after_extract(
    video_path: str,
    *,
    log_label: str = "extractor",
) -> int:
    """Trash freshly-extracted sidecars that classify as signs/forced/songs.

    Runs the same SignsRemovalLevel classifier as the library-wide cleanup rule
    (services.cleanup_signs) so newly extracted sidecars do not re-accumulate
    after the retroactive sweep.

    Last-sub guard: a sidecar is never trashed if it would leave the
    (video_base, canonical_lang) pair with zero subtitles on disk.

    Stable-file guard: intentionally omitted.  Extracted files are already
    closed by the time this runs — there is no write-race to protect against.

    Returns the number of sidecars trashed.
    """
    import glob as _glob

    # Late imports so ``patch("config.get_settings", ...)`` works in tests and
    # so the heavy subtitle-signs deps load only when actually needed.
    from config import get_settings as _get_settings
    from remux import _SIDECAR_EXTS
    from services.cleanup_executors import _classify_sidecar
    from services.subtitle_signs import SignsRemovalLevel, classify_sidecar, is_removable

    try:
        settings = _get_settings()
        level = SignsRemovalLevel.from_str(getattr(settings, "cleanup_signs_removal_level", "off"))
    except Exception:
        return 0

    if level is SignsRemovalLevel.OFF:
        return 0

    use_density = level is SignsRemovalLevel.SIGNS_FORCED_SONGS
    video_base = os.path.splitext(video_path)[0]

    # Enumerate all sidecars belonging to this video (same glob pattern used
    # by trash_non_target_sidecars in remux).
    candidates: list[str] = []
    for ext in _SIDECAR_EXTS:
        candidates.extend(_glob.glob(f"{video_base}.*{ext}"))

    if not candidates:
        return 0

    # Build per-(video_base, canonical_lang) counts for the last-sub guard.
    # Modifier is excluded intentionally: a .signs. sidecar and its
    # full-dialogue peer share the same bucket so the guard correctly permits
    # removing the signs file when a full one exists.
    def _guard_key(path: str) -> tuple:
        cl = _classify_sidecar(path)
        if cl is None:
            return (path,)
        vb, lang, _mod = cl
        return (vb, lang)

    per_key: dict[tuple, int] = {}
    for p in candidates:
        key = _guard_key(p)
        per_key[key] = per_key.get(key, 0) + 1

    trashed = 0
    for path in candidates:
        try:
            subtype = classify_sidecar(path, use_density=use_density)
        except Exception as exc:
            logger.debug("[%s]: signs purge: classify failed for %s: %s", log_label, path, exc)
            continue
        if not is_removable(subtype, level):
            continue
        key = _guard_key(path)
        if per_key.get(key, 0) <= 1:
            logger.info("[%s]: signs purge: last-sub guard kept %s", log_label, path)
            continue
        if _trash_path(path):
            trashed += 1
            per_key[key] -= 1
            logger.info("[%s]: signs purge: trashed %s (%s)", log_label, path, subtype)
        else:
            logger.warning("[%s]: signs purge: could not trash %s", log_label, path)

    return trashed


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _pick_primary(
    extracted: list[dict],
    target_language: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Return (output_path, format, language) for the "primary" sidecar.

    Prefers a sidecar whose language matches ``target_language``; falls
    back to the first sidecar in the list if none match. ``ass`` wins
    over ``srt`` when both languages match (.ass plays better with
    advanced styling).

    Matching is canonical-code equality, not prefix comparison: the old
    ``startswith(target[:2])`` missed "ger" for target "de" (picking a
    random first track as primary) and false-matched "est" (Estonian)
    for target "es".
    """
    if not extracted:
        return None, None, None

    from config_language_data import normalize_language_code

    target_lc = normalize_language_code((target_language or "").lower()) or None
    if target_lc:
        target_matches = [
            e for e in extracted if normalize_language_code(e["language"]) == target_lc
        ]
        if target_matches:
            ass_first = sorted(target_matches, key=lambda e: 0 if e["format"] == "ass" else 1)
            chosen = ass_first[0]
            return chosen["output_path"], chosen["format"], chosen["language"]

    chosen = extracted[0]
    return chosen["output_path"], chosen["format"], chosen["language"]


def extract_and_cleanup(
    file_path: str,
    probe_data: dict,
    keep_langs: set[str],
    *,
    target_language: str | None = None,
    log_label: str = "extractor",
    remove_from_container: bool = False,
) -> ExtractResult:
    """Run the full extract-and-cleanup pipeline against a container.

    Pipeline:
      1. Classify every text-based subtitle stream
      2. Extract each one to a sidecar (skipping duplicates)
      3. Only when ``remove_from_container`` is True: remove the freshly
         extracted streams from the container in one mkvmerge pass (with
         backup into ``remux_trash_dir``). Streams whose language is in
         ``keep_langs`` are never removed, and an empty ``keep_langs``
         removes nothing (see ``filter_streams_safe_to_remove``).
      4. Trash sidecars on disk whose language is not in ``keep_langs``

    Args:
        file_path: Absolute path to the video file.
        probe_data: Pre-computed ffprobe output for ``file_path``.
        keep_langs: Normalised ISO 639-1 language codes to retain (e.g.
            the profile's target_languages, plus source_language when
            auto-translation is enabled). Empty set → no sidecar cleanup.
        target_language: Optional hint for which language the caller
            considers "primary". Used solely to pick the
            ``primary_output_path``/``primary_format``/``primary_language``
            return values; does not affect what gets extracted or
            trashed.
        log_label: Tag prepended to log lines so each call site is
            identifiable in production logs.
        remove_from_container: Opt-in for the container rewrite (step 3).
            Defaults to False — issue #159: the rewrite used to be an
            unconditional side effect of extraction, stripping streams
            (including target-language ones) from users who never asked
            for it and breaking *arr hardlinks.

    Returns:
        ExtractResult — see dataclass docstring.
    """
    sub_streams = collect_subtitle_streams(probe_data)
    if not sub_streams:
        return ExtractResult(
            any_extracted=False,
            extracted=[],
            primary_output_path=None,
            primary_format=None,
            primary_language=None,
            sidecars_trashed=0,
        )

    any_extracted, streams_to_remove, extracted = extract_streams(
        file_path, sub_streams, log_label=log_label
    )

    if remove_from_container:
        safe_to_remove = filter_streams_safe_to_remove(sub_streams, streams_to_remove, keep_langs)
        remove_streams_from_container(file_path, safe_to_remove, log_label=log_label)
    elif streams_to_remove:
        logger.debug(
            "[%s]: container removal disabled — keeping %d extracted stream(s) in %s",
            log_label,
            len(streams_to_remove),
            file_path,
        )

    sidecars_trashed = 0
    if any_extracted and keep_langs:
        sidecars_trashed = trash_unwanted_sidecars(file_path, keep_langs, log_label=log_label)

    # Going-forward signs purge: trash signs/forced/songs sidecars produced by
    # this extract pass so the library does not re-accumulate them after the
    # retroactive sweep (Task 9).
    if any_extracted:
        sidecars_trashed += purge_signs_after_extract(file_path, log_label=log_label)

    primary_output_path, primary_format, primary_language = _pick_primary(
        extracted, target_language
    )

    return ExtractResult(
        any_extracted=any_extracted,
        extracted=extracted,
        primary_output_path=primary_output_path,
        primary_format=primary_format,
        primary_language=primary_language,
        sidecars_trashed=sidecars_trashed,
    )


# ---------------------------------------------------------------------------
# Wanted-item extraction entry point (moved from routes/wanted/extract.py)
# ---------------------------------------------------------------------------


def validate_extract_target(file_path: str) -> str | None:
    """Defence-in-depth boundary check on a wanted-item file_path before we
    fork ffmpeg/mkvmerge against it.

    Audit E1-1: the scanner historically wrote arbitrary paths into
    ``wanted_items.file_path`` (the standalone S0-2 fix closed that for
    new rows but legacy data may persist). Refusing extraction against
    a path that escapes ``settings.media_path`` keeps an attacker-
    controlled DB row from steering ffmpeg at ``/etc/anything``.
    Returns an error message string when the path is unsafe, None when
    extraction may proceed.
    """
    try:
        from config import get_settings as _get_settings
        from security_utils import is_safe_path

        media_path = getattr(_get_settings(), "media_path", "")
    except Exception:
        return None  # Settings not available; trust caller (test harness).
    if not media_path:
        return None
    if not is_safe_path(file_path, media_path):
        logger.warning(
            "extract: refusing path outside media_path: %s (media_path=%s)",
            file_path,
            media_path,
        )
        return "file_path is outside the configured media_path"
    return None


def extract_embedded_sub(
    item_id: int,
    file_path: str,
    auto_translate: bool = False,
    *,
    remove_from_container: bool | None = None,
) -> dict:
    """Extract embedded subtitles for a wanted item.

    Callable from outside a Flask request context (e.g. from the scanner).
    Returns a result dict with keys: status, output_path, format, language.
    Raises on hard errors; caller is responsible for exception handling.

    Moved here from ``routes/wanted/extract.py::_extract_embedded_sub``
    (2026-07-02) so services no longer import from the routes layer; the
    old name remains there as a delegating compat shim.

    Behaviour (rev. with shared embedded_extractor pipeline):
      - Extracts EVERY text-based subtitle stream the container offers,
        not just the "best" one. Image subtitles (PGS/VobSub) are skipped.
      - Container stream removal is OPT-IN (issue #159): only when
        ``embedded_extract_remove_from_container`` is enabled (or the
        caller passes ``remove_from_container=True``) are freshly
        extracted streams remuxed out — with a backup in
        ``remux_trash_dir``, and never streams in the keep-languages set.
      - Trashes any sidecar whose language is not in the wanted item's
        profile target_languages — also into ``remux_trash_dir``.
      - Returns the "primary" sidecar (the target-lang match, falling
        back to the first extracted file) so existing callers keep
        receiving a single output_path/format/language.

    Args:
        item_id: ID of the wanted item.
        file_path: Absolute path to the media file.
        auto_translate: If True, trigger translation of the primary
            extracted SRT after extraction. Translation is a Beta-gated
            feature in production; the scheduler-driven drain passes
            False so it stays manual.
        remove_from_container: Tri-state opt-in for the container rewrite.
            None (default) resolves to the
            ``embedded_extract_remove_from_container`` setting.
    """
    # Lazy imports below are intentional: tests patch these at their source
    # modules (e.g. ``patch("ass_utils.get_media_streams")``,
    # ``patch("config.get_settings")``) and rely on call-time resolution.
    from ass_utils import get_media_streams
    from config import get_settings as _get_settings
    from db.wanted import get_wanted_item, update_existing_sub, update_wanted_status

    settings = _get_settings()

    item = get_wanted_item(item_id)
    if not item:
        raise ValueError(f"Wanted item {item_id} not found")

    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")

    boundary_err = validate_extract_target(file_path)
    if boundary_err:
        raise ValueError(boundary_err)

    if not file_path.lower().endswith((".mkv", ".mp4", ".m4v")):
        raise ValueError(f"File is not a video container (MKV/MP4): {file_path}")

    target_language = item.get("target_language") or settings.target_language

    # Resolve which languages the per-series / per-movie profile asks
    # us to keep. Sidecars in other languages get moved to the trash dir
    # after the extract pass so the user only retains what they want —
    # everything is recoverable via the trash UI.
    profile = resolve_profile_for_item(item, settings)
    keep_langs = compute_keep_langs(profile, settings)

    probe_data = get_media_streams(file_path, use_cache=True)

    if remove_from_container is None:
        remove_from_container = bool(
            getattr(settings, "embedded_extract_remove_from_container", False)
        )

    result = extract_and_cleanup(
        file_path=file_path,
        probe_data=probe_data,
        keep_langs=keep_langs,
        target_language=target_language,
        log_label=f"auto-extract item {item_id}",
        remove_from_container=remove_from_container,
    )

    if not result.any_extracted or result.primary_output_path is None:
        raise LookupError(f"No suitable subtitle stream found in {file_path}")

    output_path = result.primary_output_path
    primary_format = result.primary_format or "srt"

    # Plan B5 — run repair on the primary extracted track (opt-outable).
    # Fixes BOM, newlines, invalid decimals, overlapping cues, encoding
    # mis-detection. Must never abort extraction — fall through on any error.
    #
    # Audit Gemini-2026-05-09 R4: the repair write used to be a plain
    # ``Path.write_bytes`` against the live sidecar. A crash or ENOSPC
    # mid-write would truncate the freshly-extracted file with no trash
    # backup to fall back to. Same atomicity contract as the
    # ``extract_subtitle_stream`` rewrite (G5/G12) — write to a temp
    # file in the same directory, then ``os.replace`` it into place.
    try:
        if getattr(settings, "enable_subtitle_repair", True):
            import tempfile as _repair_tempfile
            from pathlib import Path as _RepairPath

            from subtitle_repair import repair_bytes as _repair_bytes

            _ext = _RepairPath(output_path).suffix.lstrip(".") or "srt"
            _data = _RepairPath(output_path).read_bytes()
            _repaired = _repair_bytes(_data, fmt=_ext)
            if _repaired != _data:
                _out_dir = os.path.dirname(output_path) or "."
                _suffix = _RepairPath(output_path).suffix or ".tmp"
                _fd, _tmp_repair = _repair_tempfile.mkstemp(suffix=_suffix, dir=_out_dir)
                try:
                    with os.fdopen(_fd, "wb") as _fh:
                        _fh.write(_repaired)
                    os.replace(_tmp_repair, output_path)
                    _tmp_repair = ""  # ownership transferred
                finally:
                    if _tmp_repair:
                        try:
                            os.unlink(_tmp_repair)
                        except OSError:
                            pass
    except Exception as _repair_err:
        logger.warning(
            "subtitle_repair on embedded extract skipped for %s: %s",
            output_path,
            _repair_err,
        )

    # Mark item as extracted — keep visible in Wanted for user-initiated cleanup/translate
    update_existing_sub(item_id, primary_format)
    update_wanted_status(item_id, "extracted")
    emit_event(
        "wanted_item_processed",
        {
            "wanted_id": item_id,
            "status": "extracted",
            "output_path": output_path,
            "source": "embedded",
            "extracted_count": len(result.extracted),
            "sidecars_trashed": result.sidecars_trashed,
        },
    )

    log_activity(
        EVENT_EXTRACT,
        file_path=str(file_path),
        status="success",
        details={
            "format": primary_format,
            "output_path": output_path,
            "wanted_id": item_id,
            "extracted_count": len(result.extracted),
            "sidecars_trashed": result.sidecars_trashed,
        },
    )

    if auto_translate and primary_format == "srt":
        # Audit C2-3: the worker reads the language profile and writes
        # translation_events via the SQLAlchemy session, so it MUST run
        # inside an app context. The previous version raised
        # ``RuntimeError: Working outside of application context`` which
        # got caught by the catch-all and silently dropped the
        # translation. Capture the current app once on the request
        # thread, then push an app context inside the worker.
        try:
            from translator import Translator

            try:
                _captured_app = current_app._get_current_object()
            except RuntimeError:
                _captured_app = None  # invoked outside a request (scanner)

            def _translate_async():
                ctx = _captured_app.app_context() if _captured_app is not None else None
                try:
                    if ctx is not None:
                        ctx.push()
                    translator = Translator()
                    translator.translate_file(output_path, target_language=target_language)
                    # The translated sidecar now exists — the synchronous
                    # combine below ran at extract time when the target language
                    # was still missing, so re-fire it here (V1.6 #1 auto-combine
                    # after auto-translate). maybe_auto_combine never raises.
                    from services.combine_service import maybe_auto_combine

                    maybe_auto_combine(str(file_path), profile=profile)
                except Exception as _exc:
                    logger.warning("[Auto-Translate] Failed for item %d: %s", item_id, _exc)
                finally:
                    if ctx is not None:
                        try:
                            ctx.pop()
                        except Exception:
                            pass

            submit_background(_translate_async)
        except Exception as exc:
            logger.warning(
                "[Auto-Translate] Could not start translation thread for item %d: %s", item_id, exc
            )

    # Automatic per-profile combine (V1.6 #1): if this profile enables combine
    # and every target-language sidecar now exists, compose the combined file.
    # Best-effort — maybe_auto_combine never raises, but keep the call guarded.
    try:
        from services.combine_service import maybe_auto_combine

        maybe_auto_combine(str(file_path), profile=profile)
    except Exception as _combine_err:  # pragma: no cover - defensive
        logger.debug("auto-combine after extract skipped for %s: %s", file_path, _combine_err)

    return {
        "status": "extracted",
        "output_path": output_path,
        "format": primary_format,
        "language": result.primary_language or "",
        "extracted_count": len(result.extracted),
        "sidecars_trashed": result.sidecars_trashed,
    }


# ---------------------------------------------------------------------------
# Profile resolution helper (shared with batch_probe)
# ---------------------------------------------------------------------------


def resolve_profile_for_item(item: dict, settings) -> dict:
    """Return the language profile that governs a wanted item.

    Preference order:
      1. Per-series profile (for episodes) via get_series_profile
      2. Per-movie profile (for movies) via get_movie_profile
      3. Default profile

    The result always has ``target_languages`` populated so callers can
    treat it as a simple dict without defensive ``get`` calls.
    """
    from db.profiles import get_default_profile, get_movie_profile, get_series_profile

    try:
        if item.get("sonarr_series_id"):
            profile = get_series_profile(item["sonarr_series_id"])
        elif item.get("radarr_movie_id"):
            profile = get_movie_profile(item["radarr_movie_id"])
        else:
            profile = get_default_profile()
    except Exception as exc:
        logger.debug("Profile lookup failed for item %s: %s", item.get("id"), exc)
        profile = get_default_profile()

    if not profile.get("target_languages"):
        fallback = getattr(settings, "target_language", "")
        profile = dict(profile)
        profile["target_languages"] = [fallback] if fallback else []
    return profile


def compute_keep_langs(profile: dict, settings) -> set[str]:
    """Return the normalised set of languages the cleanup pass must retain.

    Always includes the profile's ``target_languages``. Adds
    ``settings.source_language`` when ``wanted_auto_translate`` is enabled
    so the source-lang sidecar survives long enough to be translated.

    Script-variant targets (zh-hans, zh-hant) also keep their base code —
    containers/sidecars are usually tagged with the generic language
    ("chi"/"zho"/"zh" → "zh"), and those must never be trashed for a
    zh-hans profile.

    ``und``/``und1``/``und2`` placeholders are dropped: a keep-set of just
    "undetermined" would pass the non-empty guards downstream and turn the
    "empty set → no-op" safety design into "trash every recognised
    language".
    """
    from config_language_data import normalize_language_code

    keep: set[str] = set()
    codes = list(profile.get("target_languages", []))
    if getattr(settings, "wanted_auto_translate", False):
        src = getattr(settings, "source_language", "") or ""
        if src:
            codes.append(src)
    for code in codes:
        if not code:
            continue
        normalised = normalize_language_code(code)
        keep.add(normalised)
        if "-" in normalised:
            keep.add(normalised.split("-", 1)[0])
    keep.difference_update({"", "und", "und1", "und2"})
    return keep
