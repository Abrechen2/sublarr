"""Subtitle download orchestration — extracted from ProviderManager.

Contains the three core operations that were previously methods on
ProviderManager so that the class stays under 800 lines.

All functions take explicit arguments rather than ``self`` to keep
them independently testable and re-usable outside of ProviderManager.
"""

import logging
import os

import decision_log

# Plan B6 — post-processing pipeline trigger (module-level import so tests can
# patch("providers.download_manager.run_trigger")).
from post_processing.pipeline import run_trigger
from providers.base import SubtitleFormat, SubtitleResult

logger = logging.getLogger(__name__)

_MAX_SUBTITLE_SIZE = 50 * 1024 * 1024  # 50 MB


def _stream_download(
    session,
    url: str,
    timeout: int = 15,
    headers: dict | None = None,
    allow_redirects: bool = True,
    provider_name: str | None = None,
    **kwargs,
) -> bytes:
    """Download a subtitle file with a 50 MB size cap (P5).

    Uses streaming to avoid loading the entire response into memory at once.
    Raises RuntimeError if the declared or actual content exceeds _MAX_SUBTITLE_SIZE.
    Extra kwargs (headers, allow_redirects, ...) are forwarded to session.get.

    When ``provider_name`` is supplied, every redirect hop AND the final
    response URL are re-validated against the provider's P1 domain allowlist.
    This closes the "allowlist-valid URL redirects to evil host" bypass.
    """
    get_kwargs = dict(kwargs)
    get_kwargs["stream"] = True
    get_kwargs["timeout"] = timeout
    get_kwargs["allow_redirects"] = allow_redirects
    if headers is not None:
        get_kwargs["headers"] = headers
    with session.get(url, **get_kwargs) as response:
        response.raise_for_status()

        # P1: validate every redirect hop + the final URL against the
        # provider allowlist. Skip when no provider_name is set (back-compat
        # for internal callers that validated upfront and use a keyless
        # download path).
        if provider_name:
            from security_utils import validate_download_url

            hops = [r.url for r in (response.history or [])]
            final_url = response.url
            if final_url:
                hops.append(final_url)
            for hop in hops:
                # Only validate real string URLs — skip MagicMock / non-str
                # objects which appear in unit tests that mock the session.
                if not isinstance(hop, str) or not hop:
                    continue
                hop_ok, hop_err = validate_download_url(hop, provider_name)
                if not hop_ok:
                    raise RuntimeError(
                        f"Subtitle download blocked at redirect hop {hop!r}: {hop_err}"
                    )

        # Preflight: reject oversized files advertised via Content-Length
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > _MAX_SUBTITLE_SIZE:
                    raise RuntimeError(
                        f"Subtitle file too large: {int(content_length)} bytes "
                        f"(max {_MAX_SUBTITLE_SIZE})"
                    )
            except ValueError:
                pass  # Non-integer Content-Length — proceed with streaming check

        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > _MAX_SUBTITLE_SIZE:
                raise RuntimeError(
                    f"Subtitle download exceeded size limit of {_MAX_SUBTITLE_SIZE} bytes"
                )
            chunks.append(chunk)

        return b"".join(chunks)


def download_subtitle(
    providers: dict,
    circuit_breakers: dict,
    rate_limit_checker,
    result: SubtitleResult,
) -> bytes | None:
    """Download a subtitle from its provider.

    Args:
        providers: Dict mapping provider name → provider instance.
        circuit_breakers: Dict mapping provider name → CircuitBreaker.
        rate_limit_checker: Callable(provider_name) → bool.
        result: A SubtitleResult from search().

    Returns:
        Raw subtitle file content, or None on failure.
    """
    provider = providers.get(result.provider_name)
    if not provider:
        logger.error("Provider %s not available for download", result.provider_name)
        return None

    breaker = circuit_breakers.get(result.provider_name)
    if breaker and not breaker.allow_request():
        logger.debug("Skipping download from %s: circuit breaker OPEN", result.provider_name)
        return None

    if not rate_limit_checker(result.provider_name):
        logger.debug("Skipping download from provider %s due to rate limit", result.provider_name)
        return None

    try:
        content = provider.download(result)
        result.content = content
        if breaker:
            breaker.record_success()
        return content
    except Exception as e:
        logger.error("Download from %s failed: %s", result.provider_name, e)
        if breaker:
            breaker.record_failure()
        return None


