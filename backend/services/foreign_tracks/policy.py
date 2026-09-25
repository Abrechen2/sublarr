"""Resolve the track variant policy for a file: global settings + overrides."""

from __future__ import annotations

import logging
import os

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


def resolve_policy(series_id: int | None = None, movie_id: int | None = None) -> TrackPolicy:
    """Resolve the effective policy for a series or movie, falling back to the
    global policy on any resolution failure — never to "strip more"."""
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
    except Exception:  # noqa: BLE001 — fall back to the global policy, never to "strip more"
        logger.warning("track policy: override resolution failed", exc_info=True)
    return policy_from_settings(settings)


def _has_override(row) -> bool:
    return any(getattr(row, name, None) is not None for name in _FIELDS)


def override_paths() -> tuple[list[tuple[str, TrackPolicy]], bool]:
    """Resolve one (mapped folder path, policy) pair per series/movie that has
    at least one of the four override columns set. Called once per sweep
    slice.

    Returns ``(pairs, complete)``. ``complete`` is False when ANY overridden
    series/movie could not be resolved — the Sonarr/Radarr client raised, was
    not configured (falsy), or returned no path. A caller MUST treat
    ``complete=False`` as "do not trust this override set for stripping":
    Sonarr/Radarr being unreachable must never make the sweep strip MORE than
    configured, and a missing override silently falling back to the (usually
    less restrictive) default policy would risk exactly that. Each failing id
    is logged by name; one failure never aborts resolution of the others.
    """
    from config_utils import map_path
    from db.models.core import MovieSettings, SeriesSettings
    from extensions import db

    result: list[tuple[str, TrackPolicy]] = []
    complete = True
    for row in db.session.query(SeriesSettings).all():
        if not _has_override(row):
            continue
        try:
            from sonarr_client import get_sonarr_client

            client = get_sonarr_client()
            if not client:
                raise RuntimeError("Sonarr is not configured")
            series = client.get_series_by_id(row.sonarr_series_id) or {}
            path = series.get("path")
            if not path:
                raise RuntimeError("Sonarr returned no path")
            result.append((map_path(path), resolve_policy(series_id=row.sonarr_series_id)))
        except Exception:  # noqa: BLE001 — one failing series must not abort the others
            complete = False
            logger.warning(
                "track policy: override path unavailable for series %s — sweep will not "
                "strip more than configured until this resolves",
                row.sonarr_series_id,
                exc_info=True,
            )
    for row in db.session.query(MovieSettings).all():
        if not _has_override(row):
            continue
        try:
            from radarr_client import get_radarr_client

            client = get_radarr_client()
            if not client:
                raise RuntimeError("Radarr is not configured")
            movie = client.get_movie_by_id(row.radarr_movie_id) or {}
            path = movie.get("path")
            if not path:
                raise RuntimeError("Radarr returned no path")
            result.append((map_path(path), resolve_policy(movie_id=row.radarr_movie_id)))
        except Exception:  # noqa: BLE001 — one failing movie must not abort the others
            complete = False
            logger.warning(
                "track policy: override path unavailable for movie %s — sweep will not "
                "strip more than configured until this resolves",
                row.radarr_movie_id,
                exc_info=True,
            )
    return result, complete


def policy_for_path(
    path: str, overrides: list[tuple[str, TrackPolicy]], default: TrackPolicy
) -> TrackPolicy:
    """Longest matching folder prefix wins; a sibling folder that merely
    shares a text prefix (e.g. "Anime Two" vs "Anime") never matches."""
    norm = os.path.normpath(path)
    best: tuple[int, TrackPolicy] | None = None
    for folder, policy in overrides:
        root = os.path.normpath(folder)
        if norm == root or norm.startswith(root + os.sep):
            if best is None or len(root) > best[0]:
                best = (len(root), policy)
    return best[1] if best else default
