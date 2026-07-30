"""Scoring weights, modifiers, and presets endpoints."""

from flask import jsonify, request

from cache_response import cached_get, invalidate_response_cache
from routes.hooks import bp

# ---- Scoring Weight endpoints ------------------------------------------------


@bp.route("/scoring/weights", methods=["GET"])
@cached_get(ttl_seconds=60)
def get_weights():
    """Return all scoring weights (episode + movie) merged with defaults.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Get scoring weights
      description: Returns current scoring weights for episode and movie subtitle matching, along with the default values.
      responses:
        200:
          description: Scoring weights
          content:
            application/json:
              schema:
                type: object
                properties:
                  episode:
                    type: object
                    additionalProperties:
                      type: number
                  movie:
                    type: object
                    additionalProperties:
                      type: number
                  defaults:
                    type: object
                    properties:
                      episode:
                        type: object
                        additionalProperties:
                          type: number
                      movie:
                        type: object
                        additionalProperties:
                          type: number
    """
    from db.scoring import _DEFAULT_EPISODE_WEIGHTS, _DEFAULT_MOVIE_WEIGHTS, get_all_scoring_weights

    weights = get_all_scoring_weights()
    return jsonify(
        {
            "episode": weights["episode"],
            "movie": weights["movie"],
            "defaults": {
                "episode": _DEFAULT_EPISODE_WEIGHTS,
                "movie": _DEFAULT_MOVIE_WEIGHTS,
            },
        }
    )


@bp.route("/scoring/weights", methods=["PUT"])
def update_weights():
    """Update scoring weights for episode and/or movie types.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Update scoring weights
      description: Updates scoring weights for episode and/or movie subtitle matching. Invalidates the scoring cache.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                episode:
                  type: object
                  additionalProperties:
                    type: number
                movie:
                  type: object
                  additionalProperties:
                    type: number
      responses:
        200:
          description: Updated scoring weights
          content:
            application/json:
              schema:
                type: object
    """
    from db.scoring import get_all_scoring_weights, set_scoring_weights
    from providers.base import invalidate_scoring_cache

    data = request.get_json(silent=True) or {}

    if "episode" in data and isinstance(data["episode"], dict):
        set_scoring_weights("episode", data["episode"])
    if "movie" in data and isinstance(data["movie"], dict):
        set_scoring_weights("movie", data["movie"])

    invalidate_scoring_cache()
    invalidate_response_cache()

    weights = get_all_scoring_weights()
    from db.scoring import _DEFAULT_EPISODE_WEIGHTS, _DEFAULT_MOVIE_WEIGHTS

    return jsonify(
        {
            "episode": weights["episode"],
            "movie": weights["movie"],
            "defaults": {
                "episode": _DEFAULT_EPISODE_WEIGHTS,
                "movie": _DEFAULT_MOVIE_WEIGHTS,
            },
        }
    )


@bp.route("/scoring/weights", methods=["DELETE"])
def reset_weights():
    """Reset all scoring weights to defaults.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Reset scoring weights
      description: Resets all scoring weights to their default values and invalidates the scoring cache.
      responses:
        204:
          description: Weights reset to defaults
    """
    from db.scoring import reset_scoring_weights
    from providers.base import invalidate_scoring_cache

    reset_scoring_weights()
    invalidate_scoring_cache()
    invalidate_response_cache()
    return "", 204


# ---- Provider Modifier endpoints ---------------------------------------------


@bp.route("/scoring/modifiers", methods=["GET"])
@cached_get(ttl_seconds=60)
def get_modifiers():
    """Return all provider score modifiers.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Get provider score modifiers
      description: Returns all provider-specific score modifiers (-100 to +100) that adjust subtitle match scoring.
      responses:
        200:
          description: Provider modifiers map
          content:
            application/json:
              schema:
                type: object
                additionalProperties:
                  type: integer
    """
    from db.scoring import get_all_provider_modifiers

    modifiers = get_all_provider_modifiers()
    return jsonify(modifiers)


