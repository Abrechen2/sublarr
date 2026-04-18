"""System notification routes — /notifications/test, /notifications/status.

These routes send/query Apprise-based system notifications. Notification-template
CRUD, quiet-hours, and history live in routes/notifications_mgmt/ (a separate
Blueprint).
"""

import logging

from flask import jsonify, request

from routes.system import bp

logger = logging.getLogger(__name__)


@bp.route("/notifications/test", methods=["POST"])
def notification_test():
    """Send a test notification.
    ---
    post:
      tags:
        - System
      summary: Send test notification
      description: Sends a test notification via Apprise. Optionally test a specific notification URL.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                url:
                  type: string
                  description: Optional specific Apprise URL to test
      responses:
        200:
          description: Notification sent successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  message:
                    type: string
        500:
          description: Notification failed
    """
    from notifier import test_notification

    data = request.get_json() or {}
    url = data.get("url")  # Optional: test a specific URL
    result = test_notification(url=url)
    status_code = 200 if result["success"] else 500
    return jsonify(result), status_code


@bp.route("/notifications/status", methods=["GET"])
def notification_status():
    """Get notification configuration status.
    ---
    get:
      tags:
        - System
      summary: Get notification status
      description: Returns whether notifications are configured and the count of notification URLs.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Notification configuration status
          content:
            application/json:
              schema:
                type: object
                properties:
                  configured:
                    type: boolean
                  url_count:
                    type: integer
    """
    from notifier import get_notification_status

    return jsonify(get_notification_status())
