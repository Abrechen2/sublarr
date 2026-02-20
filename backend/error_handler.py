"""Centralized error handling with structured JSON error responses.

Custom exception hierarchy with error codes, HTTP status mapping,
and troubleshooting hints. All SublarrError subtypes are automatically
caught by Flask error handlers and returned as structured JSON.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from flask import request, jsonify, g

logger = logging.getLogger(__name__)


# ─── Exception Hierarchy ─────────────────────────────────────────────────────


class SublarrError(Exception):
    """Base exception for all Sublarr application errors.

    Attributes:
        code: Machine-readable error code (e.g. "TRANS_001")
        http_status: HTTP status code to return
        context: Additional context data for debugging
        troubleshooting: Human-readable hint for resolving the issue
    """

    code: str = "SUBLARR_000"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        http_status: Optional[int] = None,
        context: Optional[dict] = None,
        troubleshooting: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        self.context = context or {}
        self.troubleshooting = troubleshooting


class TranslationError(SublarrError):
    """Translation pipeline errors."""

    code = "TRANS_001"
    http_status = 500


class OllamaConnectionError(TranslationError):
    """Cannot connect to Ollama."""

    code = "TRANS_002"
    http_status = 503

    def __init__(self, message: str = "Cannot connect to Ollama", **kwargs: object) -> None:
        super().__init__(
            message,
            troubleshooting="Check that Ollama is running and the URL is correct in Settings.",
            **kwargs,  # type: ignore[arg-type]
        )


class OllamaModelError(TranslationError):
    """Requested model not available in Ollama."""

    code = "TRANS_003"
    http_status = 503

    def __init__(self, model: str = "", **kwargs: object) -> None:
        super().__init__(
            f"Model '{model}' not available in Ollama" if model else "Model not available",
            troubleshooting=f"Run 'ollama pull {model}' to download the model.",
            **kwargs,  # type: ignore[arg-type]
        )


class DatabaseError(SublarrError):
    """Database operation errors."""

    code = "DB_001"
    http_status = 500


class DatabaseIntegrityError(DatabaseError):
    """Database integrity check failed."""

    code = "DB_002"
    http_status = 500

    def __init__(self, message: str = "Database integrity check failed", **kwargs: object) -> None:
        super().__init__(
            message,
            troubleshooting="Try restoring from a backup via Settings > Database.",
            **kwargs,  # type: ignore[arg-type]
        )


class DatabaseBackupError(DatabaseError):
    """Backup operation failed."""

    code = "DB_003"
    http_status = 500


class DatabaseRestoreError(DatabaseError):
    """Restore operation failed."""

    code = "DB_004"
    http_status = 500


class ConfigurationError(SublarrError):
    """Configuration validation errors."""

    code = "CFG_001"
    http_status = 400


# ─── Structured Error Response Builder ───────────────────────────────────────


def _build_error_response(error: SublarrError) -> dict:
    """Build a structured JSON error response from a SublarrError."""
    response: dict = {
        "error": str(error),
        "code": error.code,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Include request ID if available
    request_id = getattr(g, "request_id", None)
    if request_id:
        response["request_id"] = request_id

    if error.context:
        response["context"] = error.context

    if error.troubleshooting:
        response["troubleshooting"] = error.troubleshooting

    return response


# ─── Flask Error Handler Registration ────────────────────────────────────────


def register_error_handlers(app: object) -> None:
    """Register global error handlers on a Flask app.

    Call this once during app setup to install:
    - SublarrError handler (structured JSON)
    - Generic Exception handler (500 with logging)
    - before_request hook for request IDs
    """
    from flask import Flask
    flask_app: Flask = app  # type: ignore[assignment]

    @flask_app.before_request
    def _set_request_id() -> None:
        """Assign a unique request ID to every incoming request."""
        g.request_id = str(uuid.uuid4())[:8]

    @flask_app.errorhandler(SublarrError)
    def _handle_sublarr_error(error: SublarrError):  # type: ignore[return]
        """Return structured JSON for known application errors."""
        logger.warning(
            "[%s] %s: %s (request_id=%s)",
            error.code,
            error.__class__.__name__,
            error,
            getattr(g, "request_id", "?"),
        )
        return jsonify(_build_error_response(error)), error.http_status

    @flask_app.errorhandler(Exception)
    def _handle_generic_error(error: Exception):  # type: ignore[return]
        """Catch-all: log full traceback, return generic 500."""
        # Don't intercept HTTPException (404, 405, etc.) — let Flask handle those
        from werkzeug.exceptions import HTTPException
        if isinstance(error, HTTPException):
            return error

        request_id = getattr(g, "request_id", "?")
        logger.exception(
            "Unhandled exception (request_id=%s): %s", request_id, error
        )
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 500
