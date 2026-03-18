"""Translate routes package — translation jobs, batch, backends, memory."""

from flask import Blueprint

bp = Blueprint("translate", __name__, url_prefix="/api/v1")

from routes.translate import backends, batch, core, memory  # noqa: E402, F401

# Re-export for routes/wanted/providers.py and routes/webhooks.py:
# "from routes.translate import _run_job"
from routes.translate._helpers import _run_job  # noqa: F401
