"""Scoring weights, modifiers, and presets endpoints."""

from flask import jsonify, request

from routes.hooks import bp

# ---- Scoring Weight endpoints ------------------------------------------------


@bp.route("/scoring/weights", methods=["GET"])
def get_weights():
    """Return all scoring weights (episode + movie) merged with defaults.
    ---
    get:
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
    return "", 204


# ---- Provider Modifier endpoints ---------------------------------------------


@bp.route("/scoring/modifiers", methods=["GET"])
def get_modifiers():
    """Return all provider score modifiers.
    ---
    get:
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

    for provider_name, modifier in data.items():
        set_provider_modifier(provider_name, int(modifier))

    invalidate_scoring_cache()

    modifiers = get_all_provider_modifiers()
    return jsonify(modifiers)


@bp.route("/scoring/modifiers/<provider_name>", methods=["DELETE"])
def delete_modifier(provider_name):
    """Delete a single provider modifier.
    ---
    delete:
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
    return "", 204


# ---- Scoring preset endpoints ------------------------------------------------


@bp.route("/scoring/presets", methods=["GET"])
def list_presets():
    """Return metadata for all bundled scoring presets.
    ---
    get:
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
def get_preset(name: str):
    """Return a single bundled preset by name.
    ---
    get:
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

    return jsonify({"status": "ok", "preset": data.get("name", "custom"), "applied": applied})
