"""Ollama API client with batching, retry logic, and validation.

All configuration is loaded from config.py Settings.
"""

import re
import time
import logging

import requests

from config import get_settings
from database import get_glossary_for_series

logger = logging.getLogger(__name__)

# CJK Unicode ranges for hallucination detection (Qwen2.5 sometimes drifts into Chinese)
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff"    # CJK Unified Ideographs
    r"\u3400-\u4dbf"     # CJK Extension A
    r"\u2e80-\u2eff"     # CJK Radicals
    r"\uf900-\ufaff]"    # CJK Compatibility Ideographs
)


def _has_cjk_hallucination(text):
    """Detect CJK characters in translated text (Qwen2.5 hallucination)."""
    return bool(_CJK_RE.search(text))


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
        model_found = any(
            settings.ollama_model in name for name in models
        )
        if not model_found:
            return False, f"Model '{settings.ollama_model}' not found. Available: {models}"
        return True, "OK"
    except requests.Timeout:
        return False, f"Ollama health check timed out at {settings.ollama_url}"
    except requests.ConnectionError:
        return False, f"Cannot connect to Ollama at {settings.ollama_url}"
    except Exception as e:
        return False, f"Ollama health check failed: {e}"


def _call_ollama(prompt):
    """Make a single Ollama API call.

    Returns:
        str: Model response text

    Raises:
        RuntimeError: On API errors or invalid responses
        requests.RequestException: On network errors
    """
    settings = get_settings()
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": settings.temperature,
            "num_predict": 4096,
        },
    }
    resp = requests.post(
        f"{settings.ollama_url}/api/generate",
        json=payload,
        timeout=settings.request_timeout,
    )
    
    # Handle rate limiting (429) before raise_for_status
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                wait_seconds = int(retry_after)
            except ValueError:
                wait_seconds = 60
        else:
            wait_seconds = 60
        logger.warning("Ollama API rate limited, waiting %ds", wait_seconds)
        raise RuntimeError(f"Ollama rate limited, retry after {wait_seconds}s")
    
    resp.raise_for_status()

    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError("Ollama returned invalid JSON response")

    if "error" in data:
        raise RuntimeError(f"Ollama error: {data['error']}")

    if "response" not in data:
        raise RuntimeError(f"Ollama response missing 'response' key: {list(data.keys())}")

    return data["response"].strip()


def _parse_response(response_text, expected_count):
    """Parse Ollama response into individual lines.

    Handles numbered responses (e.g., "1: text") and plain lines.
    Attempts to merge split lines before truncating.

    Returns:
        list: Parsed lines, or None if count mismatch
    """
    lines = response_text.strip().split("\n")
    lines = [l for l in lines if l.strip()]

    # Strip numbering if present (e.g., "1: text" or "1. text")
    cleaned = []
    for line in lines:
        stripped = re.sub(r"^\d+[\.:]\s*", "", line)
        cleaned.append(stripped)

    if len(cleaned) == expected_count:
        return cleaned

    # Too many lines: try merging consecutive non-numbered lines
    if len(cleaned) > expected_count:
        logger.warning(
            "Got %d lines, expected %d. Trying to merge excess lines.",
            len(cleaned), expected_count,
        )
        merged = []
        for i, line in enumerate(cleaned):
            original = lines[i] if i < len(lines) else ""
            if re.match(r"^\d+[\.:]\s*", original):
                merged.append(line)
            elif merged:
                merged[-1] = merged[-1] + " " + line
            else:
                merged.append(line)

        if len(merged) == expected_count:
            return merged

        logger.warning("Merge failed (%d lines), truncating to %d", len(merged), expected_count)
        return cleaned[:expected_count]

    logger.warning(
        "Line count mismatch: got %d, expected %d", len(cleaned), expected_count,
    )
    return None


def build_prompt_with_glossary(prompt_template, glossary_entries, lines):
    """Build a translation prompt with glossary terms prepended.
    
    Args:
        prompt_template: Base prompt template
        glossary_entries: List of {source_term, target_term} dicts (max 15)
        lines: List of subtitle lines to translate
    
    Returns:
        str: Complete prompt with glossary and numbered lines
    """
    if not glossary_entries:
        numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines))
        return prompt_template + numbered
    
    # Build glossary string (max 15 entries)
    glossary_parts = [f"{entry['source_term']} → {entry['target_term']}" for entry in glossary_entries[:15]]
    glossary_str = "Glossary: " + ", ".join(glossary_parts) + "\n\n"
    
    numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines))
    return glossary_str + prompt_template + numbered


