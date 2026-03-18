"""Library integrations endpoints — Sonarr/Radarr instance management."""

import logging

from flask import jsonify, request

from routes.library import bp

logger = logging.getLogger(__name__)


@bp.route("/sonarr/instances", methods=["GET"])
def get_sonarr_instances():
    """Get all configured Sonarr instances.
    ---
    get:
      tags:
        - Library
      summary: List Sonarr instances
      description: Returns all configured Sonarr instance connections.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Sonarr instances
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      type: string
                    url:
                      type: string
    """
    from config import get_sonarr_instances

    instances = get_sonarr_instances()
    return jsonify(instances)


@bp.route("/radarr/instances", methods=["GET"])
def get_radarr_instances():
    """Get all configured Radarr instances.
    ---
    get:
      tags:
        - Library
      summary: List Radarr instances
      description: Returns all configured Radarr instance connections.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Radarr instances
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      type: string
                    url:
                      type: string
    """
    from config import get_radarr_instances

    instances = get_radarr_instances()
    return jsonify(instances)


@bp.route("/sonarr/instances/test", methods=["POST"])
def test_sonarr_instance():
    """Test connection to a Sonarr instance.
    ---
    post:
      tags:
        - Library
      summary: Test Sonarr connection
      description: Tests connectivity to a Sonarr instance using the provided URL and API key.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [url, api_key]
              properties:
                url:
                  type: string
                  description: Sonarr base URL
                api_key:
                  type: string
                  description: Sonarr API key
      responses:
        200:
          description: Connection test result
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
        400:
          description: Missing url or api_key
        500:
          description: Connection failed
    """
    data = request.get_json() or {}
    url = data.get("url")
    api_key = data.get("api_key")

    if not url or not api_key:
        return jsonify({"error": "url and api_key required"}), 400

    try:
        from sonarr_client import SonarrClient

        client = SonarrClient(url, api_key)
        is_healthy, message = client.health_check()
        return jsonify({"healthy": is_healthy, "message": message})
    except Exception as e:
        return jsonify({"healthy": False, "message": str(e)}), 500


@bp.route("/radarr/instances/test", methods=["POST"])
def test_radarr_instance():
    """Test connection to a Radarr instance.
    ---
    post:
      tags:
        - Library
      summary: Test Radarr connection
      description: Tests connectivity to a Radarr instance using the provided URL and API key.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [url, api_key]
              properties:
                url:
                  type: string
                  description: Radarr base URL
                api_key:
                  type: string
                  description: Radarr API key
      responses:
        200:
          description: Connection test result
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
        400:
          description: Missing url or api_key
        500:
          description: Connection failed
    """
    data = request.get_json() or {}
    url = data.get("url")
    api_key = data.get("api_key")

    if not url or not api_key:
        return jsonify({"error": "url and api_key required"}), 400

    try:
        from radarr_client import RadarrClient

        client = RadarrClient(url, api_key)
        is_healthy, message = client.health_check()
        return jsonify({"healthy": is_healthy, "message": message})
    except Exception as e:
        return jsonify({"healthy": False, "message": str(e)}), 500