@bp.route("/scoring/modifiers", methods=["PUT"])
def update_modifiers():
    """Update provider modifiers from a dict of {provider_name: modifier}.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Update provider score modifiers
      description: Sets score modifiers for one or more providers. Invalidates the scoring cache.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties:
                type: integer
              example:
                animetosho: 20
                opensubtitles: -10
      responses:
        200:
          description: Updated modifiers
          content:
            application/json:
              schema:
                type: object
                additionalProperties:
                  type: integer
    """
    from db.scoring import get_all_provider_modifiers, set_provider_modifier
    from providers.base import invalidate_scoring_cache

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Payload must be a JSON object"}), 400

    # Cap key length so a long string can't DoS the scoring table; the
    # int() cast must be guarded so a non-numeric value gets a 400 instead
    # of crashing into a 500 inside the loop.
    for provider_name, modifier in data.items():
        if not isinstance(provider_name, str) or len(provider_name) > 64:
            return jsonify({"error": "provider name must be a string ≤ 64 chars"}), 400
        try:
            mod_int = int(modifier)
        except (TypeError, ValueError):
            return jsonify({"error": f"modifier for {provider_name} must be an integer"}), 400
        set_provider_modifier(provider_name, max(-100, min(mod_int, 100)))

    invalidate_scoring_cache()
    invalidate_response_cache()

    modifiers = get_all_provider_modifiers()
    return jsonify(modifiers)


@bp.route("/scoring/modifiers/<provider_name>", methods=["DELETE"])
def delete_modifier(provider_name):
    """Delete a single provider modifier.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Delete a provider score modifier
      description: Removes the score modifier for a specific provider, reverting it to the default (0).
      parameters:
        - in: path
          name: provider_name
          required: true
          schema:
            type: string
      responses:
        204:
          description: Modifier deleted
    """
    from db.scoring import delete_provider_modifier
    from providers.base import invalidate_scoring_cache

    delete_provider_modifier(provider_name)
    invalidate_scoring_cache()
    invalidate_response_cache()
    return "", 204


# ---- Scoring preset endpoints ------------------------------------------------


@bp.route("/scoring/presets", methods=["GET"])
@cached_get(ttl_seconds=60)
def list_presets():
    """Return metadata for all bundled scoring presets.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: List scoring presets
      description: Returns name, description, and type of all bundled scoring presets.
      responses:
        200:
          description: List of preset metadata
    """
    from scoring_presets import load_bundled_presets

    return jsonify(load_bundled_presets())


@bp.route("/scoring/presets/<name>", methods=["GET"])
@cached_get(ttl_seconds=60)
def get_preset(name: str):
    """Return a single bundled preset by name.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Get scoring preset
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
      responses:
        200:
          description: Full preset data
        404:
          description: Preset not found
    """
    from scoring_presets import get_bundled_preset

    preset = get_bundled_preset(name)
    if preset is None:
        return jsonify({"error": f"Preset '{name}' not found"}), 404
    return jsonify(preset)


@bp.route("/scoring/presets/import", methods=["POST"])
def import_preset():
    """Import a scoring preset (bundled or custom JSON) and apply it.

    Accepts a preset JSON body. Writes weights and provider modifiers to DB.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Import scoring preset
      description: Applies a preset's scoring weights and provider modifiers. Partial presets are supported.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                weights:
                  type: object
                provider_modifiers:
                  type: object
      responses:
        200:
          description: Preset applied
        400:
          description: Invalid preset data
    """
    from db.scoring import set_provider_modifier, set_scoring_weights
    from providers.base import invalidate_scoring_cache
    from scoring_presets import validate_preset

    data = request.get_json(silent=True)
    if not data or not validate_preset(data):
        return jsonify({"error": "Invalid preset data"}), 400

    applied: dict = {"weights": {}, "provider_modifiers": {}}

    weights = data.get("weights", {})
    for score_type, w in weights.items():
        if w:
            set_scoring_weights(score_type, w)
            applied["weights"][score_type] = w

    modifiers = data.get("provider_modifiers", {})
    for provider_name, modifier in modifiers.items():
        set_provider_modifier(provider_name, int(modifier))
        applied["provider_modifiers"][provider_name] = modifier

    invalidate_scoring_cache()
    invalidate_response_cache()

    return jsonify({"status": "ok", "preset": data.get("name", "custom"), "applied": applied})


# ---- Penalty Rule endpoints (Plan B4) ----------------------------------------


