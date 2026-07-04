"""Tests for per-profile combined-subtitle config fields (V1.6 Feature #1, C1).

A LanguageProfile carries the combine rules: whether automatic combine is on,
the output format, which target languages to combine, and ASS positioning.
Unlike the provisional-MT fields (#8), combine IS exposed through profile CRUD
because the frontend profile editor edits it directly.
See docs/plans/2026-07-04-v1.6-combined-subtitles.md.
"""

from __future__ import annotations

import json

import pytest

from db.models.core import LanguageProfile
from db.repositories.profiles import ProfileRepository
from extensions import db

_DEFAULT_POSITION = {"primary": "bottom", "secondary": "top"}


def _make(repo: ProfileRepository, name: str, **extra) -> int:
    return repo.create_profile(
        name=name,
        source_lang="en",
        source_name="English",
        target_langs=["de", "en"],
        target_names=["German", "English"],
        **extra,
    )


def test_new_profile_has_combine_defaults(app_ctx):
    """A freshly created profile gets the combine defaults."""
    repo = ProfileRepository()
    pid = _make(repo, "Combine Defaults")

    p = db.session.get(LanguageProfile, pid)
    assert p.combine_enabled == 0
    assert p.combine_format == "ass"
    assert json.loads(p.combine_languages_json) == []
    assert json.loads(p.combine_position_json) == _DEFAULT_POSITION


def test_serialized_profile_exposes_parsed_combine_fields(app_ctx):
    """get_profile() returns parsed combine_* keys and strips the raw _json columns."""
    repo = ProfileRepository()
    pid = _make(repo, "Combine Serialize")

    d = repo.get_profile(pid)
    assert d["combine_enabled"] is False
    assert d["combine_format"] == "ass"
    assert d["combine_languages"] == []
    assert d["combine_position"] == _DEFAULT_POSITION
    assert "combine_languages_json" not in d
    assert "combine_position_json" not in d


def test_create_profile_accepts_combine_kwargs(app_ctx):
    repo = ProfileRepository()
    pid = _make(
        repo,
        "Combine Create",
        combine_enabled=True,
        combine_format="srt",
        combine_languages=["de", "en"],
        combine_position={"primary": "top", "secondary": "bottom"},
    )

    d = repo.get_profile(pid)
    assert d["combine_enabled"] is True
    assert d["combine_format"] == "srt"
    assert d["combine_languages"] == ["de", "en"]
    assert d["combine_position"] == {"primary": "top", "secondary": "bottom"}


def test_update_profile_persists_combine_fields(app_ctx):
    repo = ProfileRepository()
    pid = _make(repo, "Combine Update")

    ok = repo.update_profile(
        pid,
        combine_enabled=1,
        combine_format="srt",
        combine_languages=["de", "en"],
        combine_position={"primary": "top", "secondary": "bottom"},
    )
    assert ok

    d = repo.get_profile(pid)
    assert d["combine_enabled"] is True
    assert d["combine_format"] == "srt"
    assert d["combine_languages"] == ["de", "en"]
    assert d["combine_position"] == {"primary": "top", "secondary": "bottom"}


def test_create_profile_rejects_invalid_combine_format(app_ctx):
    repo = ProfileRepository()
    with pytest.raises(ValueError):
        _make(repo, "Combine Bad Fmt", combine_format="vtt")


def test_update_profile_rejects_invalid_combine_format(app_ctx):
    repo = ProfileRepository()
    pid = _make(repo, "Combine Update Bad Fmt")
    with pytest.raises(ValueError):
        repo.update_profile(pid, combine_format="mkv")


# --- Service layer (the mapping from route JSON body to repo kwargs) ---------


def test_service_create_and_update_round_trip_combine(app_ctx):
    """The profile_service maps combine_* JSON keys through to persistence."""
    from services import profile_service

    created = profile_service.create_profile(
        {
            "name": "Combine Service",
            "target_languages": ["de", "en"],
            "target_language_names": ["German", "English"],
            "combine_enabled": True,
            "combine_format": "ass",
            "combine_languages": ["de", "en"],
            "combine_position": {"primary": "bottom", "secondary": "top"},
        }
    )
    assert created["combine_enabled"] is True
    assert created["combine_languages"] == ["de", "en"]

    updated = profile_service.update_profile(
        created["id"],
        {"combine_format": "srt", "combine_position": {"primary": "top", "secondary": "bottom"}},
    )
    assert updated["combine_format"] == "srt"
    assert updated["combine_position"] == {"primary": "top", "secondary": "bottom"}


def test_service_create_rejects_bad_combine_format(app_ctx):
    from services import profile_service

    with pytest.raises(profile_service.ProfileValidationError):
        profile_service.create_profile({"name": "Combine Service Bad", "combine_format": "vtt"})
