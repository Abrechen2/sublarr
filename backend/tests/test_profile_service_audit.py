"""Regression tests for the 2026-04-30 Profiles + Glossary + Presets audit.

Pins:
- Cross-DB UNIQUE-conflict detection (string match used to only catch
  SQLite's "UNIQUE constraint failed", missing PostgreSQL's "duplicate
  key value violates unique constraint").
- Glossary TSV export must escape newlines/tabs and prevent CSV
  injection (cells beginning with =, +, -, @).
- assign_profile_to_item validates arr_id / profile_id types up front
  (previously a string arr_id sailed through the truthiness check and
  500'd from the DB driver).
- assign_profile_bulk caps arr_ids length.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from services.profile_service import (
    _MAX_BULK_ASSIGN,
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileValidationError,
    _tsv_safe,
    assign_profile_to_item,
    create_profile,
    export_glossary_as_tsv,
    update_profile,
)

# ---------------------------------------------------------------------------
# Cross-DB UNIQUE conflict detection
# ---------------------------------------------------------------------------


class TestCrossDBUniqueDetection:
    """Both SQLite-style and PostgreSQL-style UNIQUE errors must surface as 409."""

    @staticmethod
    def _valid_payload():
        return {
            "name": "TestProfile",
            "source_language": "en",
            "target_languages": ["de"],
            "translation_backend": "ollama",
        }

    def test_sqlite_unique_constraint_phrasing_caught(self):
        """SQLite raises 'UNIQUE constraint failed: language_profiles.name'."""
        with (
            patch(
                "db.profiles.create_language_profile",
                side_effect=Exception("UNIQUE constraint failed: language_profiles.name"),
            ),
            pytest.raises(ProfileConflictError, match="already exists"),
        ):
            create_profile(self._valid_payload())

    def test_postgres_duplicate_key_phrasing_caught(self):
        """PostgreSQL raises an IntegrityError with 'duplicate key value violates'."""
        # Build a real IntegrityError with the PG-style message.
        pg_error = IntegrityError(
            statement="INSERT INTO language_profiles ...",
            params={},
            orig=Exception(
                'duplicate key value violates unique constraint "language_profiles_name_key"'
            ),
        )
        with (
            patch("db.profiles.create_language_profile", side_effect=pg_error),
            pytest.raises(ProfileConflictError, match="already exists"),
        ):
            create_profile(self._valid_payload())

    def test_unrelated_integrity_error_still_raises_conflict(self):
        """Any IntegrityError from the create path is treated as a name
        conflict — that's the only UNIQUE constraint on the create path
        and it's a clearer 409 than a generic 500."""
        ie = IntegrityError(statement="...", params={}, orig=Exception("any IE"))
        with (
            patch("db.profiles.create_language_profile", side_effect=ie),
            pytest.raises(ProfileConflictError),
        ):
            create_profile(self._valid_payload())

    def test_non_unique_runtime_error_propagates(self):
        """Random RuntimeError must still bubble up so the route returns 500."""
        with (
            patch(
                "db.profiles.create_language_profile",
                side_effect=RuntimeError("disk full"),
            ),
            pytest.raises(RuntimeError),
        ):
            create_profile(self._valid_payload())

    def test_update_profile_pg_unique_caught(self):
        """update_profile must also handle PG-style IntegrityError."""
        pg_error = IntegrityError(
            statement="UPDATE language_profiles ...",
            params={},
            orig=Exception("duplicate key value violates unique constraint"),
        )
        with (
            patch("db.profiles.get_language_profile", return_value={"id": 1, "name": "x"}),
            patch("db.profiles.update_language_profile", side_effect=pg_error),
            pytest.raises(ProfileConflictError),
        ):
            update_profile(1, {"name": "duplicate"})


# ---------------------------------------------------------------------------
# Glossary TSV export hardening
# ---------------------------------------------------------------------------


class TestTsvSafeHelper:
    def test_none_becomes_empty_string(self):
        assert _tsv_safe(None) == ""

    def test_tab_replaced_with_space(self):
        assert _tsv_safe("foo\tbar") == "foo bar"

    def test_newline_replaced_with_space(self):
        """Newlines would split a single cell into two rows on import."""
        assert _tsv_safe("line1\nline2") == "line1 line2"

    def test_carriage_return_replaced_with_space(self):
        assert _tsv_safe("line1\rline2") == "line1 line2"

    def test_crlf_collapses_to_single_space_pair(self):
        assert _tsv_safe("line1\r\nline2") == "line1  line2"

    def test_csv_injection_equals_prefixed(self):
        """A leading = is interpreted as formula by Excel/Sheets."""
        assert _tsv_safe('=HYPERLINK("http://evil/")') == '\'=HYPERLINK("http://evil/")'

    def test_csv_injection_plus_prefixed(self):
        assert _tsv_safe("+cmd") == "'+cmd"

    def test_csv_injection_minus_prefixed(self):
        assert _tsv_safe("-cmd") == "'-cmd"

    def test_csv_injection_at_prefixed(self):
        assert _tsv_safe("@SUM(A1:A10)") == "'@SUM(A1:A10)"

    def test_normal_value_unchanged(self):
        assert _tsv_safe("Hello world") == "Hello world"

    def test_empty_string_left_alone(self):
        assert _tsv_safe("") == ""


