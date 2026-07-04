"""Business logic for language profiles, glossary, and prompt presets.

Extracted from routes/profiles.py to keep route handlers thin.
All public functions raise ``ValueError`` for validation errors and return
domain dicts/scalars — the route layer maps these to HTTP responses.
"""

from __future__ import annotations

import io
import logging

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


# Defense in depth: bulk-assign accepts a list of arr_ids and runs N DB
# round-trips. Without an upper bound a single request could pin a worker
# for minutes; cap at 1000 (matches /wanted/batch-action's existing 500-cap
# logic, slightly higher because profile assignment is cheaper than wanted
# bulk actions).
_MAX_BULK_ASSIGN = 1000

# ─── Valid enum values ───────────────────────────────────────────────────────

VALID_FORCED_PREFERENCES = ("disabled", "separate", "auto")
VALID_HI_PREFERENCES = ("include", "prefer", "exclude", "only")
VALID_FORCED_SCORING = ("include", "prefer", "exclude", "only")

UPDATABLE_PROFILE_KEYS = (
    "name",
    "source_language",
    "source_language_name",
    "target_languages",
    "target_language_names",
    "translation_backend",
    "fallback_chain",
    "forced_preference",
    "hi_preference",
    "forced_scoring",
    "must_contain",
    "must_not_contain",
    "cutoff_language",
    "audio_exclude_languages",
    "combine_enabled",
    "combine_format",
    "combine_languages",
    "combine_position",
)

VALID_COMBINE_FORMATS = ("ass", "srt")


# ─── Language Profile Logic ──────────────────────────────────────────────────


class ProfileValidationError(ValueError):
    """Raised when profile input fails validation."""


class ProfileConflictError(Exception):
    """Raised when a profile name already exists (UNIQUE constraint)."""


class ProfileNotFoundError(Exception):
    """Raised when a profile is not found."""


def validate_create_profile_data(data: dict) -> dict:
    """Parse and validate data for creating a language profile.

    Returns a sanitised kwargs dict ready for ``create_language_profile``.
    Raises ``ProfileValidationError`` on bad input.
    """
    name = data.get("name", "").strip()
    if not name:
        raise ProfileValidationError("name is required")

    target_langs = data.get("target_languages", ["de"])
    if not target_langs:
        raise ProfileValidationError("At least one target language is required")

    forced_preference = data.get("forced_preference", "disabled")
    if forced_preference not in VALID_FORCED_PREFERENCES:
        raise ProfileValidationError("forced_preference must be one of: disabled, separate, auto")

    hi_preference = data.get("hi_preference", "include")
    if hi_preference not in VALID_HI_PREFERENCES:
        raise ProfileValidationError("hi_preference must be one of: include, prefer, exclude, only")

    forced_scoring = data.get("forced_scoring", "include")
    if forced_scoring not in VALID_FORCED_SCORING:
        raise ProfileValidationError(
            "forced_scoring must be one of: include, prefer, exclude, only"
        )

    must_contain = data.get("must_contain", [])
    must_not_contain = data.get("must_not_contain", [])
    audio_exclude_languages = data.get("audio_exclude_languages", [])
    cutoff_language = data.get("cutoff_language", "")

    combine_format = data.get("combine_format", "ass")
    if combine_format not in VALID_COMBINE_FORMATS:
        raise ProfileValidationError("combine_format must be one of: ass, srt")
    combine_languages = data.get("combine_languages", [])
    combine_position = data.get("combine_position")

    return {
        "name": name,
        "source_lang": data.get("source_language", "en"),
        "source_name": data.get("source_language_name", "English"),
        "target_langs": target_langs,
        "target_names": data.get("target_language_names", ["German"]),
        "translation_backend": data.get("translation_backend", "ollama"),
        "fallback_chain": data.get("fallback_chain"),
        "forced_preference": forced_preference,
        "hi_preference": hi_preference,
        "forced_scoring": forced_scoring,
        "must_contain": must_contain if isinstance(must_contain, list) else [],
        "must_not_contain": must_not_contain if isinstance(must_not_contain, list) else [],
        "cutoff_language": cutoff_language if isinstance(cutoff_language, str) else "",
        "audio_exclude_languages": (
            audio_exclude_languages if isinstance(audio_exclude_languages, list) else []
        ),
        "combine_enabled": bool(data.get("combine_enabled", False)),
        "combine_format": combine_format,
        "combine_languages": combine_languages if isinstance(combine_languages, list) else [],
        "combine_position": combine_position if isinstance(combine_position, dict) else None,
    }