@bp.route("/scoring/penalty-rules", methods=["GET"])
@cached_get(ttl_seconds=60)
def list_penalty_rules():
    """Return all registered penalty rules with their metadata and current weight.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: List penalty rules
      description: >-
        Returns every registered penalty rule (15 in the default registry)
        together with its stable ``rule_id``, ``label``, ``description``,
        ``default_weight`` and ``current_weight``. The current weight is the
        DB override when present, otherwise the rule's default.
      responses:
        200:
          description: Penalty rules list
          content:
            application/json:
              schema:
                type: object
                properties:
                  rules:
                    type: array
                    items:
                      type: object
                      properties:
                        rule_id: { type: string }
                        label: { type: string }
                        description: { type: string }
                        default_weight: { type: integer }
                        current_weight: { type: integer }
    """
    from db.scoring import get_penalty_rule_weights
    from wanted_search.penalty_rules import _RULE_REGISTRY

    overrides = get_penalty_rule_weights()
    rules = [
        {
            "rule_id": cls.rule_id,
            "label": cls.label,
            "description": cls.description,
            "default_weight": cls.default_weight,
            "current_weight": overrides.get(cls.rule_id, cls.default_weight),
        }
        for cls in _RULE_REGISTRY
    ]
    return jsonify({"rules": rules})


@bp.route("/scoring/penalty-rules/<rule_id>", methods=["PUT"])
def update_penalty_rule(rule_id):
    """Update a penalty rule's weight override.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Update a penalty rule weight
      description: >-
        Sets the weight override for a single penalty rule. Writing 0
        persists the row but disables the rule (the pipeline skips
        zero-weight rules). Invalidates the scoring cache.
      parameters:
        - in: path
          name: rule_id
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                weight:
                  type: integer
      responses:
        200:
          description: Weight updated
        400:
          description: Weight is not an integer
        404:
          description: Unknown rule_id
    """
    from db.scoring import set_penalty_rule_weight
    from providers.base import invalidate_scoring_cache
    from wanted_search.penalty_rules import _RULE_REGISTRY

    if not any(cls.rule_id == rule_id for cls in _RULE_REGISTRY):
        return jsonify({"error": "unknown rule_id", "rule_id": rule_id}), 404

    data = request.get_json(silent=True) or {}
    try:
        weight = int(data.get("weight", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "weight must be an integer"}), 400

    set_penalty_rule_weight(rule_id, weight)
    invalidate_scoring_cache()
    invalidate_response_cache()
    return jsonify({"rule_id": rule_id, "weight": weight})


# ---- Release-group tier endpoints --------------------------------------------


@bp.route("/scoring/release-group-tiers", methods=["GET"])
def get_release_group_tiers():
    """Return the global release-group tier ranking.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Get release-group tiers
      description: >-
        Returns the ordered global release-group tier list (best first) and
        the per-tier step weight. A result matching the group at index ``i``
        of ``N`` tiers earns ``step * (N - i)`` bonus points in wanted-search
        scoring.
      responses:
        200:
          description: Tier configuration
          content:
            application/json:
              schema:
                type: object
                properties:
                  tiers:
                    type: array
                    items: { type: string }
                  step:
                    type: integer
    """
    from services.release_group_tiers import get_tier_config

    return jsonify(get_tier_config())


@bp.route("/scoring/release-group-tiers", methods=["PUT"])
def update_release_group_tiers():
    """Replace the global release-group tier ranking.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Events
      summary: Update release-group tiers
      description: >-
        Replaces the ordered tier list and per-tier step weight. Entries are
        trimmed, empties dropped, and duplicates removed case-insensitively
        (first occurrence wins). An empty list disables tier scoring.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                tiers:
                  type: array
                  items: { type: string }
                step:
                  type: integer
      responses:
        200:
          description: Stored tier configuration
        400:
          description: Invalid tiers or step
    """
    from services.release_group_tiers import DEFAULT_STEP, set_tier_config

    data = request.get_json(silent=True) or {}
    try:
        step = data.get("step", DEFAULT_STEP)
        if isinstance(step, str) and step.strip().lstrip("-").isdigit():
            step = int(step)
        config = set_tier_config(data.get("tiers", []), step)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    invalidate_response_cache()
    return jsonify(config)
