"""Tests for per-profile provisional-MT config fields (plan #8, Task 1).

When ``mt_keep_seeking_original`` is enabled on a profile, a Sublarr-translated
subtitle is recorded with ``source="machine_translation"`` and its wanted item
stays "provisional" (still seeking the human original) instead of being
deleted. See docs/plans/2026-07-03-v1.6-provisional-mt.md.
"""

from __future__ import annotations

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
