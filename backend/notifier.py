"""Notification module using Apprise.

Supports any Apprise-compatible URL (Pushover, Discord, Telegram, Gotify, etc.).
Event types can be individually toggled via config settings.
"""

import json
import logging

logger = logging.getLogger(__name__)

_apprise_instance = None


def _get_apprise():
    """Get or create the singleton Apprise instance."""
    global _apprise_instance
    if _apprise_instance is not None:
        return _apprise_instance

    try:
        import apprise
    except ImportError:
        logger.warning("Apprise not installed — notifications disabled")
        return None

    from config import get_settings
    settings = get_settings()
    urls = _parse_notification_urls(settings.notification_urls_json)

    if not urls:
        return None

    ap = apprise.Apprise()
    for url in urls:
        ap.add(url)

    _apprise_instance = ap
    return ap


def _parse_notification_urls(urls_json: str) -> list[str]:
    """Parse notification URLs from JSON array or newline-separated string."""
    if not urls_json or not urls_json.strip():
        return []

    # Try JSON array first
    try:
        parsed = json.loads(urls_json)
        if isinstance(parsed, list):
            return [u.strip() for u in parsed if u and u.strip()]
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: newline-separated
    return [u.strip() for u in urls_json.strip().splitlines() if u.strip()]


def invalidate_notifier():
    """Reset the cached Apprise instance (call on config change)."""
    global _apprise_instance
    _apprise_instance = None
    logger.debug("Notifier cache invalidated")


def send_notification(title: str, body: str, event_type: str, is_manual: bool = False):
    """Send a notification if the event type is enabled.

    Args:
        title: Notification title
        body: Notification body text
        event_type: One of 'download', 'upgrade', 'batch_complete', 'error'
        is_manual: Whether this was triggered by a manual action
    """
    from config import get_settings
    settings = get_settings()

    # Check if manual notifications are allowed
    if is_manual and not settings.notify_manual_actions:
        return

    # Check event-specific toggles
    event_toggles = {
        "download": settings.notify_on_download,
        "upgrade": settings.notify_on_upgrade,
        "batch_complete": settings.notify_on_batch_complete,
        "error": settings.notify_on_error,
    }

    if not event_toggles.get(event_type, False):
        logger.debug("Notification suppressed for event_type=%s", event_type)
        return

    ap = _get_apprise()
    if not ap:
        return

    try:
        import apprise
        notify_type = apprise.NotifyType.INFO
        if event_type == "error":
            notify_type = apprise.NotifyType.FAILURE

        ap.notify(title=title, body=body, notify_type=notify_type)
        logger.info("Notification sent: [%s] %s", event_type, title)
    except Exception as e:
        logger.warning("Failed to send notification: %s", e)


def test_notification(url: str = None) -> dict:
    """Send a test notification.

    Args:
        url: Optional single URL to test. If None, tests all configured URLs.

    Returns:
        dict with 'success' and 'message' keys
    """
    try:
        import apprise
    except ImportError:
        return {"success": False, "message": "Apprise not installed"}

    if url:
        ap = apprise.Apprise()
        ap.add(url)
    else:
        ap = _get_apprise()
        if not ap:
            return {"success": False, "message": "No notification URLs configured"}

    try:
        result = ap.notify(
            title="Sublarr Test Notification",
            body="If you see this, notifications are working correctly.",
            notify_type=apprise.NotifyType.INFO,
        )
        if result:
            return {"success": True, "message": "Test notification sent successfully"}
        else:
            return {"success": False, "message": "Notification delivery failed"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_notification_status() -> dict:
    """Get notification configuration status."""
    from config import get_settings
    settings = get_settings()
    urls = _parse_notification_urls(settings.notification_urls_json)

    return {
        "configured": len(urls) > 0,
        "url_count": len(urls),
        "events": {
            "download": settings.notify_on_download,
            "upgrade": settings.notify_on_upgrade,
            "batch_complete": settings.notify_on_batch_complete,
            "error": settings.notify_on_error,
            "manual_actions": settings.notify_manual_actions,
        },
    }
