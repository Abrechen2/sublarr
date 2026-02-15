"""Shared Flask extensions — import from here to avoid circular imports.

The SocketIO instance is created unbound; app.py calls socketio.init_app(app)
inside the create_app() factory function.
"""

from flask_socketio import SocketIO

socketio = SocketIO()