def create_profile(data: dict) -> dict:
    """Validate *data*, persist a new profile, and return its dict.

    Raises ``ProfileValidationError`` / ``ProfileConflictError``.
    """
    from db.profiles import create_language_profile, get_language_profile

    kwargs = validate_create_profile_data(data)

    try:
        profile_id = create_language_profile(**kwargs)
    except IntegrityError as exc:
        # Cross-DB UNIQUE-conflict detection. The previous string-match on
        # "UNIQUE constraint" only worked on SQLite — PostgreSQL raises
        # "duplicate key value violates unique constraint", so the same
        # request 500'd on PG instead of returning a clean 409.
        raise ProfileConflictError(f"Profile name '{kwargs['name']}' already exists") from exc
    except Exception as exc:
        # Legacy fallback: some test seams still raise plain Exception with
        # the SQLite phrasing. Once those are migrated this branch can go.
        if "UNIQUE constraint" in str(exc) or "unique constraint" in str(exc).lower():
            raise ProfileConflictError(f"Profile name '{kwargs['name']}' already exists") from exc
        raise

    return get_language_profile(profile_id)


def validate_update_profile_fields(data: dict) -> dict:
    """Extract updatable fields from *data* and validate enum values.

    Returns a dict of fields to update.
    Raises ``ProfileValidationError`` if validation fails.
    """
    fields = {k: data[k] for k in UPDATABLE_PROFILE_KEYS if k in data}

    if not fields:
        raise ProfileValidationError("No fields to update")

    if (
        "forced_preference" in fields
        and fields["forced_preference"] not in VALID_FORCED_PREFERENCES
    ):
        raise ProfileValidationError("forced_preference must be one of: disabled, separate, auto")

    if "hi_preference" in fields and fields["hi_preference"] not in VALID_HI_PREFERENCES:
        raise ProfileValidationError("hi_preference must be one of: include, prefer, exclude, only")

    if "forced_scoring" in fields and fields["forced_scoring"] not in VALID_FORCED_SCORING:
        raise ProfileValidationError(
            "forced_scoring must be one of: include, prefer, exclude, only"
        )

    if "combine_format" in fields and fields["combine_format"] not in VALID_COMBINE_FORMATS:
        raise ProfileValidationError("combine_format must be one of: ass, srt")

    return fields


def update_profile(profile_id: int, data: dict) -> dict:
    """Validate and apply updates to *profile_id*. Returns the updated dict.

    Raises ``ProfileNotFoundError``, ``ProfileValidationError``,
    ``ProfileConflictError``.
    """
    from db.profiles import get_language_profile, update_language_profile

    profile = get_language_profile(profile_id)
    if not profile:
        raise ProfileNotFoundError("Profile not found")

    fields = validate_update_profile_fields(data)

    try:
        update_language_profile(profile_id, **fields)
    except IntegrityError as exc:
        raise ProfileConflictError(f"Profile name '{data.get('name')}' already exists") from exc
    except Exception as exc:
        if "UNIQUE constraint" in str(exc) or "unique constraint" in str(exc).lower():
            raise ProfileConflictError(f"Profile name '{data.get('name')}' already exists") from exc
        raise

    return get_language_profile(profile_id)


def delete_profile(profile_id: int) -> dict:
    """Delete *profile_id*. Returns ``{"status": "deleted", "id": ...}``.

    Raises ``ProfileNotFoundError`` if not found or is default.
    """
    from db.profiles import delete_language_profile

    deleted = delete_language_profile(profile_id)
    if not deleted:
        raise ProfileNotFoundError("Profile not found or is the default profile")
    return {"status": "deleted", "id": profile_id}