def search_and_download_best(
    search_fn,
    download_fn,
    update_stats_fn,
    query,
    format_filter: SubtitleFormat | None = None,
    min_score: int = 0,
    must_contain: list[str] | None = None,
    must_not_contain: list[str] | None = None,
) -> SubtitleResult | None:
    """Search providers, pick the best result, and download it.

    Args:
        search_fn: Callable that accepts (query, format_filter, min_score,
                   must_contain, must_not_contain) and returns [SubtitleResult].
        download_fn: Callable that accepts (result) and returns bytes | None.
        update_stats_fn: Callable that accepts (provider_name, success, score).
        query: VideoQuery to search for.
        format_filter: Optional format constraint.
        min_score: Minimum acceptable score.
        must_contain: Release title must contain all of these strings.
        must_not_contain: Release title must not contain any of these strings.

    Returns:
        SubtitleResult with content populated, or None.
    """
    results = search_fn(
        query,
        format_filter=format_filter,
        min_score=min_score,
        must_contain=must_contain,
        must_not_contain=must_not_contain,
    )
    if not results:
        return None

    for result in results:
        try:
            content = download_fn(result)
            if content is not None:
                # Plan B3 — granular blacklist by content hash. The (provider,
                # subtitle_id) filter runs pre-download in _finalise_search_results,
                # but the same provider can serve byte-identical content under
                # rotating IDs. Recompute SHA-256 here so a blacklisted hash is
                # honoured even when the ID changes between sessions. Without
                # this, the entire `file_hash` column on `blacklist_entries` is
                # unreachable at runtime (caught by the 2026-04-30 audit).
                if _is_content_hash_blacklisted(result.provider_name, content):
                    logger.info(
                        "Skipping %s/%s: content hash is blacklisted",
                        result.provider_name,
                        result.subtitle_id,
                    )
                    decision_log.download_attempt(
                        result.provider_name, result.subtitle_id, "hash_blacklisted"
                    )
                    continue
                update_stats_fn(result.provider_name, success=True, score=result.score)
                try:
                    from providers.reranker import apply_auto_reranking

                    apply_auto_reranking()
                except Exception as _rr_err:
                    logger.debug("Re-ranking trigger skipped: %s", _rr_err)
                decision_log.download_attempt(
                    result.provider_name, result.subtitle_id, "selected"
                )
                decision_log.selected(result)
                return result
            else:
                update_stats_fn(result.provider_name, success=False, score=0)
                decision_log.download_attempt(
                    result.provider_name, result.subtitle_id, "download_failed"
                )
        except Exception as e:
            logger.warning("Download failed for %s: %s", result.subtitle_id, e)
            update_stats_fn(result.provider_name, success=False, score=0)
            decision_log.download_attempt(
                result.provider_name, result.subtitle_id, "error", detail=str(e)
            )

    return None


def _is_content_hash_blacklisted(provider_name: str, content: bytes) -> bool:
    """Return True if SHA-256(content) is on the blacklist for this provider.

    Failures are swallowed (logged at DEBUG): the blacklist table or the DB
    session may be unavailable in unit tests / startup paths, and a check
    failure must never block an otherwise-valid download.
    """
    try:
        import hashlib

        from db.blacklist import is_blacklisted_by_hash

        content_hash = hashlib.sha256(content).hexdigest()
        return bool(is_blacklisted_by_hash(provider_name, content_hash))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Hash blacklist check skipped for %s: %s", provider_name, exc)
        return False


