"""Hook log endpoints."""

from flask import jsonify, request

from routes.hooks import bp

# ---- Hook Log endpoints ------------------------------------------------------


@bp.route("/hooks/logs", methods=["GET"])
def list_hook_logs():
    """List hook execution logs with optional filters.
    ---
    get:
      tags:
        - Events
      summary: List hook execution logs
      description: Returns hook and webhook execution logs with optional filtering by hook or webhook ID.
      parameters:
        - in: query
          name: hook_id
          schema:
            type: integer
          description: Filter logs by hook ID
        - in: query
          name: webhook_id
          schema:
            type: integer
          description: Filter logs by webhook ID
        - in: query
          name: limit
          schema:
            type: integer
            default: 50
      responses:
        200:
          description: List of execution logs
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
    """
    from db.hooks import get_hook_logs

    hook_id = request.args.get("hook_id", type=int)
    webhook_id = request.args.get("webhook_id", type=int)
    limit = request.args.get("limit", 50, type=int)

    logs = get_hook_logs(hook_id=hook_id, webhook_id=webhook_id, limit=limit)
    return jsonify(logs)


@bp.route("/hooks/logs", methods=["DELETE"])
def clear_logs():
    """Clear all hook logs.
    ---
    delete:
      tags:
        - Events
      summary: Clear hook logs
      description: Deletes all hook and webhook execution logs.
      responses:
        204:
          description: Logs cleared
    """
    from db.hooks import clear_hook_logs

    clear_hook_logs()
    return "", 204
