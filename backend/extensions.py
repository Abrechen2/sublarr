"""Shared Flask extensions — import from here to avoid circular imports.

The SocketIO instance is created unbound; app.py calls socketio.init_app(app)
inside the create_app() factory function.

Flask-SQLAlchemy and Flask-Migrate are guarded with try/except ImportError
for graceful degradation during the transition period.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO

socketio = SocketIO()

# Rate limiter — unbound, init_app() called in create_app()
# Default storage: in-memory (sufficient for single-process Gunicorn)
limiter = Limiter(key_func=get_remote_address, default_limits=[])

try:
    from flask_migrate import Migrate
    from flask_sqlalchemy import SQLAlchemy

    db = SQLAlchemy()
    migrate = Migrate()
except ImportError as e:
    raise ImportError(
        "flask_sqlalchemy is required: pip install flask_sqlalchemy flask_migrate"
    ) from e
