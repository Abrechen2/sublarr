"""Glossary endpoints: list / create / update / delete / TSV export."""

from __future__ import annotations

from flask import Response, jsonify, request

from routes.profiles import bp
from services.profile_service import (
    ProfileNotFoundError,
    ProfileValidationError,
    create_glossary,
    delete_glossary,
    export_glossary_as_tsv,
    update_glossary,
)


@bp.route("/glossary", methods=["GET"])
def list_glossary():
    """Get glossary entries for a series or global glossary.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: List glossary entries
      description: >
        Returns glossary entries. When series_id is provided, returns per-series
        entries. When omitted, returns global glossary entries.
        Optionally filter by search query.
      parameters:
        - in: query
          name: series_id
          schema:
            type: integer
          description: Series ID for per-series entries. Omit for global glossary.
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
                    nullable: true
    """
    from db.translation import get_glossary_entries, search_glossary_terms

    series_id = request.args.get("series_id", type=int)
    query = request.args.get("query", "").strip()

    if query:
        entries = search_glossary_terms(series_id, query)
    else:
        entries = get_glossary_entries(series_id)

    return jsonify({"entries": entries, "series_id": series_id})


@bp.route("/glossary", methods=["POST"])
def create_glossary_entry():
    """Create a new glossary entry (per-series or global).
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Create a glossary entry
      description: >
        Adds a new source-to-target term mapping for translation consistency.
        Omit or set series_id to null for a global glossary entry.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - source_term
                - target_term
              properties:
                series_id:
                  type: integer
                  nullable: true
                  description: Omit or null for global glossary entry
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
    try:
        entry = create_glossary(request.get_json() or {})
    except ProfileValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(entry), 201


@bp.route("/glossary/<int:entry_id>", methods=["PUT"])
def update_glossary_entry_endpoint(entry_id):
    """Update a glossary entry.
    ---
    put:
      security:
        - apiKeyAuth: []
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
    try:
        entry = update_glossary(entry_id, request.get_json() or {})
    except ProfileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ProfileValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(entry)


@bp.route("/glossary/<int:entry_id>", methods=["DELETE"])
def delete_glossary_entry_endpoint(entry_id):
    """Delete a glossary entry.
    ---
    delete:
      security:
        - apiKeyAuth: []
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
    try:
        result = delete_glossary(entry_id)
    except ProfileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify(result)


@bp.route("/glossary/export", methods=["GET"])
def export_glossary_tsv():
    """Export glossary entries as a TSV file download.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Export glossary as TSV
      description: >
        Downloads all glossary entries as a tab-separated values file.
        When series_id is provided, exports only entries for that series.
        When omitted, exports the global glossary.
      parameters:
        - in: query
          name: series_id
          schema:
            type: integer
          description: Series ID for per-series entries. Omit for global glossary.
      responses:
        200:
          description: TSV file download
          content:
            text/tab-separated-values:
              schema:
                type: string
    """
    series_id = request.args.get("series_id", type=int)
    tsv_content, filename = export_glossary_as_tsv(series_id)

    return Response(
        tsv_content,
        status=200,
        mimetype="text/tab-separated-values; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
