"""REST API for the Profiles & Overrides Settings page (Template C)."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from auth import require_api_key
from config import get_settings
from db.models.core import (
    LanguageProfile,
    MovieLanguageProfile,
    MovieSettings,
    SeriesLanguageProfile,
    SeriesSettings,
)
from extensions import db
from schemas.profiles_overrides import OverridePatch
from services.arr_title_cache import (
    get_radarr_movie_titles,
    get_sonarr_series_titles,
)
from services.inheritance_resolver import (
    INHERITABLE_FIELDS,
    _decode,
    resolve_for_movie,
    resolve_for_series,
)

bp = Blueprint("profiles_overrides", __name__, url_prefix="/api/v1/profiles-overrides")


# ─── /scopes ─────────────────────────────────────────────────────────────────


@bp.route("/scopes", methods=["GET"])
@require_api_key
def get_scopes():
    """Return the full scope tree: every profile with its assigned series
    and movies, plus the 'unassigned' bucket for items with no profile."""
    profiles = LanguageProfile.query.order_by(
        LanguageProfile.is_default.desc(), LanguageProfile.name
    ).all()

    # Build profile_id → list of series/movies via the mapping tables.
    series_map = SeriesLanguageProfile.query.all()
    movie_map = MovieLanguageProfile.query.all()
    series_by_profile: dict[int, list[int]] = {}
    movie_by_profile: dict[int, list[int]] = {}
    assigned_series_ids: set[int] = set()
    assigned_movie_ids: set[int] = set()
    for m in series_map:
        series_by_profile.setdefault(m.profile_id, []).append(m.sonarr_series_id)
        assigned_series_ids.add(m.sonarr_series_id)
    for m in movie_map:
        movie_by_profile.setdefault(m.profile_id, []).append(m.radarr_movie_id)
        assigned_movie_ids.add(m.radarr_movie_id)

    # Sublarr does not maintain a master `series` / `movies` table — Sonarr
    # and Radarr own that. We aggregate every series/movie that has *any*
    # touchpoint in Sublarr's own DB: cached searches, wanted items,
    # per-series/movie settings, profile mappings, or standalone library
    # entries. For titles we prefer search_series.title / standalone_*.title
    # when present, otherwise we fall back to a `#<id>` placeholder.
    from sqlalchemy import text

    def _safe_query(sql: str) -> list:
        try:
            return list(db.session.execute(text(sql)).all())
        except Exception:
            return []

    # Collect IDs that are eligible to appear in the scope tree:
    # ONLY series/movies that have an explicit settings row OR a profile mapping.
    # search_series / wanted_items / standalone_* are NOT ID sources for the tree
    # (they would make the list too noisy). They are still used for title lookup.
    settings_series_ids: set[int] = {int(ss.sonarr_series_id) for ss in SeriesSettings.query.all()}
    settings_movie_ids: set[int] = {int(ms.radarr_movie_id) for ms in MovieSettings.query.all()}
    eligible_series_ids: set[int] = assigned_series_ids | settings_series_ids
    eligible_movie_ids: set[int] = assigned_movie_ids | settings_movie_ids

    # Title lookup map: prefer search_series / standalone_* for pretty names,
    # but scope membership is governed by eligible_*_ids above.
    series_id_titles: dict[int, str] = {}
    # search_series: id is the sonarr_series_id, populated whenever a search
    # for an episode of that series ran. Title is the cached display name.
    for row in _safe_query("SELECT id, title FROM search_series"):
        sid, title = int(row[0]), str(row[1] or "")
        # Strip episode-tail like " — S01E01 [DE]" if present.
        clean = title.split(" — ")[0] if " — " in title else title
        series_id_titles[sid] = clean or f"#{sid}"
    # standalone_series: manual library entries with their own id + title.
    for row in _safe_query("SELECT id, title FROM standalone_series"):
        sid, title = int(row[0]), str(row[1] or "")
        series_id_titles.setdefault(sid, title or f"#{sid}")
    # Sonarr/Radarr fallback for IDs that have no title in our caches yet
    # (e.g. items added to the override tree purely via the SeriesDetail
    # button before any search ever ran). Only invoked when there are gaps.
    missing_series_ids = {sid for sid in eligible_series_ids if sid not in series_id_titles}
    if missing_series_ids:
        sonarr_titles = get_sonarr_series_titles()
        for sid in missing_series_ids:
            if sid in sonarr_titles:
                series_id_titles[sid] = sonarr_titles[sid]
    # Ensure every eligible series has at least a placeholder title.
    for sid in eligible_series_ids:
        series_id_titles.setdefault(sid, f"#{sid}")
    # Restrict to only eligible IDs — drop any title-only entries.
    series_titles = {
        sid: series_id_titles[sid] for sid in eligible_series_ids if sid in series_id_titles
    }

    movie_id_titles: dict[int, str] = {}
    for row in _safe_query("SELECT id, title FROM standalone_movies"):
        mid, title = int(row[0]), str(row[1] or "")
        movie_id_titles[mid] = title or f"#{mid}"
    missing_movie_ids = {mid for mid in eligible_movie_ids if mid not in movie_id_titles}
    if missing_movie_ids:
        radarr_titles = get_radarr_movie_titles()
        for mid in missing_movie_ids:
            if mid in radarr_titles:
                movie_id_titles[mid] = radarr_titles[mid]
    for mid in eligible_movie_ids:
        movie_id_titles.setdefault(mid, f"#{mid}")
    movie_titles = {
        mid: movie_id_titles[mid] for mid in eligible_movie_ids if mid in movie_id_titles
    }

    def _entries(ids: list[int], titles: dict[int, str]) -> list[dict]:
        return [{"id": i, "title": titles.get(i, f"#{i}")} for i in ids]

    profile_nodes = []
    for p in profiles:
        profile_nodes.append(
            {
                "id": p.id,
                "name": p.name,
                "is_default": bool(p.is_default),
                "series": _entries(series_by_profile.get(p.id, []), series_titles),
                "movies": _entries(movie_by_profile.get(p.id, []), movie_titles),
            }
        )

    unassigned_series = _entries(
        [sid for sid in eligible_series_ids if sid not in assigned_series_ids],
        series_titles,
    )
    unassigned_movies = _entries(
        [mid for mid in eligible_movie_ids if mid not in assigned_movie_ids],
        movie_titles,
    )

    return jsonify(
        {
            "profiles": profile_nodes,
            "unassigned_series": unassigned_series,
            "unassigned_movies": unassigned_movies,
        }
    )


# ─── /resolved ───────────────────────────────────────────────────────────────


def _resolved_response(scope_type: str, scope_id, scope_name: str, settings: dict) -> dict:
    return {
        "scope": {"type": scope_type, "id": scope_id, "name": scope_name},
        "settings": settings,
    }


@bp.route("/resolved/global", methods=["GET"])
@require_api_key
def get_resolved_global():
    cfg = get_settings()
    out: dict[str, dict] = {}
    for field in INHERITABLE_FIELDS:
        if field.global_key is None:
            chain: list[dict] = []
            effective = None
            source = "global"
        else:
            raw = getattr(cfg, field.global_key, None)
            decoded = _decode(raw, field.value_kind)
            chain = [{"scope": "global", "value": decoded, "label": "Global default"}]
            effective = decoded
            source = "global"
        out[field.display_name] = {
            "effective": effective,
            "source": source,
            "chain": chain,
        }
    return jsonify(_resolved_response("global", None, "Global default", out))


@bp.route("/resolved/profile/<int:profile_id>", methods=["GET"])
@require_api_key
def get_resolved_profile(profile_id: int):
    profile = LanguageProfile.query.get(profile_id)
    if profile is None:
        return jsonify({"error": "profile not found"}), 404
    cfg = get_settings()
    out: dict[str, dict] = {}
    for field in INHERITABLE_FIELDS:
        chain: list[dict] = []
        if field.global_key is not None:
            raw_global = getattr(cfg, field.global_key, None)
            chain.append(
                {
                    "scope": "global",
                    "value": _decode(raw_global, field.value_kind),
                    "label": "Global default",
                }
            )
        if field.profile_attr is not None:
            raw_profile = getattr(profile, field.profile_attr, None)
            chain.append(
                {
                    "scope": "profile",
                    "value": _decode(raw_profile, field.value_kind),
                    "label": profile.name,
                }
            )
        effective = None
        source = "global"
        for step in reversed(chain):
            if step["value"] is not None:
                effective = step["value"]
                source = step["scope"]
                break
        if effective is None and chain:
            effective = chain[0]["value"]
            source = chain[0]["scope"]
        out[field.display_name] = {"effective": effective, "source": source, "chain": chain}
    return jsonify(_resolved_response("profile", profile_id, profile.name, out))


def _series_known_to_sublarr(series_id: int) -> bool:
    """Series is 'known' if any of: profile mapping, settings row, search-cache
    row, wanted-item row, or standalone-library row exists for it."""
    from sqlalchemy import text

    if SeriesLanguageProfile.query.filter_by(sonarr_series_id=series_id).first():
        return True
    if SeriesSettings.query.get(series_id) is not None:
        return True
    for sql in (
        "SELECT 1 FROM search_series WHERE id = :id LIMIT 1",
        "SELECT 1 FROM wanted_items WHERE sonarr_series_id = :id LIMIT 1",
        "SELECT 1 FROM standalone_series WHERE id = :id LIMIT 1",
    ):
        try:
            if db.session.execute(text(sql), {"id": series_id}).fetchone():
                return True
        except Exception:
            continue
    return False


def _series_title(series_id: int) -> str:
    """Best-effort title lookup across the same sources /scopes uses,
    plus a Sonarr API fallback for items that exist only in series_settings."""
    from sqlalchemy import text

    for sql in (
        "SELECT title FROM search_series WHERE id = :id LIMIT 1",
        "SELECT title FROM standalone_series WHERE id = :id LIMIT 1",
    ):
        try:
            row = db.session.execute(text(sql), {"id": series_id}).fetchone()
            if row and row[0]:
                title = str(row[0])
                return title.split(" — ")[0] if " — " in title else title
        except Exception:
            continue
    # Sonarr fallback (cached, swallows errors).
    sonarr_title = get_sonarr_series_titles().get(series_id)
    if sonarr_title:
        return sonarr_title
    return f"#{series_id}"


@bp.route("/resolved/series/<int:series_id>", methods=["GET"])
@require_api_key
def get_resolved_series(series_id: int):
    if not _series_known_to_sublarr(series_id):
        return jsonify({"error": "series not found"}), 404

    title = _series_title(series_id)
    mapping = SeriesLanguageProfile.query.filter_by(sonarr_series_id=series_id).first()
    series = SeriesSettings.query.get(series_id)
    profile = LanguageProfile.query.get(mapping.profile_id) if mapping else None
    cfg = get_settings()
    settings = resolve_for_series(series=series, profile=profile, global_cfg=cfg)
    return jsonify(_resolved_response("series", series_id, title, settings))


def _movie_known_to_sublarr(movie_id: int) -> bool:
    from sqlalchemy import text

    if MovieLanguageProfile.query.filter_by(radarr_movie_id=movie_id).first():
        return True
    if MovieSettings.query.get(movie_id) is not None:
        return True
    for sql in (
        "SELECT 1 FROM wanted_items WHERE radarr_movie_id = :id LIMIT 1",
        "SELECT 1 FROM standalone_movies WHERE id = :id LIMIT 1",
    ):
        try:
            if db.session.execute(text(sql), {"id": movie_id}).fetchone():
                return True
        except Exception:
            continue
    return False


def _movie_title(movie_id: int) -> str:
    from sqlalchemy import text

    try:
        row = db.session.execute(
            text("SELECT title FROM standalone_movies WHERE id = :id LIMIT 1"),
            {"id": movie_id},
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:
        pass
    radarr_title = get_radarr_movie_titles().get(movie_id)
    if radarr_title:
        return radarr_title
    return f"#{movie_id}"


@bp.route("/resolved/movie/<int:movie_id>", methods=["GET"])
@require_api_key
def get_resolved_movie(movie_id: int):
    if not _movie_known_to_sublarr(movie_id):
        return jsonify({"error": "movie not found"}), 404

    title = _movie_title(movie_id)
    mapping = MovieLanguageProfile.query.filter_by(radarr_movie_id=movie_id).first()
    movie = MovieSettings.query.get(movie_id)
    profile = LanguageProfile.query.get(mapping.profile_id) if mapping else None
    cfg = get_settings()
    settings = resolve_for_movie(movie=movie, profile=profile, global_cfg=cfg)
    return jsonify(_resolved_response("movie", movie_id, title, settings))


# ─── PATCH /series/<id> ─────────────────────────────────────────────────────
_SERIES_ONLY_FIELDS = {
    "cleanup_foreign_tracks",
    "preferred_audio_track_index",
    "priority_override",
    "min_attempts_per_day",
}


def _column_name_for_field(display_name: str) -> str:
    """Map display_name to the actual override column name."""
    for field in INHERITABLE_FIELDS:
        if field.display_name == display_name:
            return field.override_col
    raise KeyError(display_name)


def _serialize_for_storage(field: str, value) -> object:
    """JSON-encode list values, return scalars as-is."""
    if value is None:
        return None
    if isinstance(value, list):
        import json

        return json.dumps(value)
    return value


@bp.route("/series/<int:series_id>", methods=["PATCH"])
@require_api_key
def patch_series(series_id: int):
    try:
        patch = OverridePatch.model_validate(request.get_json() or {})
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 422

    ss = SeriesSettings.query.get(series_id)
    if ss is None:
        ss = SeriesSettings(
            sonarr_series_id=series_id,
            updated_at=datetime.now(UTC),
        )
        db.session.add(ss)

    for field_name, value in patch.changes.items():
        col = _column_name_for_field(field_name)
        setattr(ss, col, _serialize_for_storage(field_name, value))
    ss.updated_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/movie/<int:movie_id>", methods=["PATCH"])
@require_api_key
def patch_movie(movie_id: int):
    try:
        patch = OverridePatch.model_validate(request.get_json() or {})
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 422

    ms = MovieSettings.query.get(movie_id)
    if ms is None:
        ms = MovieSettings(
            radarr_movie_id=movie_id,
            updated_at=datetime.now(UTC),
        )
        db.session.add(ms)

    for field_name, value in patch.changes.items():
        col = _column_name_for_field(field_name)
        setattr(ms, col, _serialize_for_storage(field_name, value))
    ms.updated_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/series/<int:series_id>/reset", methods=["POST"])
@require_api_key
def reset_series(series_id: int):
    ss = SeriesSettings.query.get(series_id)
    if ss is None:
        return jsonify({"ok": True})  # nothing to reset
    for field in INHERITABLE_FIELDS:
        if hasattr(ss, field.override_col) and field.display_name not in {"min_attempts_per_day"}:
            setattr(ss, field.override_col, None)
    ss.updated_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/movie/<int:movie_id>/reset", methods=["POST"])
@require_api_key
def reset_movie(movie_id: int):
    ms = MovieSettings.query.get(movie_id)
    if ms is None:
        return jsonify({"ok": True})
    for field in INHERITABLE_FIELDS:
        if hasattr(ms, field.override_col) and field.display_name not in {"min_attempts_per_day"}:
            setattr(ms, field.override_col, None)
    ms.updated_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"ok": True})


# ─── CREATE / DELETE override rows ───────────────────────────────────────────


@bp.route("/series/<int:series_id>/create-override", methods=["POST"])
@require_api_key
def create_override_series(series_id: int):
    """Idempotent INSERT of an empty series_settings row.

    Returns 201 if a new row was created, 200 if one already existed.
    """
    existed = SeriesSettings.query.get(series_id) is not None
    if not existed:
        ss = SeriesSettings(
            sonarr_series_id=series_id,
            updated_at=datetime.now(UTC),
        )
        db.session.add(ss)
        db.session.commit()
    return jsonify({"created": not existed}), 201 if not existed else 200


@bp.route("/series/<int:series_id>", methods=["DELETE"])
@require_api_key
def delete_series_settings(series_id: int):
    """Drop the series_settings row for *series_id* (idempotent)."""
    ss = SeriesSettings.query.get(series_id)
    if ss is not None:
        db.session.delete(ss)
        db.session.commit()
    return jsonify({"deleted": ss is not None})


@bp.route("/movie/<int:movie_id>/create-override", methods=["POST"])
@require_api_key
def create_override_movie(movie_id: int):
    """Idempotent INSERT of an empty movie_settings row.

    Returns 201 if a new row was created, 200 if one already existed.
    """
    existed = MovieSettings.query.get(movie_id) is not None
    if not existed:
        ms = MovieSettings(
            radarr_movie_id=movie_id,
            updated_at=datetime.now(UTC),
        )
        db.session.add(ms)
        db.session.commit()
    return jsonify({"created": not existed}), 201 if not existed else 200


@bp.route("/movie/<int:movie_id>", methods=["DELETE"])
@require_api_key
def delete_movie_settings(movie_id: int):
    """Drop the movie_settings row for *movie_id* (idempotent)."""
    ms = MovieSettings.query.get(movie_id)
    if ms is not None:
        db.session.delete(ms)
        db.session.commit()
    return jsonify({"deleted": ms is not None})
