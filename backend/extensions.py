"""Shared Flask extensions — import from here to avoid circular imports.

The SocketIO instance is created unbound; app.py calls socketio.init_app(app)
inside the create_app() factory function.

Flask-SQLAlchemy and Flask-Migrate are guarded with try/except ImportError
for graceful degradation during the transition period.
"""

from flask_socketio import SocketIO

socketio = SocketIO()

try:
    from flask_sqlalchemy import SQLAlchemy
    from flask_migrate import Migrate

    db = SQLAlchemy()
    migrate = Migrate()
except ImportError:
    db = None  # type: ignore[assignment]
    migrate = None  # type: ignore[assignment]