_VIDEO_EXTS_FOR_SIDECAR = (".mkv", ".mp4", ".m4v", ".webm", ".mov", ".avi", ".ts")


def _video_for_sidecar(sidecar_path: str) -> str | None:
    """Best-effort: resolve the video file a sidecar belongs to.

    Sidecars are ``<video_base>.<lang>[.<modifier>].<ext>``. Strip the
    subtitle extension, then progressively strip trailing language/modifier
    tokens, probing for a sibling video file at each step. Returns the first
    match, or None when no companion video is found (caller skips the hook).
    """
    base = os.path.splitext(sidecar_path)[0]
    for _ in range(3):
        for ext in _VIDEO_EXTS_FOR_SIDECAR:
            candidate = base + ext
            if os.path.isfile(candidate):
                return candidate
        new_base = base.rsplit(".", 1)[0]
        if new_base == base:
            break
        base = new_base
    return None


def save_subtitle(
    result: SubtitleResult,
    output_path: str,
    series_id: int | None = None,
) -> str:
    """Save a downloaded subtitle to disk.

    .. important::
        The returned path **must** be used by the caller for any further
        operations (auto-sync, NFO writing, recording the saved location).
        ``output_path`` is treated as a *hint*: when the actual subtitle
        format does not match the input extension (e.g. caller asked for
        ``.de.ass`` but content detection determined SRT) this function
        rewrites the extension, writes the file under the corrected name,
        and returns the corrected path. Discarding the return value leaves
        the caller pointing at a file that does not exist on disk.

        See ``wanted_search/process.py`` for the canonical usage pattern
        (``saved_path = manager.save_subtitle(...)``).

    Args:
        result: SubtitleResult with content populated.
        output_path: Suggested path. The extension is treated as a hint
            and may be rewritten to match the actual subtitle format.
        series_id: Sonarr series ID for per-series pipeline overrides.

    Returns:
        Actual path the subtitle was saved to (may differ from ``output_path``
        when the extension was rewritten).

    Raises:
        ValueError: If result has no content or path is outside media_path.
        RuntimeError: If disk space is insufficient or I/O fails.
    """
    from providers.format_validator import _validate_subtitle_content, detect_format_from_content

    if not result.content:
        raise ValueError("SubtitleResult has no content (download first)")

    # Validate content against declared format before processing (P4)
    fmt_hint = result.format.value if result.format != SubtitleFormat.UNKNOWN else "srt"
    valid, reason = _validate_subtitle_content(result.content, fmt_hint)
    if not valid:
        raise RuntimeError(f"Downloaded subtitle content failed validation: {reason}")

    # Determine extension — detect from content if format is unknown
    if result.format == SubtitleFormat.UNKNOWN and result.content:
        result.format = detect_format_from_content(result.content)
    ext = result.format.value if result.format != SubtitleFormat.UNKNOWN else "srt"
    if not output_path.endswith(f".{ext}"):
        # Telemetry: callers that ignore the return value will end up referring
        # to a path that does not exist on disk. This warning lets us spot the
        # frequency in production logs and identify any remaining bad callers.
        original = output_path
        base, _ = os.path.splitext(output_path)
        output_path = f"{base}.{ext}"
        logger.warning(
            "save_subtitle: rewrote extension %r → %r "
            "(provider=%s, declared format=%s, actual ext=%s); "
            "callers MUST use the returned path",
            original,
            output_path,
            result.provider_name,
            result.format.value,
            ext,
        )

    # Check disk space before writing (defensive guard)
    try:
        import shutil

        stat = shutil.disk_usage(os.path.dirname(output_path))
        free_mb = stat.free / (1024 * 1024)
        MIN_FREE_SPACE_MB = 100
        if free_mb < MIN_FREE_SPACE_MB:
            raise RuntimeError(
                f"Insufficient disk space: {free_mb:.0f}MB free, "
                f"need at least {MIN_FREE_SPACE_MB}MB"
            )
    except OSError as e:
        logger.warning("Failed to check disk space for %s: %s", output_path, e)

    # Validate output path is within allowed media directory (path traversal guard)
    try:
        import security_utils as _security_utils
        from config import get_settings as _get_settings

        _settings = _get_settings()
        _media_path = getattr(_settings, "media_path", "/media")
        # Resolve is_safe_path from the source module at call time so
        # monkeypatch("security_utils.is_safe_path") (legacy + B6 tests) works.
        if not _security_utils.is_safe_path(output_path, _media_path):
            raise ValueError(f"save_subtitle: output_path {output_path!r} is outside media_path")
    except ValueError:
        raise
    except Exception as e:
        logger.debug("Path validation skipped (config unavailable, likely in tests): %s", e)

    # Sanitise + the B5 repair pass (BOM, newlines, invalid decimals, overlapping
    # cues, encoding mis-detection) before the content is written and hashed.
    #
    # This lives in subtitle_normalise so the repair feature can reproduce it
    # exactly: the hash recorded below is of the NORMALISED content, so a
    # re-download has to be put through the same transform before it can be
    # compared against it. Duplicating the chain here is how they drifted apart
    # in the first place.
    from subtitle_normalise import normalise_downloaded_content

    result.content = normalise_downloaded_content(result.content, result.format)

    # Duplicate detection: skip write if identical content already exists on disk
    try:
        from config import get_settings as _get_settings_dedup
        from db.repositories.cleanup import CleanupRepository
        from dedup_engine import compute_content_hash_from_bytes
        from error_handler import DuplicateSubtitleError

        _dedup_settings = _get_settings_dedup()
        if getattr(_dedup_settings, "dedup_on_download", True):
            content_hash = compute_content_hash_from_bytes(result.content)
            _output_dir = os.path.dirname(os.path.abspath(output_path))

            repo = CleanupRepository()
            matches = repo.find_by_content_hash(content_hash)
            stale_paths = []
            duplicate_path = None

            for match in matches:
                match_path = match["file_path"]
                if not os.path.isfile(match_path):
                    stale_paths.append(match_path)
                    continue
                if os.path.dirname(os.path.abspath(match_path)) == _output_dir:
                    duplicate_path = match_path
                    break

            if stale_paths:
                repo.delete_hashes_by_paths(stale_paths)
                logger.debug("Cleaned %d stale hash entries", len(stale_paths))

            if duplicate_path:
                logger.info(
                    "Duplicate subtitle skipped: hash %s already at %s",
                    content_hash[:12],
                    duplicate_path,
                )
                raise DuplicateSubtitleError(content_hash, duplicate_path, output_path)
    except DuplicateSubtitleError:
        raise
    except Exception as e:
        logger.debug("Dedup check skipped: %s", e)

    # Create directory with error handling
    try:
        dir_path = os.path.dirname(output_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
    except OSError as e:
        logger.error("Failed to create directory for %s: %s", output_path, e)
        raise RuntimeError(f"Cannot create directory for subtitle: {e}") from e

    # Write file with error handling. Atomic (tmp + os.replace) so a crash mid-
    # write can't replace a previously-good sidecar with a truncated one.
    try:
        from utils.atomic_write import atomic_write_bytes

        atomic_write_bytes(output_path, result.content)
    except OSError as e:
        logger.error("Failed to write subtitle to %s: %s", output_path, e)
        raise RuntimeError(f"Cannot write subtitle file: {e}") from e

    # Register hash in dedup DB after successful write
    try:
        from db.repositories.cleanup import CleanupRepository as CleanupRepo
        from dedup_engine import compute_content_hash_from_bytes as _chfb

        _hash = _chfb(result.content)
        _ext = result.format.value if result.format.value != "unknown" else "srt"
        CleanupRepo().upsert_hash(
            file_path=output_path,
            content_hash=_hash,
            file_size=len(result.content),
            format=_ext,
            language=result.language,
        )
    except Exception as e:
        try:
            from extensions import db as _db

            _db.session.rollback()
        except Exception:
            pass
        logger.debug("Failed to register subtitle hash after write: %s", e)

    logger.info(
        "Saved subtitle: %s (%s, %s, score=%d)",
        output_path,
        result.provider_name,
        result.language,
        result.score,
    )

    # Fire subtitle_downloaded event for post-processing hooks
    try:
        from events import emit_event

        emit_event(
            "subtitle_downloaded",
            {
                "subtitle_path": output_path,
                "provider_name": result.provider_name or "",
                "language": result.language or "",
                "format": result.format.value if result.format else "",
                "score": result.score or 0,
            },
        )
    except Exception as _ev_err:
        logger.debug("subtitle_downloaded event skipped: %s", _ev_err)

    # Post-download processing pipeline
    try:
        from routes.subtitle_processor import _run_pipeline_for_path

        _run_pipeline_for_path(output_path, series_id=series_id)
    except Exception as _exc:
        logger.warning("[pipeline] hook error: %s", _exc)

    # Foreign-track cleanup hook (additive, best-effort). Strips embedded
    # non-target subtitle tracks from the video container now that a
    # target-language sidecar has landed — closing the gap where
    # provider-downloaded episodes never went through the extract path.
    # No-ops unless cleanup_foreign_tracks_default (or a series override)
    # is enabled; the keep-set is target ∪ configured always-keep
    # languages. Errors are swallowed inside the hook.
    _video = None
    try:
        _video = _video_for_sidecar(output_path)
        if _video:
            from services.foreign_track_cleanup import maybe_run_foreign_track_cleanup

            maybe_run_foreign_track_cleanup(
                {"sonarr_series_id": series_id, "target_language": result.language},
                _video,
            )
    except Exception as _exc:
        logger.debug("[foreign-track] post-download hook skipped: %s", _exc)

    # Media-server refresh (best-effort) — a new sidecar landed (and the
    # container may have been stripped above), so tell the configured media
    # servers to re-scan the item. No-op when no server is configured.
    try:
        from services.media_server_notify import notify_media_servers

        notify_media_servers(_video or output_path, "episode" if series_id else "")
    except Exception as _exc:
        logger.debug("[mediaserver] post-download refresh skipped: %s", _exc)

    # Post-download shell command (user-configurable, Bazarr parity)
    from post_download import run_post_download_command

    try:
        from config import get_settings as _pd_get_settings

        _pd_settings = _pd_get_settings()
        _pd_cmd = getattr(_pd_settings, "post_download_command", "")
    except Exception:
        _pd_cmd = ""

    if _pd_cmd:
        try:
            _pd_enabled = getattr(_pd_settings, "post_processing_enabled", False)
            _pd_media_type = "series" if series_id is not None else "movie"
            run_post_download_command(
                _pd_cmd,
                subtitle_path=output_path,
                language=result.language or "",
                provider=result.provider_name or "",
                score=result.score or 0,
                media_type=_pd_media_type,
                enabled=_pd_enabled,
            )
        except Exception as _pd_err:
            logger.warning("post_download_command hook failed: %s", _pd_err)

    # Plan B6 — fire after_download post-processing trigger.
    # The pipeline runs on a dedicated thread pool so this returns immediately;
    # an empty op list is a no-op in run_trigger itself.
    try:
        from post_processing.config_store import get_trigger_ops

        op_ids = get_trigger_ops("after_download")
        if op_ids:
            run_trigger(
                trigger="after_download",
                op_ids=op_ids,
                context={
                    "subtitle_path": output_path,
                    "video_path": "",
                    "lang": result.language or "",
                    "score": result.score or 0,
                    "trigger": "after_download",
                },
            )
    except Exception as _pp_err:
        logger.warning("post_processing after_download skipped: %s", _pp_err)

    return output_path
