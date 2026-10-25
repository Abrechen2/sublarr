"""Pre-1.18 standalone rows are read where they are, never moved.

Before 1.18.0 a standalone title's profile, settings, glossary and fansub
rows were written under its positive row id when no Sonarr/Radarr was
configured. Since 1.18.0 they are written under the owner key (the negated
id). Nothing moves them: readers fall back to the positive key read-only
while the matching arr is not configured and nothing shows it ever was, and
the first write copies them to the owner key (docs/specs/standalone-ids.md).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

_NOW = datetime(2026, 10, 1, tzinfo=UTC)

_OWNER_TABLES = (
    "series_language_profiles",
    "movie_language_profiles",
    "series_settings",
    "movie_settings",
    "fansub_preferences",
    "glossary_entries",
    "subtitle_health_findings",
)


class _Arr:
    def get_series_by_id(self, *_a, **_kw):
        return None


@pytest.fixture
def no_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)


@pytest.fixture
def with_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: _Arr())
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: _Arr())


def _sql(sql: str, **params) -> None:
    from extensions import db

    db.session.execute(sa.text(sql), {"t": _NOW, **params})
    db.session.commit()


def _profiles() -> None:
    from db.models.core import LanguageProfile
    from extensions import db

    for pid, name in ((1, "Default"), (2, "French")):
        row = db.session.get(LanguageProfile, pid)
        if row is None:
            db.session.add(
                LanguageProfile(
                    id=pid, name=name, is_default=int(pid == 1), created_at=_NOW, updated_at=_NOW
                )
            )
        else:
            row.is_default = int(pid == 1)
    db.session.commit()


def _seed_legacy(series_id: int = 3, movie_id: int = 4) -> None:
    """A 1.17 standalone install: rows under the positive standalone ids."""
    _profiles()
    _sql(
        "INSERT INTO standalone_series (id, title, folder_path, created_at, updated_at) "
        "VALUES (:s, 'Show', '/m/Show', :t, :t)",
        s=series_id,
    )
    _sql(
        "INSERT INTO standalone_movies (id, title, file_path, created_at, updated_at) "
        "VALUES (:m, 'Film', '/m/Film.mkv', :t, :t)",
        m=movie_id,
    )
    _sql(
        "INSERT INTO series_language_profiles (sonarr_series_id, profile_id) VALUES (:s, 2)",
        s=series_id,
    )
    _sql(
        "INSERT INTO movie_language_profiles (radarr_movie_id, profile_id) VALUES (:m, 2)",
        m=movie_id,
    )
    _sql(
        "INSERT INTO series_settings (sonarr_series_id, absolute_order, min_attempts_per_day, "
        "cleanup_foreign_tracks, preferred_audio_track_index, subtitle_format_requirement, "
        "updated_at) VALUES (:s, 1, 0, 0, 2, 'require_ass', :t)",
        s=series_id,
    )
    _sql(
        "INSERT INTO movie_settings (radarr_movie_id, min_attempts_per_day, "
        "cleanup_foreign_tracks, updated_at) VALUES (:m, 0, 0, :t)",
        m=movie_id,
    )
    _sql(
        "INSERT INTO fansub_preferences (sonarr_series_id, preferred_groups_json, "
        "excluded_groups_json, bonus, updated_at) VALUES (:s, '[\"SubsPlease\"]', '[]', 30, :t)",
        s=series_id,
    )
    for src, dst in (("Titan", "Titan"), ("Wall", "Mauer")):
        _sql(
            "INSERT INTO glossary_entries (series_id, source_term, target_term, notes, "
            "term_type, approved, created_at, updated_at) "
            "VALUES (:s, :a, :b, '', 'other', 1, :t, :t)",
            s=series_id,
            a=src,
            b=dst,
        )


def _digest(rows) -> str:
    return hashlib.sha256(repr(sorted(map(repr, rows))).encode()).hexdigest()


def _owner_snapshot() -> dict[str, str]:
    from extensions import db

    return {
        table: _digest(db.session.execute(sa.text(f"SELECT * FROM {table}")).fetchall())  # noqa: S608
        for table in _OWNER_TABLES
    }


def _legacy_rows_intact(series_id: int = 3) -> None:
    from extensions import db

    q = db.session.execute
    assert (
        q(
            sa.text("SELECT profile_id FROM series_language_profiles WHERE sonarr_series_id=:s"),
            {"s": series_id},
        ).scalar()
        == 2
    )
    assert q(
        sa.text(
            "SELECT cleanup_foreign_tracks, preferred_audio_track_index FROM series_settings "
            "WHERE sonarr_series_id=:s"
        ),
        {"s": series_id},
    ).one() == (0, 2)
    assert sorted(
        r[0]
        for r in q(
            sa.text("SELECT source_term FROM glossary_entries WHERE series_id=:s"),
            {"s": series_id},
        )
    ) == ["Titan", "Wall"]


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def test_standalone_only_install_reads_its_legacy_rows(app_ctx, no_arr):
    from db.models.core import SeriesSettings
    from db.profiles import get_profile_for_item
    from db.repositories.anidb import AnidbRepository
    from db.repositories.fansub_prefs import FansubPreferenceRepository
    from db.repositories.series_audio import SeriesAudioRepository
    from db.translation import get_glossary_entries
    from services.foreign_track_cleanup import _get_title_override
    from services.series_format import get_series_format_requirement
    from services.standalone_owner_keys import get_row

    _seed_legacy()
    assert get_profile_for_item({"standalone_series_id": 3})["id"] == 2
    assert get_profile_for_item({"standalone_movie_id": 4})["id"] == 2
    assert get_row(SeriesSettings, -3).cleanup_foreign_tracks is False
    assert SeriesAudioRepository().get_audio_track_pref(-3) == 2
    assert AnidbRepository().get_absolute_order(-3) is True
    assert get_series_format_requirement(-3) == "require_ass"
    assert FansubPreferenceRepository().get_fansub_prefs(-3)["preferred_groups"] == ["SubsPlease"]
    assert sorted(e["source_term"] for e in get_glossary_entries(-3)) == ["Titan", "Wall"]
    assert _get_title_override({"standalone_series_id": 3}) is False
    assert _get_title_override({"standalone_movie_id": 4}) is False


def test_configured_arr_owns_the_positive_keys(app_ctx, with_arr):
    from db.profiles import get_profile_for_item
    from db.repositories.fansub_prefs import FansubPreferenceRepository
    from db.translation import get_glossary_entries
    from services.series_format import get_series_format_requirement

    _seed_legacy()
    assert get_profile_for_item({"standalone_series_id": 3})["id"] == 1
    assert get_profile_for_item({"standalone_movie_id": 4})["id"] == 1
    assert get_series_format_requirement(-3) is None
    assert FansubPreferenceRepository().get_fansub_prefs(-3) is None
    assert get_glossary_entries(-3) == []
    # Sonarr/Radarr-mode positive ids are unchanged.
    assert get_profile_for_item({"sonarr_series_id": 3})["id"] == 2
    assert get_profile_for_item({"radarr_movie_id": 4})["id"] == 2
    assert get_series_format_requirement(3) == "require_ass"


def test_stored_arr_url_is_evidence_against_the_fallback(app_ctx, no_arr):
    from db.profiles import get_profile_for_item

    _seed_legacy()
    _sql(
        "INSERT INTO config_entries (key, value, updated_at) VALUES ('sonarr_url', 'http://s', :t)"
    )
    assert get_profile_for_item({"standalone_series_id": 3})["id"] == 1
    # The Radarr side has no evidence: still read.
    assert get_profile_for_item({"standalone_movie_id": 4})["id"] == 2


def test_wanted_row_with_a_radarr_id_is_evidence(app_ctx, no_arr):
    from db.profiles import get_profile_for_item

    _seed_legacy()
    _sql(
        "INSERT INTO wanted_items (item_type, file_path, title, radarr_movie_id, status, "
        "priority, error_count, added_at, updated_at) VALUES ('movie', '/x.mkv', 'x', 9, "
        "'wanted', 'standard', 0, :t, :t)"
    )
    assert get_profile_for_item({"standalone_movie_id": 4})["id"] == 1
    assert get_profile_for_item({"standalone_series_id": 3})["id"] == 2


def test_own_row_wins_over_the_legacy_row(app_ctx, no_arr):
    from db.profiles import assign_series_profile, get_profile_for_item

    _seed_legacy()
    assign_series_profile(-3, 1)
    assert get_profile_for_item({"standalone_series_id": 3})["id"] == 1
    _legacy_rows_intact()


def test_unknown_standalone_id_reads_nothing(app_ctx, no_arr):
    from db.profiles import get_series_profile

    _seed_legacy()
    _sql("INSERT INTO series_language_profiles (sonarr_series_id, profile_id) VALUES (8, 2)")
    assert get_series_profile(-8)["id"] == 1


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def test_first_write_copies_legacy_rows_and_wins(app_ctx, no_arr):
    from db.models.core import SeriesSettings
    from db.repositories.fansub_prefs import FansubPreferenceRepository
    from db.repositories.series_audio import SeriesAudioRepository
    from db.translation import get_glossary_entries
    from extensions import db
    from services.series_format import get_series_format_requirement

    _seed_legacy()
    SeriesAudioRepository().set_audio_track_pref(-3, 5)

    row = db.session.get(SeriesSettings, -3)
    assert row is not None and row.preferred_audio_track_index == 5
    # The other settings came along instead of resetting to defaults.
    assert row.cleanup_foreign_tracks is False
    assert get_series_format_requirement(-3) == "require_ass"
    assert FansubPreferenceRepository().get_fansub_prefs(-3)["bonus"] == 30
    assert sorted(e["source_term"] for e in get_glossary_entries(-3)) == ["Titan", "Wall"]
    assert SeriesAudioRepository().get_audio_track_pref(-3) == 5
    _legacy_rows_intact()


def test_delete_after_claim_does_not_bring_the_legacy_row_back(client, no_arr):
    with client.application.app_context():
        _seed_legacy()
    assert client.delete("/api/v1/series/-3/fansub-prefs").status_code == 200
    assert client.get("/api/v1/series/-3/fansub-prefs").get_json()["bonus"] == 20
    assert client.delete("/api/v1/profiles-overrides/series/-3").status_code == 200
    with client.application.app_context():
        from db.repositories.fansub_prefs import FansubPreferenceRepository
        from db.translation import get_glossary_entries
        from services.foreign_track_cleanup import _get_title_override

        assert FansubPreferenceRepository().get_fansub_prefs(-3) is None
        assert _get_title_override({"standalone_series_id": 3}) is None
        # The glossary was copied along by the first write; still there.
        assert len(get_glossary_entries(-3)) == 2
        _legacy_rows_intact()


def test_glossary_edit_of_a_legacy_entry_edits_a_copy(app_ctx, no_arr):
    from db.translation import add_glossary_entry, get_glossary_entries, update_glossary_entry
    from extensions import db

    _seed_legacy()
    legacy = {e["source_term"]: e["id"] for e in get_glossary_entries(-3)}
    assert update_glossary_entry(legacy["Wall"], target_term="Wand") is True

    own = {e["source_term"]: e for e in get_glossary_entries(-3)}
    assert own["Wall"]["target_term"] == "Wand"
    assert own["Wall"]["series_id"] == -3
    assert own["Wall"]["id"] != legacy["Wall"]
    _legacy_rows_intact()

    add_glossary_entry(-3, "Eren", "Eren")
    assert sorted(e["source_term"] for e in get_glossary_entries(-3)) == ["Eren", "Titan", "Wall"]
    assert (
        db.session.execute(
            sa.text("SELECT COUNT(*) FROM glossary_entries WHERE series_id = 3")
        ).scalar()
        == 2
    )


def test_glossary_delete_of_a_legacy_entry_deletes_the_copy(app_ctx, no_arr):
    from db.translation import delete_glossary_entry, get_glossary_entries

    _seed_legacy()
    legacy = {e["source_term"]: e["id"] for e in get_glossary_entries(-3)}
    assert delete_glossary_entry(legacy["Titan"]) is True
    remaining = get_glossary_entries(-3)
    assert [e["source_term"] for e in remaining] == ["Wall"]
    assert delete_glossary_entry(remaining[0]["id"]) is True
    # Empty under the owner key now; the claim keeps the legacy set hidden.
    assert get_glossary_entries(-3) == []
    _legacy_rows_intact()


def test_glossary_add_keeps_the_legacy_terms(app_ctx, no_arr):
    from db.translation import add_glossary_entry, get_glossary_entries

    _seed_legacy()
    add_glossary_entry(-3, "Eren", "Eren")
    assert sorted(e["source_term"] for e in get_glossary_entries(-3)) == ["Eren", "Titan", "Wall"]
    _legacy_rows_intact()


def test_profile_assignment_route_after_fallback(client, no_arr):
    with client.application.app_context():
        _seed_legacy()
    resp = client.put(
        "/api/v1/language-profiles/assign", json={"type": "series", "arr_id": -3, "profile_id": 1}
    )
    assert resp.status_code == 200, resp.get_json()
    with client.application.app_context():
        from db.profiles import get_profile_for_item

        assert get_profile_for_item({"standalone_series_id": 3})["id"] == 1
        _legacy_rows_intact()


def test_override_patch_after_fallback_keeps_the_other_settings(client, no_arr):
    with client.application.app_context():
        _seed_legacy()
    resp = client.patch("/api/v1/profiles-overrides/series/-3", json={"cutoff_language": "de"})
    assert resp.status_code == 200, resp.get_json()
    with client.application.app_context():
        from db.models.core import SeriesSettings
        from extensions import db

        row = db.session.get(SeriesSettings, -3)
        assert row.cutoff_language_override == "de"
        assert row.preferred_audio_track_index == 2
        _legacy_rows_intact()


def test_sonarr_mode_writes_stay_on_positive_ids(app_ctx, with_arr):
    from db.models.core import SeriesSettings
    from db.repositories.series_audio import SeriesAudioRepository
    from extensions import db

    _seed_legacy()
    SeriesAudioRepository().set_audio_track_pref(3, 7)
    assert db.session.get(SeriesSettings, 3).preferred_audio_track_index == 7
    assert db.session.get(SeriesSettings, -3) is None
    assert (
        db.session.execute(sa.text("SELECT COUNT(*) FROM standalone_legacy_claims")).scalar() == 0
    )


def test_deleted_title_never_hands_its_rows_to_a_reused_id(app_ctx, no_arr):
    from db.profiles import get_series_profile
    from db.standalone import delete_standalone_series

    _seed_legacy()
    assert delete_standalone_series(3) is True
    _sql(
        "INSERT INTO standalone_series (id, title, folder_path, created_at, updated_at) "
        "VALUES (3, 'Other', '/m/Other', :t, :t)"
    )
    assert get_series_profile(-3)["id"] == 1


# ---------------------------------------------------------------------------
# Bulk readers
# ---------------------------------------------------------------------------


def test_library_profile_map_shows_legacy_assignment(app_ctx, no_arr):
    from db.profiles import get_series_profile_map

    _seed_legacy()
    assert get_series_profile_map()[-3]["profile_id"] == 2


def test_library_profile_map_with_arr_has_no_standalone_entry(app_ctx, with_arr):
    from db.profiles import get_series_profile_map

    _seed_legacy()
    profile_map = get_series_profile_map()
    assert -3 not in profile_map
    assert profile_map[3]["profile_id"] == 2


def test_track_policy_sweep_uses_legacy_row_once(app_ctx, no_arr):
    """The sweep's bulk read: a legacy switch-off protects the standalone
    folder until the title has its own row, then only the own row counts."""
    from services.foreign_tracks.policy import override_paths

    _seed_legacy()
    result = override_paths()
    assert result.excluded.count("/m/Show") == 1
    assert "/m/Film.mkv" in result.excluded
    assert result.complete

    _sql(
        "INSERT INTO series_settings (sonarr_series_id, absolute_order, min_attempts_per_day, "
        "cleanup_foreign_tracks, updated_at) VALUES (-3, 0, 0, 1, :t)"
    )
    result = override_paths()
    assert "/m/Show" not in result.excluded


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def _boot(db_path, monkeypatch) -> None:
    from config import reload_settings
    from db import close_db

    monkeypatch.setenv("SUBLARR_DB_PATH", str(db_path))
    monkeypatch.setenv("SUBLARR_LOG_LEVEL", "ERROR")
    reload_settings()
    try:
        from app import create_app

        create_app(testing=True)
    finally:
        close_db()


def _file_snapshot(db_path) -> dict[str, str]:
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        out = {
            table: _digest(conn.execute(sa.text(f"SELECT * FROM {table}")).fetchall())  # noqa: S608
            for table in _OWNER_TABLES
        }
    engine.dispose()
    return out


def _seed_file(db_path, statements) -> None:
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        # As if the database came from 1.17 and no 1.18 build ever started on
        # it (release candidates wrote this marker for their one-time move).
        conn.execute(
            sa.text(
                "DELETE FROM untracked_data_repairs WHERE revision = 'sa2_standalone_owner_keys'"
            )
        )
        for sql in statements:
            conn.execute(sa.text(sql), {"t": _NOW})
    engine.dispose()


_SEED_1032 = (
    "INSERT INTO standalone_series (id, title, folder_path, created_at, updated_at) "
    "VALUES (1032, 'Show', '/m/Show', :t, :t)",
    "INSERT INTO series_language_profiles (sonarr_series_id, profile_id) VALUES (1032, 2)",
    "INSERT INTO series_settings (sonarr_series_id, absolute_order, min_attempts_per_day, "
    "cleanup_foreign_tracks, updated_at) VALUES (1032, 1, 0, 0, :t)",
    # The Sonarr period left download history only (wanted rows drained).
    "INSERT INTO subtitle_downloads (provider_name, subtitle_id, language, file_path, "
    "downloaded_at) VALUES ('p', 's', 'de', '/tv/Sonarr Show/S01E01.de.srt', :t)",
    "INSERT INTO subtitle_health_findings (episode_id, target_kind, target_path, lang, "
    "issue_type, severity, count, snippets_json, raw_hash, status, scanner_version, "
    "detected_at) VALUES (11, 'sidecar', '/m/Show/S01E01.de.srt', 'de', 'mojibake', "
    "'warning', 1, '[]', 'h', 'open', 1, :t)",
)


def test_startup_changes_no_owner_rows(tmp_path, monkeypatch):
    """The 1032 repro (Sonarr removed, a standalone series with the same id):
    starting the app leaves every owner-keyed row and health finding alone."""
    db_path = tmp_path / "boot.db"
    _boot(db_path, monkeypatch)
    _seed_file(db_path, _SEED_1032)
    before = _file_snapshot(db_path)

    _boot(db_path, monkeypatch)
    _boot(db_path, monkeypatch)
    assert _file_snapshot(db_path) == before


def test_1032_repro_reads_the_legacy_row_only_without_evidence(app_ctx, no_arr):
    """Nothing is moved. Without durable Sonarr evidence the standalone title
    may read the row read-only (documented); a stored Sonarr URL stops it."""
    from db.profiles import get_series_profile
    from extensions import db
    from services.standalone_owner_keys import reset_cache

    _profiles()
    for sql in _SEED_1032:
        db.session.execute(sa.text(sql), {"t": _NOW})
    db.session.commit()
    before = _owner_snapshot()

    assert get_series_profile(-1032)["id"] == 2
    _sql(
        "INSERT INTO config_entries (key, value, updated_at) VALUES ('sonarr_url', 'http://s', :t)"
    )
    reset_cache()
    assert get_series_profile(-1032)["id"] == 1
    assert _owner_snapshot() == before


_SEED_PURE_STANDALONE = (
    "INSERT INTO standalone_series (id, title, folder_path, created_at, updated_at) "
    "VALUES (3, 'Show', '/m/Show', :t, :t)",
    "INSERT INTO series_language_profiles (sonarr_series_id, profile_id) VALUES (3, 1)",
    "INSERT INTO series_settings (sonarr_series_id, absolute_order, min_attempts_per_day, "
    "cleanup_foreign_tracks, updated_at) VALUES (3, 1, 0, 0, :t)",
    "INSERT INTO glossary_entries (series_id, source_term, target_term, notes, term_type, "
    "approved, created_at, updated_at) VALUES (3, 'Titan', 'Titan', '', 'other', 1, :t, :t)",
    "INSERT INTO wanted_items (id, item_type, file_path, title, standalone_series_id, status, "
    "priority, error_count, added_at, updated_at) VALUES (11, 'episode', '/m/Show/S01E01.mkv', "
    "'t', 3, 'wanted', 'standard', 0, :t, :t)",
    "INSERT INTO subtitle_health_findings (episode_id, target_kind, target_path, lang, "
    "issue_type, severity, count, snippets_json, raw_hash, status, scanner_version, "
    "detected_at) VALUES (11, 'sidecar', '/m/Show/S01E01.de.srt', 'de', 'mojibake', "
    "'warning', 1, '[]', 'h', 'open', 1, :t)",
)


def test_startup_leaves_pure_standalone_legacy_rows_alone(tmp_path, monkeypatch):
    """No arr evidence at all (what the removed one-time move acted on):
    starting the app still changes nothing; findings keep their wanted ids
    and are regenerated by the next health scan."""
    db_path = tmp_path / "pure.db"
    _boot(db_path, monkeypatch)
    _seed_file(db_path, _SEED_PURE_STANDALONE)
    before = _file_snapshot(db_path)

    _boot(db_path, monkeypatch)
    assert _file_snapshot(db_path) == before
