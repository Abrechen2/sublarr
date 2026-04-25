"""Tests for Pydantic schemas of the profiles-overrides API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.profiles_overrides import (
    OverridePatch,
    ResolvedSettingsResponse,
    ScopesTreeResponse,
)


def test_override_patch_accepts_known_fields():
    patch = OverridePatch.model_validate({"forced_preference": "prefer"})
    assert patch.changes == {"forced_preference": "prefer"}


def test_override_patch_accepts_null_to_clear():
    patch = OverridePatch.model_validate({"hi_preference": None})
    assert patch.changes == {"hi_preference": None}


def test_override_patch_rejects_unknown_field():
    with pytest.raises(ValidationError):
        OverridePatch.model_validate({"random_unknown_field": "x"})


def test_override_patch_rejects_invalid_enum_value():
    with pytest.raises(ValidationError):
        OverridePatch.model_validate({"forced_preference": "notvalid"})


def test_override_patch_validates_language_array():
    OverridePatch.model_validate({"target_languages": ["de", "en"]})
    with pytest.raises(ValidationError):
        OverridePatch.model_validate({"target_languages": ["xxx"]})


def test_resolved_response_shape():
    resp = ResolvedSettingsResponse.model_validate(
        {
            "scope": {"type": "series", "id": 42, "name": "Frieren"},
            "settings": {
                "cleanup_foreign_tracks": {
                    "effective": True,
                    "source": "series",
                    "chain": [
                        {"scope": "global", "value": False, "label": "Global default"},
                        {"scope": "series", "value": True, "label": "This series"},
                    ],
                }
            },
        }
    )
    assert resp.scope.type == "series"
