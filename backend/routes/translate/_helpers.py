"""Shared helpers for translate routes — BACKEND_TEMPLATES, _run_job, _update_stats."""

import ipaddress
import logging
import threading
import time
from urllib.parse import urlparse

import requests

from extensions import socketio

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
    # --- Community / Fine-tuned Models ---
    {
        "name": "anime_translator_v6",
        "display_name": "Anime Translator V6",
        "backend_type": "ollama",
        "category": "community",
        "description": (
            "Gemma-3-12B fine-tuned on 74k anime subtitle pairs (EN→DE). "
            "Matches qwen2.5:14b quality at 7 GB — no API key, runs fully local via Ollama."
        ),
        "config_defaults": {
            "model": "anime-translator-v6",
            "temperature": "0.3",
        },
        "hf_repo": "sublarr/anime-translator-v6-GGUF",
        "hf_tag": "Q4_K_M",
        "ollama_pull": "hf.co/sublarr/anime-translator-v6-GGUF:Q4_K_M",
        "install_hint": (
            "# Pull directly via Ollama (requires Ollama ≥ 0.3):\n"
            "ollama pull hf.co/sublarr/anime-translator-v6-GGUF:Q4_K_M\n\n"
            "# Or use the Install button above — Sublarr pulls it automatically."
        ),
        "tags": ["fine-tuned", "anime", "en→de", "local", "7GB", "beta"],
        "languages": ["en→de"],
        "size_gb": 7.0,
        "benchmark": {
            "bleu1": 0.281,
            "bleu2": 0.111,
            "length_ratio": 1.02,
            "test_set": "JJK S01E01 vs Crunchyroll DE (30 pairs)",
            "vs_baseline": "beats qwen2.5:14b (0.264) and hunyuan-mt-7b (0.141)",
        },
    },
]


# Batch state (still in-memory for real-time tracking)
batch_state = {
    "running": False,
    "total": 0,
    "processed": 0,
    "succeeded": 0,
    "failed": 0,
    "skipped": 0,
    "current_file": None,
    "errors": [],
}
batch_lock = threading.Lock()

# In-memory stats for quick access (synced to DB)
stats_lock = threading.Lock()
_memory_stats = {
    "started_at": time.time(),
    "upgrades": {"srt_to_ass_translated": 0, "srt_upgrade_skipped": 0},
    "quality_warnings": 0,
}


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


def _validate_callback_url(url):
    """Validate callback URL to prevent SSRF attacks.

    Blocks private IPs, localhost, and non-HTTP schemes.

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    # Block localhost variants
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False, "Localhost callbacks are not allowed"

    # Block private/reserved IP ranges
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
            return False, f"Private/reserved IP not allowed: {hostname}"
    except ValueError:
        # hostname is not an IP — that's fine (it's a domain name)
        pass

    return True, None


def _send_callback(url, data):
    """Send a callback notification (fire-and-forget)."""
    try:
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.warning("Callback to %s failed: %s", url, e)
