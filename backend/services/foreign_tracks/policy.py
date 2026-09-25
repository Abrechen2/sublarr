"""Resolve the track variant policy for a file: global settings + overrides."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from services.foreign_tracks.select import TrackPolicy

logger = logging.getLogger(__name__)

_FIELDS = (
    "cleanup_track_variant_mode",
    "cleanup_keep_forced",
    "cleanup_keep_sdh",
    "cleanup_sidecar_policy",
)


def policy_from_settings(settings) -> TrackPolicy:
    return TrackPolicy(
        mode=getattr(settings, "cleanup_track_variant_mode", "all") or "all",
        keep_forced=bool(getattr(settings, "cleanup_keep_forced", True)),
        keep_sdh=bool(getattr(settings, "cleanup_keep_sdh", False)),
        sidecar_policy=getattr(settings, "cleanup_sidecar_policy", "keep_embedded")
        or "keep_embedded",
    )


def _from_resolved(resolved: dict) -> TrackPolicy:
    """Build a TrackPolicy from an ``inheritance_resolver.resolve_for_series/movie``
    result — a dict keyed by display name, each value a ResolvedSetting
    (``{"effective": ..., "source": ..., "chain": [...]}``)."""

    def effective(name):
        return resolved[name]["effective"]

    return TrackPolicy(
        mode=effective("cleanup_track_variant_mode"),
        keep_forced=bool(effective("cleanup_keep_forced")),
        keep_sdh=bool(effective("cleanup_keep_sdh")),
        sidecar_policy=effective("cleanup_sidecar_policy"),
    )


def resolve_policy(series_id: int | None = None, movie_id: int | None = None) -> TrackPolicy | None:
    """Resolve the effective policy for a series or movie.

    A series/movie without a settings row inherits the global policy. A
    resolution ERROR returns None — never the global policy, which may strip
    more than the override the user configured (final review I5). Callers
    treat None as "do not strip now": the queue drain books CLEANUP_FAILED
    (retry), ``override_paths`` marks the set incomplete, and the preview
    answers 503.
    """
    from config import get_settings
    from db.models.core import MovieSettings, SeriesSettings
    from extensions import db
    from services.inheritance_resolver import resolve_for_movie, resolve_for_series

    settings = get_settings()
    try:
        if series_id:
            row = db.session.get(SeriesSettings, series_id)
            if row is not None:
                return _from_resolved(
                    resolve_for_series(series=row, profile=None, global_cfg=settings)
                )
        if movie_id:
            row = db.session.get(MovieSettings, movie_id)
            if row is not None:
                return _from_resolved(
                    resolve_for_movie(movie=row, profile=None, global_cfg=settings)
                )
    except Exception:  # noqa: BLE001 — reported as None; callers refuse to strip
        logger.warning(
            "track policy: override resolution failed (series=%s movie=%s) — not stripping",
            series_id,
            movie_id,
            exc_info=True,
        )
        return None
    return policy_from_settings(settings)


def _has_override(row) -> bool:
    return any(getattr(row, name, None) is not None for name in _FIELDS)


def _is_switched_off(row) -> bool:
    return getattr(row, "cleanup_foreign_tracks", None) is False


@dataclass(frozen=True)
class OverrideSet:
    """What the sweep needs from the series/movie settings, resolved once per slice.

    ``pairs``    (mapped folder, policy) for every title with a policy override.
    ``excluded`` mapped folders of titles with ``cleanup_foreign_tracks=False``
                 — files under them are never stripped (final review I7).
    ``complete`` False when any title could not be resolved; a caller must
                 not strip on an incomplete set.
    ``failed``   the unresolved titles, e.g. ``("series 21", "movie 4")``.
    """

    pairs: list[tuple[str, TrackPolicy]] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    complete: bool = True
    failed: tuple[str, ...] = ()


class _UnresolvedError(Exception):
    """A title whose folder or policy cannot be known right now."""


def _confirmed_missing(client, cache: dict) -> bool:
    """Whether a None/empty lookup means the arr really does not know the title.

    The arr clients swallow connection errors and return None, so a None is
    only a confirmed "missing" when the arr answers its own health check.
    Checked once per client per resolution.
    """
    key = id(client)
    if key not in cache:
        try:
            cache[key] = bool(client.health_check()[0])
        except Exception:  # noqa: BLE001 — cannot confirm, so not "missing"
            logger.debug("track policy: arr health check failed", exc_info=True)
            cache[key] = False
    return cache[key]


def _lookup_path(kind: str, title_id: int, health: dict) -> str | None:
    """The title's folder as the arr reports it, or None when confirmed missing.

    Raises ``_UnresolvedError`` when the arr is unconfigured or does not answer.
    """
    if kind == "series":
        from sonarr_client import get_sonarr_client

        client = get_sonarr_client()
        if not client:
            raise _UnresolvedError("Sonarr is not configured")
        info = client.get_series_by_id(title_id)
    else:
        from radarr_client import get_radarr_client

        client = get_radarr_client()
        if not client:
            raise _UnresolvedError("Radarr is not configured")
        info = client.get_movie_by_id(title_id)

    path = (info or {}).get("path")
    if path:
        return path
    if _confirmed_missing(client, health):
        return None
    raise _UnresolvedError("no answer from the arr")


def override_paths() -> OverrideSet:
    """Resolve the folders of every series/movie with a policy override or with
    the cleanup switched off. Called once per sweep slice.

    - A title Sonarr/Radarr confirms missing (lookup None/empty while the arr
      answers its health check) is skipped with a warning; it does not make
      the set incomplete (final review I4).
    - An unconfigured or unreachable arr, a raising lookup, or an
      unresolvable policy marks the set incomplete and names the title in
      ``failed``: the sweep must never strip more than configured because an
      override could not be read.
    - A title with ``cleanup_foreign_tracks=False`` lands in ``excluded``
      (final review I7), whatever policy overrides it also carries.
    """
    from config_utils import map_path
    from db.models.core import MovieSettings, SeriesSettings
    from extensions import db

    pairs: list[tuple[str, TrackPolicy]] = []
    excluded: list[str] = []
    failed: list[str] = []
    health: dict = {}

    rows = [("series", r.sonarr_series_id, r) for r in db.session.query(SeriesSettings).all()]
    rows += [("movie", r.radarr_movie_id, r) for r in db.session.query(MovieSettings).all()]
    for kind, title_id, row in rows:
        switched_off = _is_switched_off(row)
        if not (switched_off or _has_override(row)):
            continue
        label = f"{kind} {title_id}"
        try:
            path = _lookup_path(kind, title_id, health)
            if path is None:
                logger.warning(
                    "track policy: %s has settings but its arr no longer knows it — skipped",
                    label,
                )
                continue
            if switched_off:
                excluded.append(map_path(path))
                continue
            if kind == "series":
                policy = resolve_policy(series_id=title_id)
            else:
                policy = resolve_policy(movie_id=title_id)
            if policy is None:
                raise _UnresolvedError("policy resolution failed")
            pairs.append((map_path(path), policy))
        except Exception as exc:  # noqa: BLE001 — one failing title must not abort the others
            failed.append(label)
            logger.warning(
                "track policy: %s unavailable (%s) — sweep will not strip until this resolves",
                label,
                exc,
                exc_info=not isinstance(exc, _UnresolvedError),
            )
    return OverrideSet(pairs=pairs, excluded=excluded, complete=not failed, failed=tuple(failed))


def _under(path: str, folder: str) -> bool:
    norm = os.path.normpath(path)
    root = os.path.normpath(folder)
    return norm == root or norm.startswith(root + os.sep)


def is_excluded(path: str, excluded: list[str]) -> bool:
    """Whether ``path`` lies inside one of the ``excluded`` folders."""
    return any(_under(path, folder) for folder in excluded)


def policy_for_path(
    path: str, overrides: list[tuple[str, TrackPolicy]], default: TrackPolicy
) -> TrackPolicy:
    """Longest matching folder prefix wins; a sibling folder that merely
    shares a text prefix (e.g. "Anime Two" vs "Anime") never matches."""
    best: tuple[int, TrackPolicy] | None = None
    for folder, policy in overrides:
        if _under(path, folder):
            root = os.path.normpath(folder)
            if best is None or len(root) > best[0]:
                best = (len(root), policy)
    return best[1] if best else default
