"""Translate routes package — translation jobs, batch, backends, memory."""

from flask import Blueprint

bp = Blueprint("translate", __name__, url_prefix="/api/v1")

from routes.translate import (  # noqa: E402, F401
    backends,
    batch,
    core,
    memory,
    retranslate,
)

# Re-export for routes/webhooks.py and routes/wanted/providers.py
from routes.translate._helpers import _run_job  # noqa: F401
