"""Webhook dispatcher -- sends HTTP POST with HMAC signature on event signals.

WebhookDispatcher fires outgoing HTTP requests asynchronously via ThreadPoolExecutor.
Supports HMAC-SHA256 payload signing, exponential backoff retry, and auto-disable
after consecutive failures.
"""

import hashlib
import hmac
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Auto-disable threshold: skip webhooks with this many consecutive failures
_AUTO_DISABLE_THRESHOLD = 10


def _create_webhook_session(retry_count: int = 3) -> requests.Session:
    """Create a requests Session with retry and backoff configured.

    Args:
        retry_count: Number of retry attempts (default 3).

    Returns:
        Configured requests.Session.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Sublarr-Webhook/1.0",
        "Content-Type": "application/json",
    })

    retry = Retry(
        total=retry_count,
        backoff_factor=2,  # 2s, 4s, 8s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


class WebhookDispatcher:
    """Sends HTTP POST webhooks on event signals via ThreadPoolExecutor.

    Each webhook config specifies a URL, optional HMAC secret, retry count,
    and timeout. Execution never blocks the event producer.
    """

    def __init__(self, max_workers: int = 4):
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="webhook",
        )
        logger.debug("WebhookDispatcher created with %d workers", max_workers)

    def send_webhook(self, webhook_config: dict, event_name: str, event_data: dict) -> dict:
        """Send a webhook synchronously (called inside thread pool).

        Args:
            webhook_config: Dict with url, secret, retry_count, timeout_seconds, etc.
            event_name: Name of the event that triggered the webhook.
            event_data: Event payload dict.

        Returns:
            Result dict with success, status_code, duration_ms.
        """
        url = webhook_config.get("url", "")
        secret = webhook_config.get("secret", "")
        retry_count = webhook_config.get("retry_count", 3)
        timeout = webhook_config.get("timeout_seconds", 10)

        # Build payload
        payload = {
            "event_name": event_name,
            "version": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": event_data,
        }

        body = json.dumps(payload, default=str)

        # Build headers
        headers = {
            "X-Sublarr-Event": event_name,
        }

        # HMAC-SHA256 signature if secret is configured
        if secret:
            sig = hmac.new(
                secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Sublarr-Signature"] = f"sha256={sig}"

        start = time.monotonic()

        try:
            session = _create_webhook_session(retry_count=retry_count)
            response = session.post(
                url,
                data=body,
                headers=headers,
                timeout=timeout,
            )
            session.close()

            duration_ms = (time.monotonic() - start) * 1000

            return {
                "success": response.status_code < 400,
                "status_code": response.status_code,
                "error": "" if response.status_code < 400 else f"HTTP {response.status_code}",
                "duration_ms": round(duration_ms, 1),
            }

        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            return {
                "success": False,
                "status_code": 0,
                "error": str(e),
                "duration_ms": round(duration_ms, 1),
            }

    def dispatch(self, event_name: str, event_data: dict) -> None:
        """Async dispatch: find matching webhooks and submit to thread pool.

        Matches webhooks by exact event_name or wildcard (*).
        Skips webhooks with too many consecutive failures (auto-disable).

        Args:
            event_name: Event name from the catalog.
            event_data: Event payload dict.
        """
        try:
            from db.hooks import get_webhook_configs
            # Get exact match + wildcard webhooks
            exact_configs = get_webhook_configs(event_name=event_name)
            wildcard_configs = get_webhook_configs(event_name="*")
            configs = exact_configs + wildcard_configs
        except Exception as e:
            logger.error("Failed to load webhook configs for %s: %s", event_name, e)
            return

        enabled_configs = [c for c in configs if c.get("enabled", 1)]

        for config in enabled_configs:
            # Auto-disable: skip webhooks with too many consecutive failures
            consecutive_failures = config.get("consecutive_failures", 0)
            if consecutive_failures >= _AUTO_DISABLE_THRESHOLD:
                logger.warning(
                    "Webhook '%s' auto-disabled: %d consecutive failures",
                    config.get("name", "?"), consecutive_failures,
                )
                continue

            try:
                self._pool.submit(
                    self._send_and_log, config, event_name, event_data
                )
            except Exception as e:
                logger.error(
                    "Failed to submit webhook '%s' for event %s: %s",
                    config.get("name", "?"), event_name, e,
                )

    def _send_and_log(self, config: dict, event_name: str, event_data: dict) -> None:
        """Send webhook and log the result (runs in thread pool).

        Args:
            config: Webhook config dict from DB.
            event_name: Event name.
            event_data: Event payload.
        """
        webhook_id = config.get("id")

        try:
            result = self.send_webhook(config, event_name, event_data)

            # Log execution to DB
            from db.hooks import log_hook_execution, update_webhook_trigger_stats
            log_hook_execution(
                webhook_id=webhook_id,
                event_name=event_name,
                hook_type="webhook",
                success=result["success"],
                status_code=result.get("status_code"),
                error=result.get("error", ""),
                duration_ms=result.get("duration_ms", 0),
            )
            update_webhook_trigger_stats(
                webhook_id,
                result["success"],
                status_code=result.get("status_code", 0),
                error=result.get("error", ""),
            )

            if result["success"]:
                logger.debug(
                    "Webhook '%s' sent for %s -> %d (%.0fms)",
                    config.get("name", "?"), event_name,
                    result.get("status_code", 0), result.get("duration_ms", 0),
                )
            else:
                logger.warning(
                    "Webhook '%s' failed for %s: %s",
                    config.get("name", "?"), event_name, result.get("error", "unknown"),
                )

        except Exception as e:
            logger.error(
                "Unexpected error sending webhook '%s' for %s: %s",
                config.get("name", "?"), event_name, e,
            )

    def shutdown(self) -> None:
        """Shutdown the thread pool gracefully."""
        self._pool.shutdown(wait=False)
        logger.info("WebhookDispatcher shut down")


def init_webhook_subscribers(dispatcher: WebhookDispatcher) -> None:
    """Subscribe the WebhookDispatcher to all catalog events.

    Creates a closure for each event that calls dispatcher.dispatch with
    the correct event_name.

    Args:
        dispatcher: WebhookDispatcher instance to register.
    """
    from events.catalog import EVENT_CATALOG

    def _make_webhook_handler(event_name: str):
        """Create a handler that captures event_name via closure."""
        def _handler(sender, data=None, **kwargs):
            dispatcher.dispatch(event_name, data or {})
        return _handler

    count = 0
    for name, entry in EVENT_CATALOG.items():
        # Skip hook_executed to avoid infinite recursion
        if name == "hook_executed":
            continue
        handler = _make_webhook_handler(name)
        entry["signal"].connect(handler, weak=False)
        count += 1

    logger.info("WebhookDispatcher subscribed to %d events", count)
