"""Tests for the inheritance resolver service."""
from __future__ import annotations

import pytest

from services.inheritance_resolver import (
    INHERITABLE_FIELDS,
    InheritableField,
    ResolvedSetting,
)


def test_registry_has_twelve_fields():
    assert len(INHERITABLE_FIELDS) == 12


def test_registry_field_names_unique():
    names = [f.display_name for f in INHERITABLE_FIELDS]
    assert len(names) == len(set(names))


def test_registry_includes_known_fields():
    names = {f.display_name for f in INHERITABLE_FIELDS}
    assert names == {
        "cleanup_foreign_tracks",
        "forced_preference",
        "hi_preference",
        "forced_scoring",
        "target_languages",
        "cutoff_language",
        "must_contain",
        "must_not_contain",
        "audio_exclude_languages",
        "preferred_audio_track_index",
        "priority_override",
        "min_attempts_per_day",
    }


def test_resolved_setting_typed_dict_shape():
    r: ResolvedSetting = {
        "effective": True,
        "source": "series",
        "chain": [
            {"scope": "global", "value": False, "label": "Global default"},
            {"scope": "series", "value": True, "label": "Frieren"},
        ],
    }
    assert r["source"] == "series"