def assign_profile_to_item(data: dict) -> dict:
    """Assign a profile to a series or movie.

    Returns a status dict. Raises ``ProfileValidationError`` /
    ``ProfileNotFoundError``.
    """
    from db.profiles import assign_movie_profile, assign_series_profile, get_language_profile

    item_type = data.get("type")
    arr_id = data.get("arr_id")
    profile_id = data.get("profile_id")

    if not item_type or arr_id is None or profile_id is None:
        raise ProfileValidationError("type, arr_id, and profile_id are required")

    # Validate item_type up front so a typo doesn't run through a profile
    # lookup before failing.
    if item_type not in ("series", "movie"):
        raise ProfileValidationError("type must be 'series' or 'movie'")

    # Validate ID types before any DB lookup. Previously a string arr_id
    # ("abc") sailed through the truthiness check and surfaced as a 500
    # from the underlying driver.
    if not isinstance(arr_id, int) or isinstance(arr_id, bool) or arr_id < 1:
        raise ProfileValidationError("arr_id must be a positive integer")
    if not isinstance(profile_id, int) or isinstance(profile_id, bool) or profile_id < 1:
        raise ProfileValidationError("profile_id must be a positive integer")

    profile = get_language_profile(profile_id)
    if not profile:
        raise ProfileNotFoundError("Profile not found")

    if item_type == "series":
        assign_series_profile(arr_id, profile_id)
    else:  # validated to be "movie" above
        assign_movie_profile(arr_id, profile_id)

    return {"status": "assigned", "type": item_type, "arr_id": arr_id, "profile_id": profile_id}


def set_default_for_all(profile_id: int) -> dict:
    """Set *profile_id* as default for all items.

    Returns ``{"status": "ok", "profile": ...}``.
    Raises ``ProfileNotFoundError``.
    """
    from db.profiles import get_language_profile, set_profile_as_default_for_all

    profile = get_language_profile(profile_id)
    if not profile:
        raise ProfileNotFoundError("Profile not found")

    set_profile_as_default_for_all(profile_id)
    updated = get_language_profile(profile_id)
    return {"status": "ok", "profile": updated}


# ─── Glossary Logic ──────────────────────────────────────────────────────────


def create_glossary(data: dict) -> dict:
    """Create a glossary entry. Returns the entry dict.

    Raises ``ProfileValidationError`` on missing fields.
    """
    from db.translation import add_glossary_entry, get_glossary_entry

    source_term = data.get("source_term", "").strip()
    target_term = data.get("target_term", "").strip()

    if not source_term or not target_term:
        raise ProfileValidationError("source_term and target_term are required")

    entry_id = add_glossary_entry(
        data.get("series_id"),
        source_term,
        target_term,
        data.get("notes", "").strip(),
        term_type=data.get("term_type", "other"),
        confidence=data.get("confidence"),
        approved=data.get("approved", 1),
    )
    return get_glossary_entry(entry_id)


def update_glossary(entry_id: int, data: dict) -> dict:
    """Update a glossary entry. Returns the updated entry dict.

    Raises ``ProfileNotFoundError`` / ``ProfileValidationError``.
    """
    from db.translation import get_glossary_entry, update_glossary_entry

    entry = get_glossary_entry(entry_id)
    if not entry:
        raise ProfileNotFoundError("Entry not found")

    _sentinel = ...
    confidence = data.get("confidence", _sentinel) if "confidence" in data else _sentinel

    updated = update_glossary_entry(
        entry_id,
        source_term=data.get("source_term"),
        target_term=data.get("target_term"),
        notes=data.get("notes"),
        term_type=data.get("term_type"),
        confidence=confidence,
        approved=data.get("approved"),
    )

    if not updated:
        raise ProfileValidationError("No fields to update")

    return get_glossary_entry(entry_id)


def delete_glossary(entry_id: int) -> dict:
    """Delete a glossary entry. Returns ``{"status": "deleted", "id": ...}``.

    Raises ``ProfileNotFoundError``.
    """
    from db.translation import delete_glossary_entry

    deleted = delete_glossary_entry(entry_id)
    if not deleted:
        raise ProfileNotFoundError("Entry not found")
    return {"status": "deleted", "id": entry_id}


