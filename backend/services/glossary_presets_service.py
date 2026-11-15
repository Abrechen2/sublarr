"""Import a bundled glossary preset into the global glossary."""

from __future__ import annotations


class UnknownPresetError(LookupError):
    """No bundled preset has the requested id."""


def list_presets() -> list[dict]:
    """Bundled presets for the settings page, each with its entries."""
    from glossary_presets import load_bundled_presets

    return load_bundled_presets()


def import_preset(preset_id: str) -> dict:
    """Add the preset's terms as approved global entries for its target language.

    A term the user already has — globally, for this language or for every
    language — is kept as it is: the import fills gaps, it never overwrites a
    choice. Running it twice adds nothing the second time.

    Returns:
        {"added": int, "skipped": int}

    Raises:
        UnknownPresetError: if no preset has ``preset_id``.
    """
    from db.translation import add_glossary_entry, get_global_glossary
    from glossary_presets import get_bundled_preset

    preset = get_bundled_preset(preset_id)
    if preset is None:
        raise UnknownPresetError(preset_id)

    target_language = preset["target_language"]
    existing = {e["source_term"].strip().lower() for e in get_global_glossary(target_language)}
    added = skipped = 0
    for entry in preset["entries"]:
        key = entry["source_term"].strip().lower()
        if key in existing:
            skipped += 1
            continue
        add_glossary_entry(
            None,
            entry["source_term"],
            entry["target_term"],
            f"Imported from preset {preset_id}",
            target_language=target_language,
        )
        existing.add(key)
        added += 1
    return {"added": added, "skipped": skipped}