class TestGlossaryTsvExport:
    """End-to-end: export_glossary_as_tsv produces well-formed, injection-safe TSV."""

    def test_tsv_export_handles_newline_in_notes(self):
        entries = [
            {
                "source_term": "demon",
                "target_term": "Dämon",
                "term_type": "creature",
                "notes": "fire-breathing\nmythical",
            }
        ]
        with patch("db.translation.get_glossary_entries", return_value=entries):
            content, filename = export_glossary_as_tsv(None)

        # Header + exactly one data row (no row-split from the embedded \n).
        lines = content.rstrip("\n").split("\n")
        assert len(lines) == 2  # header + 1 row
        # The note content survives on a single line, with the newline replaced.
        assert "fire-breathing mythical" in lines[1]

    def test_tsv_export_csv_injection_neutralised(self):
        entries = [
            {
                "source_term": '=HYPERLINK("http://evil/")',
                "target_term": "+cmd",
                "term_type": "@SUM(A1)",
                "notes": "-malicious",
            }
        ]
        with patch("db.translation.get_glossary_entries", return_value=entries):
            content, _ = export_glossary_as_tsv(None)

        # Each dangerous cell starts with the safety prefix.
        rows = content.split("\n")[1].split("\t")
        assert rows[0].startswith("'=")
        assert rows[1].startswith("'+")
        assert rows[2].startswith("'@")
        assert rows[3].startswith("'-")

    def test_tsv_export_filename_per_series_or_global(self):
        with patch("db.translation.get_glossary_entries", return_value=[]):
            _, fn_global = export_glossary_as_tsv(None)
            _, fn_series = export_glossary_as_tsv(42)
        assert fn_global == "glossary_global.tsv"
        assert fn_series == "glossary_series_42.tsv"


# ---------------------------------------------------------------------------
# assign_profile_to_item input validation
# ---------------------------------------------------------------------------


class TestAssignProfileInputValidation:
    """The route layer used to forward strings/None straight into the DB layer."""

    def test_string_arr_id_rejected(self):
        with pytest.raises(ProfileValidationError, match="arr_id"):
            assign_profile_to_item({"type": "series", "arr_id": "abc", "profile_id": 1})

    def test_string_profile_id_rejected(self):
        with pytest.raises(ProfileValidationError, match="profile_id"):
            assign_profile_to_item({"type": "series", "arr_id": 1, "profile_id": "abc"})

    def test_zero_arr_id_rejected(self):
        with pytest.raises(ProfileValidationError, match="arr_id"):
            assign_profile_to_item({"type": "series", "arr_id": 0, "profile_id": 1})

    def test_negative_profile_id_rejected(self):
        with pytest.raises(ProfileValidationError, match="profile_id"):
            assign_profile_to_item({"type": "series", "arr_id": 1, "profile_id": -1})

    def test_bool_arr_id_rejected(self):
        """``True`` is an int subclass — must be explicitly rejected."""
        with pytest.raises(ProfileValidationError, match="arr_id"):
            assign_profile_to_item({"type": "series", "arr_id": True, "profile_id": 1})

    def test_invalid_type_rejected_before_any_db_call(self):
        """Bad ``type`` must short-circuit before the profile lookup."""
        with (
            patch("db.profiles.get_language_profile") as mock_lookup,
            pytest.raises(ProfileValidationError, match="type"),
        ):
            assign_profile_to_item({"type": "tv", "arr_id": 1, "profile_id": 1})
        mock_lookup.assert_not_called()

    def test_valid_assignment_still_works(self):
        with (
            patch("db.profiles.get_language_profile", return_value={"id": 1, "name": "x"}),
            patch("db.profiles.assign_series_profile") as mock_assign,
        ):
            result = assign_profile_to_item({"type": "series", "arr_id": 5, "profile_id": 1})
        mock_assign.assert_called_once_with(5, 1)
        assert result["status"] == "assigned"


# ---------------------------------------------------------------------------
# assign_profile_bulk arr_ids cap
# ---------------------------------------------------------------------------


class TestAssignProfileBulkCap:
    """The /language-profiles/assign-bulk route must reject oversized arr_ids."""

    def test_bulk_assign_over_cap_returns_400(self, client):
        too_many = list(range(1, _MAX_BULK_ASSIGN + 2))
        resp = client.put(
            "/api/v1/language-profiles/assign-bulk",
            json={"type": "series", "arr_ids": too_many, "profile_id": 1},
        )
        assert resp.status_code == 400
        assert str(_MAX_BULK_ASSIGN) in resp.get_json()["error"]

    def test_bulk_assign_at_cap_is_accepted(self, client, monkeypatch):
        """At-cap is fine; over-cap is the boundary."""
        # Avoid actual DB work — patch the per-item assignment to no-op.
        monkeypatch.setattr(
            "routes.profiles.language.assign_profile_to_item",
            lambda *a, **kw: {"status": "assigned"},
        )
        ids = list(range(1, _MAX_BULK_ASSIGN + 1))
        resp = client.put(
            "/api/v1/language-profiles/assign-bulk",
            json={"type": "series", "arr_ids": ids, "profile_id": 1},
        )
        assert resp.status_code == 200
        assert resp.get_json()["assigned"] == _MAX_BULK_ASSIGN
