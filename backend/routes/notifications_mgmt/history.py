"""Notification history endpoints: list (paginated), resend, clear."""

from __future__ import annotations

from flask import jsonify, request

from routes.notifications_mgmt import bp


@bp.route("/history", methods=["GET"])
def list_history():
    """Get paginated notification history.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: Get notification history
      parameters:
        - in: query
          name: page
          schema:
            type: integer
            default: 1
        - in: query
          name: per_page
          schema:
            type: integer
            default: 50
        - in: query
          name: event_type
          schema:
            type: string
      responses:
        200:
          description: Paginated notification history
    """
    from db.repositories.notifications import NotificationRepository

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    event_type = request.args.get("event_type")

    repo = NotificationRepository()
    result = repo.get_history(page=page, per_page=per_page, event_type=event_type)
    return jsonify(result)


@bp.route("/history/<int:notification_id>/resend", methods=["POST"])
def resend_notification(notification_id):
    """Re-send a historical notification.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: Re-send notification
      parameters:
        - in: path
          name: notification_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Notification re-sent
        404:
          description: Not found
    """
    from db.repositories.notifications import NotificationRepository
    from notifier import send_notification

    repo = NotificationRepository()
    notification = repo.get_notification(notification_id)
    if notification is None:
        return jsonify({"error": "Notification not found"}), 404

    # Re-send using original title/body and event_type
    send_notification(
        title=notification["title"],
        body=notification["body"],
        event_type=notification["event_type"],
        is_manual=True,
    )
    return jsonify({"success": True, "message": "Notification re-sent"})


@bp.route("/history", methods=["DELETE"])
def clear_history():
    """Clear notification history.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: Clear notification history
      parameters:
        - in: query
          name: before_date
          schema:
            type: string
          description: Optional ISO date to clear history before
      responses:
        200:
          description: History cleared
    """
    from db.repositories.notifications import NotificationRepository

    before_date = request.args.get("before_date")
    repo = NotificationRepository()
    count = repo.clear_history(before_date=before_date)
    return jsonify({"success": True, "deleted": count})
