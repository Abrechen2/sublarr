"""Notification module using Apprise.

Supports any Apprise-compatible URL (Pushover, Discord, Telegram, Gotify, etc.).
Event types can be individually toggled via config settings.
Templates are rendered via Jinja2 SandboxedEnvironment before sending.
Quiet hours suppress notifications during configured time windows.
All sent notifications are logged to history.
"""

import json
import logging
import threading

logger = logging.getLogger(__name__)

_apprise_instance = None
_sandbox_env = None
_apprise_lock = threading.Lock()


def _get_apprise():
    """Get or create the singleton Apprise instance (thread-safe)."""
    global _apprise_instance
    # Fast path: already initialized
    if _apprise_instance is not None:
        return _apprise_instance

    with _apprise_lock:
        # Double-checked locking: re-test under the lock
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


def _get_sandbox_env():
    """Get or create the singleton Jinja2 SandboxedEnvironment."""
    global _sandbox_env
    if _sandbox_env is not None:
        return _sandbox_env

    try:
        from jinja2.sandbox import SandboxedEnvironment

        _sandbox_env = SandboxedEnvironment()
        return _sandbox_env
    except ImportError:
        logger.warning("jinja2 not available — template rendering disabled")
        return None


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
    """Reset the cached Apprise instance (call on config change).

    Thread-safe: uses _apprise_lock to prevent a concurrent call to
    _get_apprise() from reading the old instance after invalidation.
    """
    global _apprise_instance
    with _apprise_lock:
        _apprise_instance = None
    logger.debug("Notifier cache invalidated")


def render_template(template_str: str, variables: dict) -> str:
    """Render a Jinja2 template string with the given variables.

    Uses SandboxedEnvironment to prevent template injection.

    Args:
        template_str: Jinja2 template string.
        variables: Dict of template variables.

    Returns:
        Rendered string.
    """
    if not template_str:
        return ""

    env = _get_sandbox_env()
    if env is None:
        return template_str

    try:
        tmpl = env.from_string(template_str)
        return tmpl.render(**variables)
    except Exception as e:
        logger.warning("Template rendering failed: %s", e)
        return template_str


def get_sample_payload(event_type: str) -> dict:
    """Return sample data for a given EVENT_CATALOG event type.

    Generates representative sample values based on the event's payload_keys.

    Args:
        event_type: Event type name from EVENT_CATALOG.

    Returns:
        Dict mapping payload keys to sample values.
    """
    try:
        from events.catalog import EVENT_CATALOG
    except ImportError:
        return {}

    meta = EVENT_CATALOG.get(event_type)
    if meta is None:
        return {}

    # Generate sample values based on key names
    sample_values = {
        "provider_name": "AnimeTosho",
        "language": "de",
        "format": "ass",
        "score": 359,
        "series_title": "Demon Slayer",
        "season": 1,
        "episode": 5,
        "movie_title": "Your Name",
        "job_id": "abc12345",
        "source_language": "en",
        "target_language": "de",
        "backend_name": "ollama",
        "duration_ms": 12500,
        "error": "Connection timeout",
        "error_type": "NetworkError",
        "result_count": 15,
        "best_score": 359,
        "total_items": 42,
        "new_items": 8,
        "removed_items": 2,
        "item_id": 1,
        "title": "Demon Slayer S01E05",
        "season_episode": "S01E05",
        "status": "completed",
        "old_format": "srt",
        "new_format": "ass",
        "old_score": 90,
        "new_score": 359,
        "total": 10,
        "succeeded": 8,
        "failed": 1,
        "skipped": 1,
        "source": "sonarr",
        "event_type": event_type,
        "changed_keys": ["notification_urls_json"],
        "detected_language": "ja",
        "segment_count": 245,
        "duration_seconds": 1440,
        "processing_time_ms": 35000,
        "hook_id": 1,
        "webhook_id": 1,
        "hook_type": "webhook",
        "event_name": event_type,
        "success": True,
        "folders_scanned": 5,
        "files_found": 120,
        "wanted_added": 15,
        "path": "/media/anime/demon-slayer/S01E05.mkv",
        "type": "episode",
        "wanted": True,
    }

    payload_keys = meta.get("payload_keys", [])
    return {key: sample_values.get(key, f"sample_{key}") for key in payload_keys}


def send_notification(title: str, body: str, event_type: str, is_manual: bool = False):
    """Send a notification if the event type is enabled.

    Checks quiet hours, applies template rendering if a matching template exists,
    and logs the notification to history.

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

    # Check quiet hours
    template_id_used = None
    try:
        from db.repositories.notifications import NotificationRepository

        repo = NotificationRepository()

        if repo.is_quiet_hours(event_type):
            logger.info(
                "Notification suppressed by quiet hours: [%s] %s",
                event_type,
                title,
            )
            return

        # Look up matching template
        template = repo.find_template_for_event(event_type)
        if template and template.get("enabled"):
            template_id_used = template["id"]
            # Build variables from event context
            variables = get_sample_payload(event_type)
            variables["title"] = title
            variables["body"] = body
            variables["event_type"] = event_type

            rendered_title = render_template(template["title_template"], variables)
            rendered_body = render_template(template["body_template"], variables)

            # Only use rendered versions if non-empty
            if rendered_title:
                title = rendered_title
            if rendered_body:
                body = rendered_body
    except Exception as e:
        # Template/quiet hours errors should not prevent notification sending
        logger.warning("Template/quiet hours check failed: %s", e)

    ap = _get_apprise()
    if not ap:
        return

    status = "sent"
    error_msg = ""

    try:
        import apprise

        notify_type = apprise.NotifyType.INFO
        if event_type == "error":
            notify_type = apprise.NotifyType.FAILURE

        ap.notify(title=title, body=body, notify_type=notify_type)
        logger.info("Notification sent: [%s] %s", event_type, title)
    except Exception as e:
        status = "failed"
        error_msg = str(e)
        logger.warning("Failed to send notification: %s", e)

    # Log to notification history
    try:
        from db.repositories.notifications import NotificationRepository

        hist_repo = NotificationRepository()
        hist_repo.log_notification(
            event_type=event_type,
            title=title,
            body=body,
            template_id=template_id_used,
            status=status,
            error=error_msg,
        )
    except Exception as e:
        logger.warning("Failed to log notification to history: %s", e)


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
