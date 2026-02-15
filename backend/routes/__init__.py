"""Routes package — Blueprint registration for all API endpoints.

Each blueprint module defines a `bp` variable. This module provides
register_blueprints() which imports and registers all 9 blueprints.
"""


def register_blueprints(app):
    """Import and register all API blueprints on the Flask app."""
    from routes.translate import bp as translate_bp
    from routes.providers import bp as providers_bp
    from routes.library import bp as library_bp
    from routes.wanted import bp as wanted_bp
    from routes.config import bp as config_bp
    from routes.webhooks import bp as webhooks_bp
    from routes.system import bp as system_bp
    from routes.profiles import bp as profiles_bp
    from routes.blacklist import bp as blacklist_bp
    from routes.plugins import bp as plugins_bp
    from routes.mediaservers import bp as mediaservers_bp
    from routes.whisper import bp as whisper_bp
    from routes.standalone import bp as standalone_bp

    for blueprint in [
        translate_bp,
        providers_bp,
        library_bp,
        wanted_bp,
        config_bp,
        webhooks_bp,
        system_bp,
        profiles_bp,
        blacklist_bp,
        plugins_bp,
        mediaservers_bp,
        whisper_bp,
        standalone_bp,
    ]:
        app.register_blueprint(blueprint)
