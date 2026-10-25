"""One id space for Sonarr, Radarr and standalone objects.

A negative id is a standalone id: ``-standalone_series.id`` for a series,
``-standalone_movies.id`` for a movie, ``-standalone_episodes.id`` for an
episode. Sonarr and Radarr ids are positive, so the sign is the source flag on
the wire and in Sublarr tables keyed by a Sonarr/Radarr id (profile
assignments, series/movie settings, glossary, fansub preferences). See
docs/specs/standalone-ids.md.

A positive id keeps its pre-1.18 meaning: the arr when its client is
configured, else a standalone row id (clients and bookmarks from 1.17.x).
"""

from __future__ import annotations

from dataclasses import dataclass

SONARR = "sonarr"
RADARR = "radarr"
STANDALONE = "standalone"


def standalone_key(row_id: int) -> int:
    """Wire id / owner key of the standalone row ``row_id``."""
    row_id = int(row_id)
    if row_id <= 0:
        raise ValueError(f"standalone row id must be positive, got {row_id}")
    return -row_id


def standalone_id_from(wire_id: int | None) -> int | None:
    """Standalone row id named by ``wire_id``, or None for a non-standalone id."""
    if wire_id is None:
        return None
    wire_id = int(wire_id)
    return -wire_id if wire_id < 0 else None


@dataclass(frozen=True)
class MediaRef:
    """What a series/movie id names: ``kind`` plus the id inside that source."""

    kind: str
    id: int

    @property
    def is_standalone(self) -> bool:
        return self.kind == STANDALONE

    @property
    def key(self) -> int:
        """Owner key in Sublarr tables (and wire id): negative for standalone."""
        return -self.id if self.is_standalone else self.id


def _sonarr_configured() -> bool:
    from sonarr_client import get_sonarr_client

    return get_sonarr_client() is not None


def _radarr_configured() -> bool:
    from radarr_client import get_radarr_client

    return get_radarr_client() is not None


def resolve_series_ref(series_id: int) -> MediaRef:
    """Negative -> standalone; positive -> Sonarr if configured, else legacy standalone."""
    series_id = int(series_id)
    if series_id < 0:
        return MediaRef(STANDALONE, -series_id)
    if _sonarr_configured():
        return MediaRef(SONARR, series_id)
    return MediaRef(STANDALONE, series_id)


def resolve_movie_ref(movie_id: int) -> MediaRef:
    """Negative -> standalone; positive -> Radarr if configured, else legacy standalone."""
    movie_id = int(movie_id)
    if movie_id < 0:
        return MediaRef(STANDALONE, -movie_id)
    if _radarr_configured():
        return MediaRef(RADARR, movie_id)
    return MediaRef(STANDALONE, movie_id)


def series_owner_key(series_id: int) -> int:
    """Key a series-keyed table row is stored under for this request id."""
    return resolve_series_ref(series_id).key


def movie_owner_key(movie_id: int) -> int:
    """Key a movie-keyed table row is stored under for this request id."""
    return resolve_movie_ref(movie_id).key


def series_key_for_item(item: dict | None) -> int | None:
    """Series owner key of a wanted item / arr_context dict, or None."""
    if not item:
        return None
    if item.get("sonarr_series_id"):
        return int(item["sonarr_series_id"])
    if item.get("standalone_series_id"):
        return standalone_key(item["standalone_series_id"])
    return None


def movie_key_for_item(item: dict | None) -> int | None:
    """Movie owner key of a wanted item / arr_context dict, or None."""
    if not item:
        return None
    if item.get("radarr_movie_id"):
        return int(item["radarr_movie_id"])
    if item.get("standalone_movie_id"):
        return standalone_key(item["standalone_movie_id"])
    return None
