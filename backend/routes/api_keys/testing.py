"""Connectivity-test helpers + dispatch table for API-keys services.

Each `_test_*` helper uses lazy imports so importing this module does not
pull in every provider/backend at startup. The `_TEST_DISPATCH` dict maps
the string names stored in `API_KEY_REGISTRY["<service>"]["test_fn"]` to
the actual callables.
"""

from __future__ import annotations


def _test_arr_client(module: str, getter: str, label: str) -> dict:
    """Test an *arr client (Sonarr/Radarr) connection."""
    try:
        import importlib

        mod = importlib.import_module(module)
        client = getattr(mod, getter)()
        if client is None:
            return {"success": False, "message": f"{label} client not configured"}
        result = client.test_connection()
        return (
            result
            if isinstance(result, dict)
            else {"success": bool(result), "message": "OK" if result else "Failed"}
        )
    except Exception as e:
        return {"success": False, "message": str(e)}


def _test_sonarr() -> dict:
    """Test Sonarr connection."""
    return _test_arr_client("sonarr_client", "get_sonarr_client", "Sonarr")


def _test_radarr() -> dict:
    """Test Radarr connection."""
    return _test_arr_client("radarr_client", "get_radarr_client", "Radarr")


def _test_provider(service_name: str) -> dict:
    """Test a subtitle provider by name."""
    try:
        from providers import get_provider_manager

        manager = get_provider_manager()
        provider = manager.get_provider(service_name)
        if provider is None:
            return {
                "success": False,
                "message": f"Provider '{service_name}' not found or not enabled",
            }
        # Use a lightweight connectivity test if available
        if hasattr(provider, "test_connection"):
            return provider.test_connection()
        return {"success": True, "message": f"Provider '{service_name}' is loaded and enabled"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _test_deepl() -> dict:
    """Test DeepL translation backend."""
    try:
        from translation import get_translation_manager

        manager = get_translation_manager()
        if manager is None:
            return {"success": False, "message": "Translation manager not available"}
        backend = manager.get_backend("deepl")
        if backend is None:
            return {"success": False, "message": "DeepL backend not configured"}
        if hasattr(backend, "test_connection"):
            return backend.test_connection()
        return {"success": True, "message": "DeepL backend is loaded"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _test_apprise() -> dict:
    """Test Apprise notification delivery."""
    try:
        from notifier import test_notification

        return test_notification()
    except Exception as e:
        return {"success": False, "message": str(e)}


_TEST_DISPATCH: dict[str, callable] = {
    "_test_sonarr": _test_sonarr,
    "_test_radarr": _test_radarr,
    "_test_provider": _test_provider,
    "_test_deepl": _test_deepl,
    "_test_apprise": _test_apprise,
}
