"""Profile routes — /language-profiles/*, /glossary/*, /prompt-presets/*."""

import logging
from flask import Blueprint, request, jsonify

bp = Blueprint("profiles", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/language-profiles", methods=["GET"])
def list_language_profiles():
    """Get all language profiles.
    ---
    get:
      tags:
        - Profiles
      summary: List all language profiles
      description: Returns all configured language profiles including source/target languages, translation backend, and forced subtitle preference.
      responses:
        200:
          description: List of language profiles
          content:
            application/json:
              schema:
                type: object
                properties:
                  profiles:
                    type: array
                    items:
                      type: object
    """
    from db.profiles import get_all_language_profiles
    profiles = get_all_language_profiles()
    return jsonify({"profiles": profiles})


@bp.route("/language-profiles", methods=["POST"])
def create_language_profile_endpoint():
    """Create a new language profile.
    ---
    post:
      tags:
        - Profiles
      summary: Create a language profile
      description: Creates a new language profile with source/target languages, translation backend, fallback chain, and forced subtitle preference.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
              properties:
                name:
                  type: string
                source_language:
                  type: string
                  default: en
                source_language_name:
                  type: string
                  default: English
                target_languages:
                  type: array
                  items:
                    type: string
                  default: ["de"]
                target_language_names:
                  type: array
                  items:
                    type: string
                  default: ["German"]
                translation_backend:
                  type: string
                  default: ollama
                fallback_chain:
                  type: array
                  items:
                    type: string
                forced_preference:
                  type: string
                  enum: [disabled, separate, auto]
                  default: disabled
      responses:
        201:
          description: Profile created
          content:
            application/json:
              schema:
                type: object
        400:
          description: Validation error (missing name or target languages)
        409:
          description: Profile name already exists
    """
    from db.profiles import create_language_profile, get_language_profile

    data = request.get_json() or {}

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    source_lang = data.get("source_language", "en")
    source_name = data.get("source_language_name", "English")
    target_langs = data.get("target_languages", ["de"])
    target_names = data.get("target_language_names", ["German"])

    if not target_langs:
        return jsonify({"error": "At least one target language is required"}), 400

    translation_backend = data.get("translation_backend", "ollama")
    fallback_chain = data.get("fallback_chain")
    forced_preference = data.get("forced_preference", "disabled")

    if forced_preference not in ("disabled", "separate", "auto"):
        return jsonify({"error": "forced_preference must be one of: disabled, separate, auto"}), 400

    try:
        profile_id = create_language_profile(
            name, source_lang, source_name, target_langs, target_names,
            translation_backend=translation_backend,
            fallback_chain=fallback_chain,
            forced_preference=forced_preference,
        )
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": f"Profile name '{name}' already exists"}), 409
        return jsonify({"error": str(e)}), 500

    profile = get_language_profile(profile_id)
    return jsonify(profile), 201


@bp.route("/language-profiles/<int:profile_id>", methods=["PUT"])
def update_language_profile_endpoint(profile_id):
    """Update a language profile.
    ---
    put:
      tags:
        - Profiles
      summary: Update a language profile
      description: Updates an existing language profile. Only provided fields are changed.
      parameters:
        - in: path
          name: profile_id
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                source_language:
                  type: string
                source_language_name:
                  type: string
                target_languages:
                  type: array
                  items:
                    type: string
                target_language_names:
                  type: array
                  items:
                    type: string
                translation_backend:
                  type: string
                fallback_chain:
                  type: array
                  items:
                    type: string
                forced_preference:
                  type: string
                  enum: [disabled, separate, auto]
      responses:
        200:
          description: Updated profile
          content:
            application/json:
              schema:
                type: object
        400:
          description: No fields to update or invalid forced_preference
        404:
          description: Profile not found
        409:
          description: Profile name already exists
    """
    from db.profiles import get_language_profile, update_language_profile

    profile = get_language_profile(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    data = request.get_json() or {}
    fields = {}
    for key in ("name", "source_language", "source_language_name",
                "target_languages", "target_language_names",
                "translation_backend", "fallback_chain", "forced_preference"):
        if key in data:
            fields[key] = data[key]

    if not fields:
        return jsonify({"error": "No fields to update"}), 400

    if "forced_preference" in fields and fields["forced_preference"] not in ("disabled", "separate", "auto"):
        return jsonify({"error": "forced_preference must be one of: disabled, separate, auto"}), 400

    try:
        update_language_profile(profile_id, **fields)
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": f"Profile name '{data.get('name')}' already exists"}), 409
        return jsonify({"error": str(e)}), 500

    updated = get_language_profile(profile_id)
    return jsonify(updated)


@bp.route("/language-profiles/<int:profile_id>", methods=["DELETE"])
def delete_language_profile_endpoint(profile_id):
    """Delete a language profile (cannot delete default).
    ---
    delete:
      tags:
        - Profiles
      summary: Delete a language profile
      description: Deletes a language profile by ID. The default profile cannot be deleted.
      parameters:
        - in: path
          name: profile_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Profile deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
        400:
          description: Profile not found or is the default profile
    """
    from db.profiles import delete_language_profile

    deleted = delete_language_profile(profile_id)
    if not deleted:
        return jsonify({"error": "Profile not found or is the default profile"}), 400
    return jsonify({"status": "deleted", "id": profile_id})


@bp.route("/language-profiles/assign", methods=["PUT"])
def assign_profile():
    """Assign a language profile to a series or movie.

    Body: { type: "series"|"movie", arr_id: int, profile_id: int }
    ---
    put:
      tags:
        - Profiles
      summary: Assign profile to series or movie
      description: Assigns a language profile to a specific series or movie by Arr ID.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - type
                - arr_id
                - profile_id
              properties:
                type:
                  type: string
                  enum: [series, movie]
                arr_id:
                  type: integer
                profile_id:
                  type: integer
      responses:
        200:
          description: Profile assigned
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  type:
                    type: string
                  arr_id:
                    type: integer
                  profile_id:
                    type: integer
        400:
          description: Missing required fields or invalid type
        404:
          description: Profile not found
    """
    from db.profiles import assign_series_profile, assign_movie_profile, get_language_profile

    data = request.get_json() or {}

    item_type = data.get("type")
    arr_id = data.get("arr_id")
    profile_id = data.get("profile_id")

    if not item_type or arr_id is None or profile_id is None:
        return jsonify({"error": "type, arr_id, and profile_id are required"}), 400

    # Verify profile exists
    profile = get_language_profile(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    if item_type == "series":
        assign_series_profile(arr_id, profile_id)
    elif item_type == "movie":
        assign_movie_profile(arr_id, profile_id)
    else:
        return jsonify({"error": "type must be 'series' or 'movie'"}), 400

    return jsonify({"status": "assigned", "type": item_type, "arr_id": arr_id, "profile_id": profile_id})


# ─── Glossary Endpoints ──────────────────────────────────────────────────────


@bp.route("/glossary", methods=["GET"])
def list_glossary():
    """Get glossary entries for a series.
    ---
    get:
      tags:
        - Profiles
      summary: List glossary entries
      description: Returns glossary entries for a series. Optionally filter by search query.
      parameters:
        - in: query
          name: series_id
          required: true
          schema:
            type: integer
        - in: query
          name: query
          schema:
            type: string
          description: Search filter for glossary terms
      responses:
        200:
          description: Glossary entries
          content:
            application/json:
              schema:
                type: object
                properties:
                  entries:
                    type: array
                    items:
                      type: object
                  series_id:
                    type: integer
        400:
          description: series_id is required
    """
    from db.translation import get_glossary_entries, search_glossary_terms

    series_id = request.args.get("series_id", type=int)
    query = request.args.get("query", "").strip()

    if not series_id:
        return jsonify({"error": "series_id is required"}), 400

    if query:
        entries = search_glossary_terms(series_id, query)
    else:
        entries = get_glossary_entries(series_id)

    return jsonify({"entries": entries, "series_id": series_id})


@bp.route("/glossary", methods=["POST"])
def create_glossary_entry():
    """Create a new glossary entry.
    ---
    post:
      tags:
        - Profiles
      summary: Create a glossary entry
      description: Adds a new source-to-target term mapping for translation consistency.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - series_id
                - source_term
                - target_term
              properties:
                series_id:
                  type: integer
                source_term:
                  type: string
                target_term:
                  type: string
                notes:
                  type: string
      responses:
        201:
          description: Entry created
          content:
            application/json:
              schema:
                type: object
        400:
          description: Missing required fields
    """
    from db.translation import add_glossary_entry, get_glossary_entry

    data = request.get_json() or {}
    series_id = data.get("series_id")
    source_term = data.get("source_term", "").strip()
    target_term = data.get("target_term", "").strip()
    notes = data.get("notes", "").strip()

    if not series_id:
        return jsonify({"error": "series_id is required"}), 400
    if not source_term or not target_term:
        return jsonify({"error": "source_term and target_term are required"}), 400

    entry_id = add_glossary_entry(series_id, source_term, target_term, notes)
    entry = get_glossary_entry(entry_id)
    return jsonify(entry), 201


@bp.route("/glossary/<int:entry_id>", methods=["PUT"])
def update_glossary_entry_endpoint(entry_id):
    """Update a glossary entry.
    ---
    put:
      tags:
        - Profiles
      summary: Update a glossary entry
      description: Updates an existing glossary entry. Only provided fields are changed.
      parameters:
        - in: path
          name: entry_id
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                source_term:
                  type: string
                target_term:
                  type: string
                notes:
                  type: string
      responses:
        200:
          description: Updated entry
          content:
            application/json:
              schema:
                type: object
        400:
          description: No fields to update
        404:
          description: Entry not found
    """
    from db.translation import get_glossary_entry, update_glossary_entry

    entry = get_glossary_entry(entry_id)
    if not entry:
        return jsonify({"error": "Entry not found"}), 404

    data = request.get_json() or {}
    source_term = data.get("source_term")
    target_term = data.get("target_term")
    notes = data.get("notes")

    updated = update_glossary_entry(
        entry_id,
        source_term=source_term,
        target_term=target_term,
        notes=notes,
    )

    if not updated:
        return jsonify({"error": "No fields to update"}), 400

    updated_entry = get_glossary_entry(entry_id)
    return jsonify(updated_entry)


@bp.route("/glossary/<int:entry_id>", methods=["DELETE"])
def delete_glossary_entry_endpoint(entry_id):
    """Delete a glossary entry.
    ---
    delete:
      tags:
        - Profiles
      summary: Delete a glossary entry
      description: Removes a glossary entry by ID.
      parameters:
        - in: path
          name: entry_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Entry deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
        404:
          description: Entry not found
    """
    from db.translation import delete_glossary_entry

    deleted = delete_glossary_entry(entry_id)
    if not deleted:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"status": "deleted", "id": entry_id})


# ─── Prompt Presets Endpoints ────────────────────────────────────────────────


@bp.route("/prompt-presets", methods=["GET"])
def list_prompt_presets():
    """Get all prompt presets.
    ---
    get:
      tags:
        - Profiles
      summary: List prompt presets
      description: Returns all configured prompt presets for LLM translation.
      responses:
        200:
          description: List of prompt presets
          content:
            application/json:
              schema:
                type: object
                properties:
                  presets:
                    type: array
                    items:
                      type: object
    """
    from db.translation import get_prompt_presets
    presets = get_prompt_presets()
    return jsonify({"presets": presets})


@bp.route("/prompt-presets/default", methods=["GET"])
def get_default_preset():
    """Get the default prompt preset.
    ---
    get:
      tags:
        - Profiles
      summary: Get default prompt preset
      description: Returns the prompt preset currently marked as default.
      responses:
        200:
          description: Default preset
          content:
            application/json:
              schema:
                type: object
        404:
          description: No default preset found
    """
    from db.translation import get_default_prompt_preset
    preset = get_default_prompt_preset()
    if not preset:
        return jsonify({"error": "No default preset found"}), 404
    return jsonify(preset)


@bp.route("/prompt-presets", methods=["POST"])
def create_prompt_preset():
    """Create a new prompt preset.
    ---
    post:
      tags:
        - Profiles
      summary: Create a prompt preset
      description: Creates a new prompt preset for LLM translation. If is_default is true, the previous default is unset.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
                - prompt_template
              properties:
                name:
                  type: string
                prompt_template:
                  type: string
                is_default:
                  type: boolean
                  default: false
      responses:
        201:
          description: Preset created
          content:
            application/json:
              schema:
                type: object
        400:
          description: Missing name or prompt_template
    """
    from db.translation import add_prompt_preset, get_prompt_preset
    from config import reload_settings
    from db.config import get_all_config_entries

    data = request.get_json() or {}
    name = data.get("name", "").strip()
    prompt_template = data.get("prompt_template", "").strip()
    is_default = data.get("is_default", False)

    if not name or not prompt_template:
        return jsonify({"error": "name and prompt_template are required"}), 400

    preset_id = add_prompt_preset(name, prompt_template, is_default)
    preset = get_prompt_preset(preset_id)

    # Reload settings if default preset was created
    if is_default:
        all_overrides = get_all_config_entries()
        reload_settings(all_overrides)

    return jsonify(preset), 201


@bp.route("/prompt-presets/<int:preset_id>", methods=["PUT"])
def update_prompt_preset_endpoint(preset_id):
    """Update a prompt preset.
    ---
    put:
      tags:
        - Profiles
      summary: Update a prompt preset
      description: Updates an existing prompt preset. If is_default is set to true, the previous default is unset.
      parameters:
        - in: path
          name: preset_id
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                prompt_template:
                  type: string
                is_default:
                  type: boolean
      responses:
        200:
          description: Updated preset
          content:
            application/json:
              schema:
                type: object
        400:
          description: No fields to update
        404:
          description: Preset not found
    """
    from db.translation import get_prompt_preset, update_prompt_preset
    from config import reload_settings
    from db.config import get_all_config_entries

    preset = get_prompt_preset(preset_id)
    if not preset:
        return jsonify({"error": "Preset not found"}), 404

    data = request.get_json() or {}
    name = data.get("name")
    prompt_template = data.get("prompt_template")
    is_default = data.get("is_default")

    updated = update_prompt_preset(
        preset_id,
        name=name,
        prompt_template=prompt_template,
        is_default=is_default,
    )

    if not updated:
        return jsonify({"error": "No fields to update"}), 400

    updated_preset = get_prompt_preset(preset_id)

    # Reload settings if default preset was updated
    if is_default or preset.get("is_default"):
        all_overrides = get_all_config_entries()
        reload_settings(all_overrides)

    return jsonify(updated_preset)


@bp.route("/prompt-presets/<int:preset_id>", methods=["DELETE"])
def delete_prompt_preset_endpoint(preset_id):
    """Delete a prompt preset.
    ---
    delete:
      tags:
        - Profiles
      summary: Delete a prompt preset
      description: Deletes a prompt preset by ID. Cannot delete the last remaining preset.
      parameters:
        - in: path
          name: preset_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Preset deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
        404:
          description: Preset not found or cannot delete last preset
    """
    from db.translation import delete_prompt_preset

    deleted = delete_prompt_preset(preset_id)
    if not deleted:
        return jsonify({"error": "Preset not found or cannot delete last preset"}), 404
    return jsonify({"status": "deleted", "id": preset_id})
