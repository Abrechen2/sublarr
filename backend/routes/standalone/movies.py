"""Standalone movie endpoints: list, detail, poster, delete."""

from __future__ import annotations

import logging

from flask import jsonify, redirect, send_file

from extensions import limiter
from routes.standalone import bp

logger = logging.getLogger(__name__)


@bp.route("/movies", methods=["GET"])
def list_movies():
    """List all standalone movies with wanted status.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: List standalone movies
      description: Returns all standalone movies with wanted count information.
      responses:
        200:
          description: List of standalone movies
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
        500:
          description: Server error
    """
    from db.standalone import get_standalone_movies
    from services.standalone_manager import enrich_movie_list

    try:
        movies = get_standalone_movies()
        return jsonify(enrich_movie_list(movies))
    except Exception as e:
        logger.error("Failed to list standalone movies: %s", e)
        return jsonify({"error": "Failed to list standalone movies"}), 500


@bp.route("/movies/<int:movie_id>", methods=["GET"])
def get_movie(movie_id):
    """Get a single standalone movie by ID.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Get standalone movie
      description: Returns a single standalone movie by ID with wanted count.
      parameters:
        - in: path
          name: movie_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Movie found
          content:
            application/json:
              schema:
                type: object
        404:
          description: Movie not found
        500:
          description: Server error
    """
    from db.standalone import get_standalone_movies
    from services.standalone_manager import enrich_movie_detail, get_radarr_movie_fallback

    movie = get_standalone_movies(movie_id)
    if not movie:
        fallback = get_radarr_movie_fallback(movie_id)
        if fallback:
            return jsonify(fallback)
        return jsonify({"error": "Movie not found"}), 404

    try:
        return jsonify(enrich_movie_detail(movie, movie_id))
    except Exception as e:
        logger.error("Failed to get movie %d: %s", movie_id, e)
        return jsonify({"error": "Failed to get movie"}), 500


@bp.route("/movies/<int:movie_id>/poster", methods=["GET"])
@limiter.limit("120/minute")
def movie_poster(movie_id):
    """Serve the local poster image for a standalone movie."""
    from db.standalone import get_standalone_movies
    from services.standalone_manager import resolve_poster_path

    movie = get_standalone_movies(movie_id)
    if not movie:
        return jsonify({"error": "Movie not found"}), 404

    poster_path, error, status = resolve_poster_path(movie, folder_key="file_path", use_parent=True)
    if error:
        return jsonify({"error": error}), status

    if poster_path.startswith(("http://", "https://")):
        return redirect(poster_path)

    try:
        return send_file(poster_path)
    except Exception as e:
        logger.error("Failed to serve poster for movie %d: %s", movie_id, e)
        return jsonify({"error": "Failed to serve poster"}), 500


@bp.route("/movies/<int:movie_id>", methods=["DELETE"])
def delete_movie(movie_id):
    """Delete a standalone movie and its wanted items.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Delete standalone movie
      description: Deletes a standalone movie and cascades to remove associated wanted items.
      parameters:
        - in: path
          name: movie_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Movie deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
        404:
          description: Movie not found
        500:
          description: Server error
    """
    from db.standalone import get_standalone_movies
    from services.standalone_manager import delete_movie_cascade

    movie = get_standalone_movies(movie_id)
    if not movie:
        return jsonify({"error": "Movie not found"}), 404

    try:
        delete_movie_cascade(movie_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to delete standalone movie %d: %s", movie_id, e)
        return jsonify({"error": "Failed to delete standalone movie"}), 500
