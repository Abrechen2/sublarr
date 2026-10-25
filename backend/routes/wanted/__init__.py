"""Wanted routes package — list, search, export, extract, batch-extract, batch-probe, providers."""

from flask import Blueprint

bp = Blueprint("wanted", __name__, url_prefix="/api/v1")


def _series_wanted(series_id: int) -> list:
    """Wanted items of a series id: negative = standalone series, positive =
    Sonarr's, or a legacy standalone id without Sonarr (the rule the series
    detail uses, see services.media_ids)."""
    from db.wanted import get_wanted_for_series
    from services.media_ids import resolve_series_ref

    try:
        ref = resolve_series_ref(int(series_id))
    except (TypeError, ValueError):
        return []
    return get_wanted_for_series(ref.id, standalone=ref.is_standalone)


import routes.wanted.automation  # noqa: E402, F401
import routes.wanted.batch_extract  # noqa: E402, F401
import routes.wanted.batch_probe  # noqa: E402, F401
import routes.wanted.bulk_actions  # noqa: E402, F401
import routes.wanted.dry_run  # noqa: E402, F401
import routes.wanted.export  # noqa: E402, F401
import routes.wanted.extract  # noqa: E402, F401
import routes.wanted.list  # noqa: E402, F401
import routes.wanted.mt_pending  # noqa: E402, F401
import routes.wanted.providers  # noqa: E402, F401
import routes.wanted.search  # noqa: E402, F401

# Re-export for wanted_scanner.py: "from routes.wanted import _extract_embedded_sub"
from routes.wanted.extract import _extract_embedded_sub  # noqa: E402, F401
