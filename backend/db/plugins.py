"""Plugin config CRUD -- delegating to SQLAlchemy repository."""

from db.repositories.plugins import PluginRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = PluginRepository()
    return _repo


def get_plugin_config(provider_name: str) -> dict:
    """Read all config entries for a plugin provider."""
    return _get_repo().get_plugin_config(provider_name)


def set_plugin_config(provider_name: str, key: str, value: str) -> None:
    """Write a single config entry for a plugin provider."""
    return _get_repo().set_plugin_config(provider_name, key, value)


def get_all_plugin_configs() -> dict:
    """Get all plugin config entries grouped by provider name."""
    return _get_repo().get_all_plugin_configs()


def delete_plugin_config(provider_name: str) -> int:
    """Delete all config entries for a plugin provider."""
    return _get_repo().delete_plugin_config(provider_name)
