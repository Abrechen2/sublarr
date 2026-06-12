"""Translate helpers — shared constants and non-route functions."""

import logging

import requests

from extensions import socketio
from routes.batch_state import (
    _memory_stats,
    stats_lock,
)

logger = logging.getLogger(__name__)


# --- Phase 28-01: LLM Backend Presets ---

BACKEND_TEMPLATES = [
    {
        "name": "deepseek_v3",
        "display_name": "DeepSeek V3",
        "backend_type": "openai_compat",
        "description": "Excellent quality, very low cost (~$0.07/1M tokens). Requires API key.",
        "config_defaults": {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "context_window": 64000,
        },
    },
    {
        "name": "gemini_flash",
        "display_name": "Gemini 1.5 Flash",
        "backend_type": "openai_compat",
        "description": "Fast, cheap Google model with huge context window. Requires API key.",
        "config_defaults": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "gemini-1.5-flash",
            "context_window": 128000,
        },
    },
    {
        "name": "claude_haiku",
        "display_name": "Claude 3 Haiku",
        "backend_type": "openai_compat",
        "description": "Fast Anthropic model, good quality/cost ratio. Requires API key.",
        "config_defaults": {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-3-haiku-20240307",
            "context_window": 32000,
        },
    },
    {
        "name": "mistral_medium",
        "display_name": "Mistral Medium",
        "backend_type": "openai_compat",
        "description": "Balanced quality and cost from Mistral AI. Requires API key.",
        "config_defaults": {
            "base_url": "https://api.mistral.ai/v1",
            "model": "mistral-medium-latest",
            "context_window": 32000,
        },
    },
    {
        "name": "lm_studio",
        "display_name": "LM Studio (local)",
        "backend_type": "openai_compat",
        "description": "Run any GGUF model locally. No API key needed. Start LM Studio server first.",
        "config_defaults": {
            "base_url": "http://localhost:1234/v1",
            "model": "local-model",
            "context_window": 8000,
        },
    },
    # --- Recommended general-purpose local models ---
    {
        "name": "qwen25_14b_instruct",
        "display_name": "Qwen2.5 14B Instruct (local)",
        "backend_type": "ollama",
        "category": "community",
        "description": (
            "Solid all-round instruction-tuned model. Runs fully local via "
            "Ollama, no API key. ~9 GB — needs a machine with the RAM/VRAM "
            "headroom to load it."
        ),
        "config_defaults": {
            "model": "qwen2.5:14b-instruct",
            "temperature": "0.3",
        },
        "ollama_pull": "qwen2.5:14b-instruct",
        "install_hint": (
            "# Pull via Ollama:\n"
            "ollama pull qwen2.5:14b-instruct\n\n"
            "# Or use the Install button above — Sublarr pulls it automatically."
        ),
        "tags": ["instruct", "general", "local", "9GB", "beta"],
        "languages": ["multi"],
        "size_gb": 9.0,
    },
    {
        "name": "llama31_8b_instruct",
        "display_name": "Llama 3.1 8B Instruct (local)",
        "backend_type": "ollama",
        "category": "community",
        "description": (
            "Lighter instruction-tuned alternative — fits in ~5 GB. "
            "Runs fully local via Ollama, no API key."
        ),
        "config_defaults": {
            "model": "llama3.1:8b-instruct",
            "temperature": "0.3",
        },
        "ollama_pull": "llama3.1:8b-instruct",
        "install_hint": (
            "# Pull via Ollama:\n"
            "ollama pull llama3.1:8b-instruct\n\n"
            "# Or use the Install button above — Sublarr pulls it automatically."
        ),
        "tags": ["instruct", "general", "local", "5GB", "beta"],
        "languages": ["multi"],
        "size_gb": 5.0,
    },
]


def _is_translation_enabled() -> bool:
    """Return True iff the translation feature is enabled in config.

    The dual /translate/disable + ``translation_enabled`` config flag had a
    silent gap: clicking Disable cancelled queued jobs and toggled the
    flag, but every translation-initiating endpoint still ran on new
    requests because nothing on the read side honoured the flag. Each
    initiating route now calls this helper after input validation and
    returns 503 when it returns False — same vocabulary as the Whisper
    feature gate (see translator._helpers._is_whisper_enabled).
    """
    try:
        from db.config import get_config_entry

        value = get_config_entry("translation_enabled")
        if value is None:
            # No DB override → fall back to the Pydantic default.
            from config import get_settings

            return bool(getattr(get_settings(), "translation_enabled", False))
        return value.lower() in ("true", "1", "yes")
    except Exception:
        # On any lookup failure default to False so a corrupt config never
        # silently re-enables a feature the user explicitly disabled.
        return False


def _update_stats(result):
    """Update stats from a translation result (thread-safe)."""
    from db.jobs import record_stat

    with stats_lock:
        if result["success"]:
            s = result.get("stats", {})
            if s.get("skipped"):
                record_stat(success=True, skipped=True)
                reason = s.get("reason", "")
                if "no ASS upgrade" in reason:
                    _memory_stats["upgrades"]["srt_upgrade_skipped"] += 1
            else:
                fmt = s.get("format", "")
                source = s.get("source", "")
                record_stat(success=True, skipped=False, fmt=fmt, source=source)
                if s.get("upgrade_from_srt"):
                    _memory_stats["upgrades"]["srt_to_ass_translated"] += 1
                if s.get("quality_warnings"):
                    _memory_stats["quality_warnings"] += len(s["quality_warnings"])
        else:
            record_stat(success=False)


def _run_job(job_data):
    """Execute a translation job in a background thread."""
    from db.jobs import record_stat, update_job
    from translator import translate_file

    job_id = job_data["id"]
    try:
        update_job(job_id, "running")

        result = translate_file(
            job_data["file_path"],
            force=job_data.get("force", False),
            arr_context=job_data.get("arr_context"),
        )

        status = "completed" if result["success"] else "failed"
        update_job(job_id, status, result=result, error=result.get("error"))
        _update_stats(result)

        # Emit WebSocket event
        socketio.emit(
            "job_update",
            {
                "id": job_id,
                "status": status,
                "result": result,
            },
        )

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        update_job(job_id, "failed", error=str(e))
        record_stat(success=False)


def _build_arr_context(data):
    """Build arr_context including language direction and optional Sonarr IDs."""
    from config import get_settings

    settings = get_settings()
    context = {
        "source_language": getattr(settings, "source_language", "en"),
        "target_language": getattr(settings, "target_language", "de"),
    }
    series_id = data.get("sonarr_series_id")
    episode_id = data.get("sonarr_episode_id")
    if series_id and episode_id:
        context["sonarr_series_id"] = series_id
        context["sonarr_episode_id"] = episode_id
    return context


def _validate_callback_url(url):
    """Validate callback URL to prevent SSRF attacks.

    Delegates to the canonical ``security_utils.validate_service_url`` so the
    bypass surface is identical to every other outbound-URL check: it
    normalises decimal/octal/hex-encoded IPv4 and IPv4-mapped IPv6 before
    the loopback/link-local/metadata checks fire (the hand-rolled
    ``ipaddress.ip_address`` form here accepted ``http://2130706433/`` =
    127.0.0.1) and resolves DNS hostnames to re-check every A/AAAA answer.

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    from security_utils import validate_service_url

    return validate_service_url(url)


def _send_callback(url, data):
    """Send a callback notification (fire-and-forget)."""
    try:
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.warning("Callback to %s failed: %s", url, e)
