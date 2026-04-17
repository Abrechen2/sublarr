"""Pool key management — POST/PATCH/DELETE/GET /api/v1/providers/<name>/keys."""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from extensions import db, limiter

logger = logging.getLogger(__name__)

bp = Blueprint("providers_keys", __name__, url_prefix="/api/v1/providers")


def _probe_user_agent() -> str:
    """Read backend/VERSION once per call; falls back to 'dev'."""
    try:
        here = Path(__file__).resolve().parent.parent  # backend/
        version = (here / "VERSION").read_text().strip()
        return f"Sublarr/{version}"
    except Exception:  # noqa: BLE001
        return "Sublarr/dev"


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "label": row["account_label"],
        "tier": row["tier"],
        "enabled": row["enabled"],
        "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
        "last_429_at": row["last_429_at"].isoformat() if row["last_429_at"] else None,
    }


def _invalidate_cache(provider: str) -> None:
    try:
        from services.key_selector import get_key_selector

        get_key_selector().invalidate(provider)
    except Exception as _exc:  # noqa: BLE001
        logger.debug("KeySelector.invalidate failed for %s: %s", provider, _exc)


@bp.route("/<name>/keys", methods=["GET"])
def list_keys(name: str):
    repo = ProviderAccountPoolRepository()
    return jsonify({"keys": [_serialize(r) for r in repo.get_all_for(name)]})


@bp.route("/<name>/keys", methods=["POST"])
def add_key(name: str):
    data = request.get_json(silent=True) or {}
    label = data.get("label")
    api_key = data.get("api_key")
    if not label or not api_key:
        return jsonify({"error": "label and api_key are required"}), 400
    repo = ProviderAccountPoolRepository()
    try:
        row_id = repo.add(
            provider=name,
            label=label,
            api_key=api_key,
            tier=data.get("tier", "free"),
            username=data.get("username"),
            password=data.get("password"),
            enabled=bool(data.get("enabled", True)),
        )
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "label already exists for this provider"}), 409
    _invalidate_cache(name)
    return jsonify(_serialize(repo.get(row_id))), 201


@bp.route("/<name>/keys/<int:row_id>", methods=["PATCH"])
def update_key(name: str, row_id: int):
    repo = ProviderAccountPoolRepository()
    data = request.get_json(silent=True) or {}
    allowed = {"api_key", "tier", "enabled", "username", "password"}
    fields = {k: v for k, v in data.items() if k in allowed}
    if "label" in data:
        fields["account_label"] = data["label"]
    try:
        updated = repo.update(row_id, **fields)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    if not updated:
        return jsonify({"error": "not found"}), 404
    _invalidate_cache(name)
    return jsonify(_serialize(repo.get(row_id))), 200


@bp.route("/<name>/keys/<int:row_id>", methods=["DELETE"])
def delete_key(name: str, row_id: int):
    repo = ProviderAccountPoolRepository()
    repo.delete(row_id)
    _invalidate_cache(name)
    return ("", 204)


@bp.route("/<name>/keys/test-connection", methods=["POST"])
@limiter.limit("20 per minute")
def test_connection(name: str):
    data = request.get_json(silent=True) or {}
    result = _probe_provider(
        name,
        api_key=data.get("api_key", ""),
        username=data.get("username"),
        password=data.get("password"),
    )
    return jsonify(result), (200 if result["ok"] else 400)


def _probe_provider(
    name: str,
    *,
    api_key: str,
    username: str | None = None,
    password: str | None = None,
) -> dict:
    """Provider-specific cheap probe. Returns {ok: bool, message: str}.

    Isolated so tests can patch. Kept small — extend per-provider as needed.
    """
    try:
        if name == "opensubtitles":
            r = requests.get(
                "https://api.opensubtitles.com/api/v1/infos/formats",
                headers={"Api-Key": api_key, "User-Agent": _probe_user_agent()},
                timeout=10,
            )
            return {"ok": r.status_code == 200, "message": f"HTTP {r.status_code}"}
        if name == "subdl":
            # API key in header, not query params, to avoid leaking it via
            # exception messages that include the URL on network failures.
            r = requests.get(
                "https://api.subdl.com/api/v1/subtitles",
                params={"type": "movie", "tmdb_id": 1},
                headers={"Api-Key": api_key, "User-Agent": _probe_user_agent()},
                timeout=10,
            )
            return {"ok": r.status_code != 401, "message": f"HTTP {r.status_code}"}
        return {
            "ok": True,
            "skipped": True,
            "message": "No probe configured — saved as-is",
        }
    except requests.exceptions.RequestException as exc:
        # Surface only the exception class name; message strings may embed
        # credentials from the URL.
        return {"ok": False, "message": f"Probe failed: {type(exc).__name__}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"Probe failed: {type(exc).__name__}"}
