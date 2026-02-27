"""Event system package — blinker signal bus with SocketIO bridge.

Provides:
    - init_event_system(app): Registers SocketIO bridge subscribers for
      every event in the catalog so WebSocket clients receive all events.
    - emit_event(event_name, data): Primary API for emitting events from
      any module. Looks up the signal and sends it on the blinker bus.
"""

import logging

from events.catalog import CATALOG_VERSION, EVENT_CATALOG

logger = logging.getLogger(__name__)


def init_event_system(app):
    """Register a SocketIO bridge for every event in the catalog.

    When any blinker signal fires, the bridge emits the same event_name
    and data dict to all connected WebSocket clients. This preserves
    backward compatibility with the existing frontend that listens on
    Socket.IO events.

    Args:
        app: The Flask application instance (used for context if needed).
    """
    from extensions import socketio

    def _make_bridge(event_name: str):
        """Create a bridge subscriber that captures event_name via closure."""
        def _bridge(sender, data=None, **kwargs):
            payload = data if data is not None else {}
            logger.debug("Event bridge: %s -> WebSocket (%d keys)",
                         event_name, len(payload) if isinstance(payload, dict) else 0)
            try:
                socketio.emit(event_name, payload)
            except Exception as exc:
                logger.warning("Failed to bridge event %s to WebSocket: %s",
                               event_name, exc)
        return _bridge

    for name, entry in EVENT_CATALOG.items():
        bridge_fn = _make_bridge(name)
        entry["signal"].connect(bridge_fn, weak=False)

    logger.info("Event system initialized: %d events, catalog v%d",
                len(EVENT_CATALOG), CATALOG_VERSION)


def emit_event(event_name: str, data: dict = None):
    """Emit an event on the blinker bus.

    This is the primary API for all modules to fire events. The signal
    is looked up in EVENT_CATALOG; unknown event names are logged and
    silently ignored.

    Args:
        event_name: Key in EVENT_CATALOG (e.g. 'subtitle_downloaded').
        data: Payload dict. Must not contain secrets or absolute paths.
    """
    entry = EVENT_CATALOG.get(event_name)
    if entry is None:
        logger.warning("emit_event called with unknown event: %s", event_name)
        return

    signal = entry["signal"]
    payload = data or {}

    # Determine sender: use current Flask app if available, else None
    sender = None
    try:
        from flask import current_app
        sender = current_app._get_current_object()
    except (ImportError, RuntimeError):
        pass

    signal.send(sender, data=payload)
