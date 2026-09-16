"""Ollama reachability check used by the health endpoints.

This module used to carry a complete second translation client — its own
prompt builder, batching and retries — that nothing in production called any
more. The live translation path is ``translation.ollama.OllamaBackend`` with
the prompt built by ``translation.llm_utils``. The dead copy was removed
because code-intelligence tools resolved "the prompt builder" to it, pointing
anyone about to edit the live one at the wrong blast radius (Forgejo #29).
"""

import logging

import requests

from config import get_settings

logger = logging.getLogger(__name__)


def check_ollama_health():
    """Check if Ollama is reachable and the model is available.

    Returns:
        tuple: (is_healthy: bool, message: str)
    """
    settings = get_settings()
    try:
        resp = requests.get(f"{settings.ollama_url}/api/tags", timeout=10)
        if resp.status_code != 200:
            return False, f"Ollama returned status {resp.status_code}"
        try:
            data = resp.json()
        except ValueError:
            return False, "Ollama returned invalid JSON"
        models = [m["name"] for m in data.get("models", [])]
        model_found = any(settings.ollama_model in name for name in models)
        if not model_found:
            return False, f"Model '{settings.ollama_model}' not found. Available: {models}"
        return True, "OK"
    except requests.Timeout:
        return False, f"Ollama health check timed out at {settings.ollama_url}"
    except requests.ConnectionError:
        return False, f"Cannot connect to Ollama at {settings.ollama_url}"
    except Exception as e:
        return False, f"Ollama health check failed: {e}"