def translate_batch(lines, series_id=None):
    """Translate a batch of subtitle lines.

    Args:
        lines: List of subtitle lines to translate
        series_id: Optional Sonarr series ID for glossary lookup

    Returns:
        list: Translated lines in same order

    Raises:
        RuntimeError: If all retries fail
    """
    if not lines:
        return []

    settings = get_settings()
    prompt_template = settings.get_prompt_template()
    
    # Load glossary if series_id provided
    glossary_entries = []
    if series_id:
        try:
            glossary_entries = get_glossary_for_series(series_id)
            if glossary_entries:
                logger.debug("Loaded %d glossary entries for series %d", len(glossary_entries), series_id)
        except Exception as e:
            logger.debug("Failed to load glossary for series %d: %s", series_id, e)
    
    prompt = build_prompt_with_glossary(prompt_template, glossary_entries, lines)

    last_error = None
    for attempt in range(1, settings.max_retries + 1):
        try:
            response = _call_ollama(prompt)
            parsed = _parse_response(response, len(lines))
            if parsed is not None:
                # Check for CJK hallucination in any line
                tainted = [i for i, t in enumerate(parsed) if _has_cjk_hallucination(t)]
                if tainted:
                    logger.warning(
                        "Attempt %d: CJK hallucination in %d lines (indices %s), retrying...",
                        attempt, len(tainted), tainted,
                    )
                    last_error = ValueError("CJK hallucination detected")
                else:
                    return parsed
            else:
                logger.warning("Attempt %d: line count mismatch, retrying...", attempt)
                last_error = ValueError(
                    f"Expected {len(lines)} lines, got different count"
                )
        except (requests.RequestException, RuntimeError) as e:
            logger.warning("Attempt %d failed: %s", attempt, e)
            last_error = e

        if attempt < settings.max_retries:
            wait = settings.backoff_base * (2 ** (attempt - 1))
            logger.info("Waiting %ds before retry...", wait)
            time.sleep(wait)

    # Fallback: translate lines individually
    logger.warning("Batch translation failed, falling back to single-line mode")
    return _translate_singles(lines, series_id=series_id)


def _translate_singles(lines, series_id=None):
    """Translate lines one by one as fallback, with retries.

    Args:
        lines: List of subtitle lines
        series_id: Optional Sonarr series ID for glossary lookup

    Returns:
        list: Translated lines (untranslated on failure)
    """
    settings = get_settings()
    prompt_template = settings.get_prompt_template()
    
    # Load glossary if series_id provided
    glossary_entries = []
    if series_id:
        try:
            glossary_entries = get_glossary_for_series(series_id)
        except Exception as e:
            logger.debug("Failed to load glossary for series %d: %s", series_id, e)

    results = []
    for i, line in enumerate(lines):
        prompt = build_prompt_with_glossary(prompt_template, glossary_entries, [line])
        last_error = None

        for attempt in range(1, settings.max_retries + 1):
            try:
                response = _call_ollama(prompt)
                translated = re.sub(r"^\d+[\.:]\s*", "", response.strip().split("\n")[0])
                if _has_cjk_hallucination(translated):
                    logger.warning("Single line %d, attempt %d: CJK hallucination, retrying", i, attempt)
                    last_error = ValueError("CJK hallucination detected")
                else:
                    results.append(translated)
                    last_error = None
                    break
            except (requests.RequestException, RuntimeError) as e:
                logger.warning("Single line %d, attempt %d failed: %s", i, attempt, e)
                last_error = e
            if attempt < settings.max_retries:
                wait = settings.backoff_base * (2 ** (attempt - 1))
                time.sleep(wait)

        if last_error is not None:
            logger.error("Failed to translate line %d after %d attempts, keeping original", i, settings.max_retries)
            results.append(line)

    return results


def translate_all(lines, batch_size=None, series_id=None):
    """Translate all lines in batches.

    Args:
        lines: List of subtitle lines to translate
        batch_size: Optional batch size (defaults to config)
        series_id: Optional Sonarr series ID for glossary lookup

    Returns:
        list: All translated lines in order
    """
    if batch_size is None:
        settings = get_settings()
        batch_size = settings.batch_size

    total = len(lines)
    if total == 0:
        return []

    logger.info("Translating %d lines in batches of %d%s", total, batch_size,
                f" (series_id: {series_id})" if series_id else "")
    results = []

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = lines[start:end]
        batch_num = start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        logger.info("Batch %d/%d (%d lines)", batch_num, total_batches, len(batch))
        translated = translate_batch(batch, series_id=series_id)
        results.extend(translated)

    return results
