"""Settings and override plumbing for the track variant policy (1.15.0)."""

import pytest
from sqlalchemy import inspect


def test_defaults_reproduce_the_old_behaviour():
    from config_settings import UISettings

    ui = UISettings()
    assert ui.cleanup_track_variant_mode == "all"
    assert ui.cleanup_keep_forced is True
    assert ui.cleanup_keep_sdh is False
    assert ui.cleanup_sidecar_policy == "keep_embedded"


def test_columns_exist_on_an_untracked_database(temp_db):
    from app import create_app
    from extensions import db

    app = create_app(testing=True)
    with app.app_context():
        insp = inspect(db.engine)
        for table in ("series_settings", "movie_settings"):
            cols = {c["name"] for c in insp.get_columns(table)}
            assert {
                "cleanup_track_variant_mode",
                "cleanup_keep_forced",
                "cleanup_keep_sdh",
                "cleanup_sidecar_policy",
            } <= cols
        assert "track_verdicts" in {c["name"] for c in insp.get_columns("foreign_track_scan")}
        assert "sidecar_origins" in insp.get_table_names()


def test_series_override_wins_over_global(app_ctx):
    from datetime import UTC, datetime

    from config import get_settings
    from db.models.core import SeriesSettings
    from extensions import db
    from services.inheritance_resolver import resolve_for_series

    row = SeriesSettings(
        sonarr_series_id=7,
        cleanup_track_variant_mode="one_per_language",
        updated_at=datetime.now(UTC),
    )
    db.session.add(row)
    db.session.commit()

    resolved = resolve_for_series(series=row, profile=None, global_cfg=get_settings())
    assert resolved["cleanup_track_variant_mode"]["effective"] == "one_per_language"
    assert resolved["cleanup_sidecar_policy"]["effective"] == "keep_embedded"


@pytest.mark.parametrize(
    "payload",
    [
        {"cleanup_track_variant_mode": "one"},
        {"cleanup_sidecar_policy": "always"},
        {"cleanup_keep_forced": 1},
    ],
)
def test_override_values_are_validated(client, payload):
    resp = client.patch("/api/v1/profiles-overrides/series/7", json=payload)
    assert resp.status_code == 422
