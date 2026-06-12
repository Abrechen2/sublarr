"""Short-lived signed tokens for browser-native media streaming.

The ``<video>`` element cannot attach an ``X-Api-Key`` header to its own
internal range requests, so the stream URL previously carried the raw API key
as a ``?apikey=`` query parameter. Query strings land in web-server access logs
(Gunicorn/Werkzeug), so every stream request wrote the full API key to disk in
plaintext — anyone with log read access could lift it.

Instead the client first POSTs to ``/media/stream-token`` (authenticated with
the normal header) and receives a short-lived HMAC token bound to the specific
file path. The token — not the key — goes in the stream URL. A leaked log line
now only exposes a path-scoped token that expires within hours.
"""

import base64
import hashlib
import hmac
import time

from flask import current_app, request

# A token must outlive a full playback session (movies run ~2-3 h) but stay
# short enough that a leaked URL is not a durable credential.
_DEFAULT_TTL_SECONDS = 6 * 60 * 60

_STREAM_PATH = "/api/v1/media/stream"


def _secret() -> bytes:
    key = current_app.config.get("SECRET_KEY") or ""
    return key.encode() if isinstance(key, str) else bytes(key)


def generate_stream_token(path: str, ttl: int = _DEFAULT_TTL_SECONDS) -> tuple[str, int]:
    """Return (token, expiry_epoch) binding ``path`` for ``ttl`` seconds."""
    expiry = int(time.time()) + ttl
    msg = f"{expiry}:{path}".encode()
    sig = hmac.new(_secret(), msg, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{expiry}.{sig_b64}", expiry


def verify_stream_token(path: str, token: str) -> bool:
    """Return True iff ``token`` is a valid, unexpired signature over ``path``."""
    if not token or "." not in token:
        return False
    expiry_str, _, sig_part = token.partition(".")
    try:
        expiry = int(expiry_str)
    except ValueError:
        return False
    if expiry < int(time.time()):
        return False
    msg = f"{expiry}:{path}".encode()
    expected = hmac.new(_secret(), msg, hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected).decode().rstrip("=")
    return hmac.compare_digest(sig_part, expected_b64)


def stream_request_has_valid_token() -> bool:
    """Auth-middleware helper: True iff the current request is a /media/stream
    GET carrying a ``token`` that validates against its ``path`` query arg."""
    if request.path != _STREAM_PATH:
        return False
    token = request.args.get("token", "")
    path = request.args.get("path", "")
    if not token or not path:
        return False
    return verify_stream_token(path, token)
