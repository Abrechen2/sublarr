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
from dataclasses import dataclass

from config import get_settings
from remux import RemuxError, remove_subtitle_streams, trash_non_target_sidecars
from services.cleanup_executors import _trash_path  # module-level so tests can patch it

logger = logging.getLogger(__name__)


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
                             ``remove_streams_from_container``.
        extracted            list of dicts {language, format, sub_index,
                             output_path} describing every sidecar that
                             ended up on disk — used by callers to decide
                             which one is "primary".

    Duplicate (lang, fmt) combinations are collapsed: only the first
    occurrence is extracted, the rest are still scheduled for container
    removal so the MKV ends up clean.
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
            any_extracted = True
            if stream_info.get("stream_index") is not None:
                streams_to_remove.append((stream_info["stream_index"], stream_info["sub_index"]))
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
            if stream_info.get("stream_index") is not None:
                streams_to_remove.append((stream_info["stream_index"], stream_info["sub_index"]))
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
    """
    if not extracted:
        return None, None, None

    target_lc = (target_language or "").lower() or None
    if target_lc:
        target_matches = [e for e in extracted if e["language"].startswith(target_lc[:2])]
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
) -> ExtractResult:
    """Run the full extract-and-cleanup pipeline against a container.

    Pipeline:
      1. Classify every text-based subtitle stream
      2. Extract each one to a sidecar (skipping duplicates)
      3. Remove the extracted streams from the container in one mkvmerge
         pass (with backup into ``remux_trash_dir``)
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

    remove_streams_from_container(file_path, streams_to_remove, log_label=log_label)

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
    """
    from config_language_data import normalize_language_code

    keep = {normalize_language_code(code) for code in profile.get("target_languages", []) if code}
    if getattr(settings, "wanted_auto_translate", False):
        src = getattr(settings, "source_language", "") or ""
        if src:
            keep.add(normalize_language_code(src))
    keep.discard("")
    return keep