def export_glossary_as_tsv(series_id: int | None) -> tuple[str, str]:
    """Build a TSV string from glossary entries.

    Returns ``(tsv_content, filename)``.

    Hardening (audit 2026-04-30):
    - Newlines / carriage returns inside values are replaced with spaces,
      otherwise they would break the row-per-line TSV invariant on the
      consumer side (Excel / Sheets / pandas all assume one row per line).
    - Cells beginning with ``= + - @ \\t`` are prefixed with ``'`` so
      Excel/Sheets won't interpret them as formulas (CSV-injection,
      OWASP-recommended mitigation). The leading apostrophe is stripped
      automatically by spreadsheet UIs on display.
    """
    from db.translation import get_glossary_entries

    entries = get_glossary_entries(series_id)

    output = io.StringIO()
    output.write("source_term\ttarget_term\tterm_type\tnotes\n")
    for entry in entries:
        source_term = _tsv_safe(entry.get("source_term"))
        target_term = _tsv_safe(entry.get("target_term"))
        term_type = _tsv_safe(entry.get("term_type"))
        notes = _tsv_safe(entry.get("notes"))
        output.write(f"{source_term}\t{target_term}\t{term_type}\t{notes}\n")

    tsv_content = output.getvalue()
    filename = (
        f"glossary_series_{series_id}.tsv" if series_id is not None else "glossary_global.tsv"
    )
    return tsv_content, filename


def _tsv_safe(value: str | None) -> str:
    """Sanitise a value for TSV output: strip control chars + neutralise CSV injection."""
    if value is None:
        return ""
    # Collapse tabs / newlines / CRs — preserve row-per-line invariant.
    cleaned = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    # CSV-injection: prefix dangerous leading chars with ``'`` so spreadsheet
    # apps render them as text rather than executing as formulas.
    if cleaned and cleaned[0] in ("=", "+", "-", "@"):
        cleaned = "'" + cleaned
    return cleaned


# ─── Prompt Preset Logic ─────────────────────────────────────────────────────


def create_preset(data: dict) -> dict:
    """Create a prompt preset. Returns the preset dict.

    Reloads settings if the new preset is marked as default.
    Raises ``ProfileValidationError``.
    """
    from config import reload_settings
    from db.config import get_all_config_entries
    from db.translation import add_prompt_preset, get_prompt_preset

    name = data.get("name", "").strip()
    prompt_template = data.get("prompt_template", "").strip()
    is_default = data.get("is_default", False)

    if not name or not prompt_template:
        raise ProfileValidationError("name and prompt_template are required")

    preset_id = add_prompt_preset(name, prompt_template, is_default)
    preset = get_prompt_preset(preset_id)

    if is_default:
        all_overrides = get_all_config_entries()
        reload_settings(all_overrides)

    return preset


def update_preset(preset_id: int, data: dict) -> dict:
    """Update a prompt preset. Returns the updated preset dict.

    Reloads settings if the preset is or was the default.
    Raises ``ProfileNotFoundError`` / ``ProfileValidationError``.
    """
    from config import reload_settings
    from db.config import get_all_config_entries
    from db.translation import get_prompt_preset, update_prompt_preset

    preset = get_prompt_preset(preset_id)
    if not preset:
        raise ProfileNotFoundError("Preset not found")

    updated = update_prompt_preset(
        preset_id,
        name=data.get("name"),
        prompt_template=data.get("prompt_template"),
        is_default=data.get("is_default"),
    )

    if not updated:
        raise ProfileValidationError("No fields to update")

    updated_preset = get_prompt_preset(preset_id)

    if data.get("is_default") or preset.get("is_default"):
        all_overrides = get_all_config_entries()
        reload_settings(all_overrides)

    return updated_preset


def delete_preset(preset_id: int) -> dict:
    """Delete a prompt preset. Returns ``{"status": "deleted", "id": ...}``.

    Raises ``ProfileNotFoundError``.
    """
    from db.translation import delete_prompt_preset

    deleted = delete_prompt_preset(preset_id)
    if not deleted:
        raise ProfileNotFoundError("Preset not found or cannot delete last preset")
    return {"status": "deleted", "id": preset_id}
