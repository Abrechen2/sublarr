"""Tests for per-profile provisional-MT config fields (plan #8, Task 1).

When ``mt_keep_seeking_original`` is enabled on a profile, a Sublarr-translated
subtitle is recorded with ``source="machine_translation"`` and its wanted item
stays "provisional" (still seeking the human original) instead of being
deleted. See docs/plans/2026-07-03-v1.6-provisional-mt.md.
"""

from __future__ import annotations

import pytest

from db.models.core import LanguageProfile
from db.repositories.profiles import ProfileRepository
from extensions import db


def test_new_profile_has_provisional_mt_defaults(app_ctx):
    """A freshly created LanguageProfile row gets the provisional-MT defaults."""
    repo = ProfileRepository()
    profile_id = repo.create_profile(
        name="Provisional MT Defaults",
        source_lang="en",
        source_name="English",
        target_langs=["de"],
        target_names=["German"],
    )

    profile = db.session.get(LanguageProfile, profile_id)
    assert profile is not None
    assert profile.mt_keep_seeking_original == 0
    assert profile.mt_on_original_found == "notify"
    assert profile.mt_min_original_score == 1


def test_update_profile_accepts_mt_keep_seeking_original(app_ctx):
    """PUT /language-profiles/<id> must accept mt_keep_seeking_original.

    Regression: the field was missing from both the service-layer
    UPDATABLE_PROFILE_KEYS and the repository-layer allowed set, so a PUT with
    only this field 400'd ("No fields to update") and it could only be toggled
    via a raw DB write. It must round-trip through the API as an int flag.
    """
    from services.profile_service import update_profile

    repo = ProfileRepository()
    profile_id = repo.create_profile(
        name="MT Keep Seeking PUT",
        source_lang="en",
        source_name="English",
        target_langs=["de"],
        target_names=["German"],
    )

    # Turn it on (truthy value coerces to the 0/1 int column).
    updated = update_profile(profile_id, {"mt_keep_seeking_original": True})
    assert updated["mt_keep_seeking_original"] == 1
    assert db.session.get(LanguageProfile, profile_id).mt_keep_seeking_original == 1

    # And back off.
    updated = update_profile(profile_id, {"mt_keep_seeking_original": False})
    assert updated["mt_keep_seeking_original"] == 0
    assert db.session.get(LanguageProfile, profile_id).mt_keep_seeking_original == 0


def test_create_profile_accepts_mt_keep_seeking_original(app_ctx):
    """POST /language-profiles must persist mt_keep_seeking_original.

    The create path flows service.validate_create_profile_data →
    db.profiles.create_language_profile → ProfileRepository.create_profile; all
    three must carry the flag so a profile created with the UI toggle on keeps
    it (previously the field was silently dropped on create).
    """
    from services.profile_service import create_profile

    prof = create_profile(
        {
            "name": "MT Keep Seeking Create",
            "target_languages": ["de"],
            "target_language_names": ["German"],
            "translation_backend": "deepl",
            "mt_keep_seeking_original": True,
        }
    )
    assert prof["mt_keep_seeking_original"] == 1
    assert db.session.get(LanguageProfile, prof["id"]).mt_keep_seeking_original == 1


# ---------------------------------------------------------------------------
# Phase 2 (#8b): mt_on_original_found / mt_min_original_score API exposure
# ---------------------------------------------------------------------------
#
# Phase 2 (mt_reseek job + approve/reject UI) landed in 1.6.2 and both
# services.mt_reseek._resolve_min_original_score and _on_original_found read
# these fields off the resolved profile dict -- but until this fix they were
# DB-only, so every profile was permanently stuck on the "notify" default
# with no way to reach "auto_replace" except a raw DB edit.


def test_create_profile_accepts_mt_on_original_found_and_min_score(app_ctx):
    """POST /language-profiles must persist mt_on_original_found and
    mt_min_original_score, not silently drop them."""
    from services.profile_service import create_profile

    prof = create_profile(
        {
            "name": "MT Phase2 Create",
            "target_languages": ["de"],
            "target_language_names": ["German"],
            "translation_backend": "deepl",
            "mt_on_original_found": "auto_replace",
            "mt_min_original_score": 42,
        }
    )
    assert prof["mt_on_original_found"] == "auto_replace"
    assert prof["mt_min_original_score"] == 42

    row = db.session.get(LanguageProfile, prof["id"])
    assert row.mt_on_original_found == "auto_replace"
    assert row.mt_min_original_score == 42


def test_create_profile_omitting_mt_fields_still_defaults(app_ctx):
    """Regression: omitting both fields on create must not break profile
    creation and must still default to notify / 1."""
    from services.profile_service import create_profile

    prof = create_profile(
        {
            "name": "MT Phase2 Defaults",
            "target_languages": ["de"],
            "target_language_names": ["German"],
        }
    )
    assert prof["mt_on_original_found"] == "notify"
    assert prof["mt_min_original_score"] == 1


def test_create_profile_rejects_invalid_mt_on_original_found():
    from services.profile_service import ProfileValidationError, create_profile

    with pytest.raises(ProfileValidationError, match="mt_on_original_found"):
        create_profile(
            {
                "name": "MT Phase2 Invalid",
                "target_languages": ["de"],
                "mt_on_original_found": "delete_original",
            }
        )


def test_create_profile_rejects_negative_min_original_score():
    from services.profile_service import ProfileValidationError, create_profile

    with pytest.raises(ProfileValidationError, match="mt_min_original_score"):
        create_profile(
            {
                "name": "MT Phase2 Negative Score",
                "target_languages": ["de"],
                "mt_min_original_score": -1,
            }
        )


def test_update_profile_accepts_mt_on_original_found_and_min_score(app_ctx):
    """PUT /language-profiles/<id> must accept both phase-2 fields."""
    from services.profile_service import update_profile

    repo = ProfileRepository()
    profile_id = repo.create_profile(
        name="MT Phase2 Update",
        source_lang="en",
        source_name="English",
        target_langs=["de"],
        target_names=["German"],
    )

    updated = update_profile(
        profile_id,
        {"mt_on_original_found": "auto_replace", "mt_min_original_score": 7},
    )
    assert updated["mt_on_original_found"] == "auto_replace"
    assert updated["mt_min_original_score"] == 7

    row = db.session.get(LanguageProfile, profile_id)
    assert row.mt_on_original_found == "auto_replace"
    assert row.mt_min_original_score == 7


def test_update_profile_rejects_invalid_mt_on_original_found(app_ctx):
    from services.profile_service import ProfileValidationError, update_profile

    repo = ProfileRepository()
    profile_id = repo.create_profile(
        name="MT Phase2 Update Invalid",
        source_lang="en",
        source_name="English",
        target_langs=["de"],
        target_names=["German"],
    )

    with pytest.raises(ProfileValidationError, match="mt_on_original_found"):
        update_profile(profile_id, {"mt_on_original_found": "ignore"})


def test_update_profile_rejects_negative_min_original_score(app_ctx):
    from services.profile_service import ProfileValidationError, update_profile

    repo = ProfileRepository()
    profile_id = repo.create_profile(
        name="MT Phase2 Update Negative",
        source_lang="en",
        source_name="English",
        target_langs=["de"],
        target_names=["German"],
    )

    with pytest.raises(ProfileValidationError, match="mt_min_original_score"):
        update_profile(profile_id, {"mt_min_original_score": -5})
