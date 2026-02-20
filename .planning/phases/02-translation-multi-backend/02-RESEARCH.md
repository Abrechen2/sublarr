# Phase 2: Translation Multi-Backend - Research

**Researched:** 2026-02-15
**Domain:** Multi-backend translation architecture, API integration (DeepL, LibreTranslate, OpenAI-compatible, Google Cloud Translation), fallback chains, quality metrics
**Confidence:** HIGH

## Summary

Phase 2 transforms Sublarr's hardcoded Ollama-only translation pipeline into a multi-backend architecture supporting 5 translation services: Ollama (existing, remains default), DeepL, LibreTranslate, OpenAI-compatible (OpenAI, Azure, LM Studio, vLLM), and Google Cloud Translation. The work requires three fundamental changes: (1) abstracting translation behind a `TranslationBackend` ABC that all backends implement, (2) integrating backend selection into the existing language profile system so different series/profiles can use different backends, and (3) building a fallback chain mechanism with quality metrics tracking.

The current codebase has a clean separation point: `translator.py` calls `translate_all()` from `ollama_client.py`, which handles batching, retry, and hallucination detection. The ABC must preserve the batch-oriented interface (`translate_batch`) while allowing backends with fundamentally different APIs (LLM prompt-based vs. dedicated translation API). The key design challenge is that LLM backends (Ollama, OpenAI-compatible) use prompt templates and produce raw text that needs parsing, while API backends (DeepL, LibreTranslate, Google) accept text directly and return clean translations. The ABC must accommodate both patterns without leaking implementation details.

The existing `language_profiles` table and `config_entries` table provide the right foundation. Backend selection per profile requires a new column on `language_profiles`, and backend configurations are stored in `config_entries` with namespaced keys (following the `plugin.<name>.<key>` pattern established in Phase 1). The fallback chain is a JSON array of backend names stored per profile, with the translation orchestrator trying each in order until one succeeds. Quality metrics (success rate, error count, average response time) are tracked per backend in a new `translation_backend_stats` table, paralleling the existing `provider_stats` pattern.

**Primary recommendation:** Build the TranslationBackend ABC and migrate Ollama first (TRAN-01, TRAN-02), then implement the four new backends (TRAN-03 through TRAN-06), then wire up profile-based selection and fallback chain (TRAN-07, TRAN-08), then build the UI and metrics (TRAN-09, TRAN-10).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| deepl | 1.28.0 | DeepL API client (Free + Pro) | Official Python SDK; supports text translation, glossaries, usage tracking; 3.9-3.13 compatible |
| openai | 1.x+ | OpenAI-compatible API client | Official SDK; `base_url` parameter enables LM Studio, vLLM, Azure, any compatible endpoint |
| google-cloud-translate | 3.x | Google Cloud Translation v3 | Official Google SDK; supports glossaries, batch translate, language detection |
| requests | 2.32+ | HTTP client for LibreTranslate | Already in requirements; LibreTranslate has no official Python client SDK, simple REST calls suffice |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.x | Backend config validation | Already in stack; validate backend-specific config fields |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| openai SDK | litellm | litellm covers 100+ providers but adds ~40 transitive deps; prior decision says openai SDK is sufficient since all target endpoints are OpenAI-compatible |
| requests for LibreTranslate | libretranslatepy (unofficial) | Unofficial, small maintainer base, adds dependency for 3 HTTP calls; raw requests is simpler |
| google-cloud-translate | REST API + requests | SDK handles auth, retry, pagination, GCS interaction automatically; manual REST would replicate all that |

**Installation:**
```bash
pip install deepl openai google-cloud-translate
```

Add to `backend/requirements.txt`:
```
deepl>=1.20.0
openai>=1.0.0
google-cloud-translate>=3.10.0
```

Note: `requests` is already a dependency. No additional libraries needed for LibreTranslate.

## Architecture Patterns

### Recommended Project Structure
```
backend/
  translation/
    __init__.py              # TranslationManager (singleton, registry, fallback orchestration)
    base.py                  # TranslationBackend ABC + TranslationResult dataclass
    ollama.py                # Ollama backend (migrated from ollama_client.py)
    deepl_backend.py         # DeepL Free + Pro backend
    libretranslate.py        # LibreTranslate backend
    openai_compat.py         # OpenAI-compatible backend (OpenAI, Azure, LM Studio, vLLM)
    google_translate.py      # Google Cloud Translation v3 backend
  db/
    translation.py           # Extended: backend stats operations
  routes/
    translate.py             # Extended: backend management endpoints
    profiles.py              # Extended: backend selection per profile
```

### Pattern 1: TranslationBackend ABC
**What:** Abstract base class that all translation backends implement, with three required methods and declarative config fields.
**When to use:** Every backend implements this contract.
**Example:**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TranslationResult:
    """Result from a backend translation call."""
    translated_lines: list[str]
    backend_name: str
    response_time_ms: float = 0
    characters_used: int = 0
    error: Optional[str] = None
    success: bool = True

class TranslationBackend(ABC):
    """Abstract base class for translation backends.

    Class-level attributes for config UI:
        name: Unique backend identifier (lowercase)
        display_name: Human-readable name for UI
        config_fields: Declarative config field definitions for Settings UI
        supports_glossary: Whether this backend supports glossary/terminology
        supports_batch: Whether translate_batch handles multiple lines natively
        max_batch_size: Maximum lines per batch call (0 = unlimited)
    """

    name: str = "unknown"
    display_name: str = "Unknown"
    config_fields: list[dict] = []
    supports_glossary: bool = False
    supports_batch: bool = True
    max_batch_size: int = 0  # 0 = no limit

    def __init__(self, **config):
        self.config = config

    @abstractmethod
    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
        """Translate a batch of subtitle lines.

        Args:
            lines: List of subtitle text lines to translate
            source_lang: ISO 639-1 source language code
            target_lang: ISO 639-1 target language code
            glossary_entries: Optional list of {source_term, target_term} dicts

        Returns:
            TranslationResult with translated_lines in same order as input
        """
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check if the backend is reachable and configured correctly.

        Returns:
            (is_healthy, message) tuple
        """
        ...

    @abstractmethod
    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI.

        Returns:
            List of field dicts: {"key": str, "label": str, "type": str,
                                  "required": bool, "default": str, "help": str}
        """
        ...

    def get_usage(self) -> dict:
        """Return usage/quota information if available.

        Returns:
            Dict with backend-specific usage info (e.g. character count for DeepL)
        """
        return {}
```

### Pattern 2: TranslationManager (Registry + Orchestration)
**What:** Singleton that manages backend instances, handles fallback chains, and delegates translation calls.
**When to use:** Called by `translator.py` instead of `ollama_client.translate_all()`.
**Example:**
```python
class TranslationManager:
    """Manages translation backends and orchestrates fallback chains."""

    _backends: dict[str, TranslationBackend] = {}
    _backend_classes: dict[str, type[TranslationBackend]] = {}

    def register_backend(self, cls: type[TranslationBackend]):
        """Register a backend class."""
        self._backend_classes[cls.name] = cls

    def get_backend(self, name: str) -> TranslationBackend | None:
        """Get or create a backend instance by name."""
        if name not in self._backends:
            cls = self._backend_classes.get(name)
            if not cls:
                return None
            config = self._load_backend_config(name)
            self._backends[name] = cls(**config)
        return self._backends[name]

    def translate_with_fallback(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        fallback_chain: list[str],
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
        """Try each backend in the fallback chain until one succeeds."""
        last_error = None
        for backend_name in fallback_chain:
            backend = self.get_backend(backend_name)
            if not backend:
                continue
            try:
                result = backend.translate_batch(
                    lines, source_lang, target_lang, glossary_entries
                )
                if result.success:
                    self._record_success(backend_name, result)
                    return result
                last_error = result.error
            except Exception as e:
                last_error = str(e)
                self._record_failure(backend_name, str(e))

        return TranslationResult(
            translated_lines=[],
            backend_name="none",
            error=f"All backends failed. Last error: {last_error}",
            success=False,
        )
```

### Pattern 3: Backend Selection via Language Profile
**What:** Each language profile stores a `translation_backend` and `fallback_chain_json` field. The translator resolves the profile for a series/movie and uses its backend config.
**When to use:** In the translation pipeline, after determining which file to translate and before calling translate.
**Example:**
```python
# In translator.py, replacing direct ollama_client.translate_all() call:

def _get_translation_backend_for_context(arr_context, target_language):
    """Resolve which translation backend to use based on profile."""
    from db.profiles import get_series_profile, get_movie_profile, get_default_profile

    profile = get_default_profile()
    if arr_context:
        if arr_context.get("sonarr_series_id"):
            profile = get_series_profile(arr_context["sonarr_series_id"])
        elif arr_context.get("radarr_movie_id"):
            profile = get_movie_profile(arr_context["radarr_movie_id"])

    backend_name = profile.get("translation_backend", "ollama")
    fallback_chain = profile.get("fallback_chain", [backend_name])

    return backend_name, fallback_chain
```

### Pattern 4: Config Storage Using config_entries Namespacing
**What:** Backend-specific configuration is stored in the `config_entries` table using `backend.<name>.<field>` namespaced keys, following the `plugin.<name>.<key>` pattern from Phase 1.
**When to use:** For storing API keys, URLs, model names, and other backend-specific settings.
**Example:**
```python
# Keys in config_entries:
# backend.deepl.api_key = "..."
# backend.deepl.plan = "free"
# backend.libretranslate.url = "http://libretranslate:5000"
# backend.libretranslate.api_key = ""
# backend.openai.api_key = "sk-..."
# backend.openai.base_url = "https://api.openai.com/v1"
# backend.openai.model = "gpt-4o-mini"
# backend.google.project_id = "my-project"
# backend.google.credentials_json = "/config/google-creds.json"
```

### Anti-Patterns to Avoid
- **Hardcoding backend selection in translator.py:** The translator must resolve backends via profiles, never hardcode "ollama" or any specific backend.
- **Making LLM-specific assumptions in the ABC:** The ABC must not assume prompt templates, temperature, or response parsing. LLM backends handle prompt construction internally.
- **Storing credentials in Pydantic Settings:** Backend credentials go in `config_entries` DB table (like plugin config), NOT as new Pydantic fields. This keeps the Settings class manageable and allows dynamic backend addition.
- **Blocking on backend initialization:** Backend instances should be created lazily (on first use), not at app startup. A misconfigured DeepL key should not prevent Ollama from working.
- **Mixing fallback logic with backend logic:** Fallback orchestration belongs in TranslationManager, not inside individual backends. Each backend simply succeeds or fails.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DeepL API integration | Custom HTTP client with auth | `deepl` official SDK (v1.28.0) | Handles auth, rate limiting, character counting, glossary management, error codes; 3M+ downloads |
| OpenAI-compatible API calls | Custom chat completions client | `openai` official SDK with `base_url` | One SDK covers OpenAI, Azure, LM Studio, vLLM, any OpenAI-compatible endpoint; handles streaming, retry, auth |
| Google Cloud Translation | Custom REST client with OAuth | `google-cloud-translate` SDK | Handles service account auth, glossary management, GCS interaction, pagination; Google-maintained |
| Circuit breaker for backends | Custom failure tracking | Reuse existing `CircuitBreaker` class | Already implemented, thread-safe, proven in provider system; apply same pattern to translation backends |
| Glossary term matching | Custom string replacement pre-translation | Pass to backend natively | DeepL and Google both have native glossary support; LLM backends use prompt injection; LibreTranslate does not support glossaries |
| Rate limiting for DeepL | Custom token bucket | DeepL SDK handles 429 responses internally | SDK has built-in retry with backoff for rate limits |

**Key insight:** The translation backends fall into two categories -- **API backends** (DeepL, LibreTranslate, Google) that accept text and return translations directly, and **LLM backends** (Ollama, OpenAI-compatible) that need prompt construction, response parsing, and hallucination detection. The ABC must accommodate both without forcing one pattern on the other.

## Common Pitfalls

### Pitfall 1: DeepL Free vs Pro API URL Confusion
**What goes wrong:** DeepL Free API uses `https://api-free.deepl.com` while Pro uses `https://api.deepl.com`. Using the wrong URL silently fails or returns 403.
**Why it happens:** Users configure an API key without specifying plan type; the SDK needs to know which endpoint to use.
**How to avoid:** The DeepL Python SDK auto-detects the plan from the API key suffix (Free keys end with `:fx`). Use `deepl.DeepLClient(auth_key)` and let the SDK choose the endpoint. But expose a plan indicator in the config UI so users see which plan they are on.
**Warning signs:** 403 Forbidden errors from DeepL; "Authorization failed" message.

### Pitfall 2: Batch Size Mismatch Between Backends
**What goes wrong:** Ollama handles 15 lines per batch (prompt-based). DeepL allows up to 50 texts per request (128KB limit). LibreTranslate handles one text at a time. Google Cloud handles up to 1024 texts.
**Why it happens:** Each backend has different optimal/maximum batch sizes.
**How to avoid:** The `max_batch_size` class attribute on each backend tells the TranslationManager how to chunk. The manager splits input lines into backend-appropriate batches. The `translate_batch` method always receives a correctly-sized batch.
**Warning signs:** Timeouts on large batches; 413 Request Entity Too Large errors; DeepL returning partial results.

### Pitfall 3: Line Count Mismatch in LLM Responses
**What goes wrong:** LLM backends (Ollama, OpenAI) may return fewer or more lines than requested, breaking the 1:1 mapping between source and translated subtitle events.
**Why it happens:** LLMs sometimes merge short lines, split long lines, or hallucinate extra content. This is a fundamental LLM problem, not a bug.
**How to avoid:** The existing `_parse_response()` logic from `ollama_client.py` handles this with numbered lines, merge attempts, and truncation. This parsing logic must be shared between Ollama and OpenAI-compatible backends (extract into a shared LLM response parser utility). API backends (DeepL, Google, LibreTranslate) do NOT have this problem -- they return exactly one translation per input text.
**Warning signs:** "Line count mismatch" warnings in logs; translated subtitles with wrong timing alignment.

### Pitfall 4: CJK Hallucination in LLM Backends
**What goes wrong:** Qwen2.5 and other multilingual LLMs sometimes drift into Chinese characters when translating between non-CJK languages.
**Why it happens:** The model's training data includes CJK text and the model occasionally "forgets" the target language mid-generation.
**How to avoid:** The existing `_has_cjk_hallucination()` check from `ollama_client.py` must be preserved in the shared LLM utilities. Apply it to both Ollama and OpenAI-compatible backend responses. API backends (DeepL, Google, LibreTranslate) are immune to this.
**Warning signs:** Chinese/Japanese characters appearing in German translations; retry loop hitting max retries.

### Pitfall 5: Glossary Support Inconsistency Across Backends
**What goes wrong:** User configures glossary terms expecting consistent behavior, but each backend handles glossaries differently -- or not at all.
**Why it happens:** DeepL has a native glossary API (create, store, reference). Google Cloud has native glossary support (stored in GCS). LLM backends inject glossary terms into the prompt. LibreTranslate has NO glossary support.
**How to avoid:** The ABC's `supports_glossary` flag lets the UI show/hide glossary features per backend. LLM backends use the existing `build_prompt_with_glossary()` function. API backends with native glossary support manage their own glossary lifecycle. LibreTranslate silently ignores glossary entries. Document this clearly per backend.
**Warning signs:** User expects consistent translations with glossary but gets different results depending on backend; glossary terms ignored by LibreTranslate.

### Pitfall 6: Fallback Chain Infinite Loop or Cascade Failure
**What goes wrong:** All backends in the chain fail, causing extremely long translation times as each backend retries internally before failing to the next.
**Why it happens:** Each backend has its own retry logic (Ollama: 3 retries with exponential backoff; DeepL SDK: internal retries). A 3-backend chain with 3 retries each = 9 total attempts with increasing delays.
**How to avoid:** The TranslationManager should: (1) use circuit breakers per backend to skip known-failing backends instantly, (2) set a total timeout for the entire fallback chain, (3) limit internal retries when operating within a fallback chain (e.g., 1 retry per backend instead of 3). The circuit breaker from the provider system is reusable here.
**Warning signs:** Translation jobs taking 10+ minutes; all backends showing failures in metrics; circuit breakers all in OPEN state.

### Pitfall 7: Google Cloud Credentials Management
**What goes wrong:** Google Cloud Translation requires service account credentials. Users must either set `GOOGLE_APPLICATION_CREDENTIALS` env var or provide a JSON key file path. This is more complex than other backends' simple API keys.
**Why it happens:** Google Cloud uses IAM/service accounts, not simple API keys. The Python SDK reads credentials from a file path or environment.
**How to avoid:** Support both methods: (1) env var `GOOGLE_APPLICATION_CREDENTIALS` for Docker users who mount a credentials file, (2) a config field `credentials_json_path` that points to the file. The health check verifies both the file exists and the credentials are valid. Clear documentation with step-by-step setup.
**Warning signs:** "DefaultCredentialsError" on startup; "Permission denied" on translate calls; credentials file not found in container.

### Pitfall 8: OpenAI-Compatible Endpoint Diversity
**What goes wrong:** LM Studio, vLLM, and Ollama's OpenAI-compatible endpoint each have slightly different behavior for the same API surface. Some support streaming, some do not. Some require model names in specific formats.
**Why it happens:** "OpenAI-compatible" means the request/response format matches, but edge cases differ. LM Studio expects model names from its loaded models. vLLM requires the model parameter to match the served model exactly.
**How to avoid:** The OpenAI-compatible backend should: (1) let users specify the exact model name, (2) have a health check that calls `/v1/models` to verify the model is available, (3) disable streaming by default (not all endpoints support it), (4) have a generous timeout (LLM inference is slow).
**Warning signs:** "Model not found" errors; empty responses; timeout errors on first request.

## Code Examples

Verified patterns from official documentation and the existing codebase:

### Ollama Backend (Migration from ollama_client.py)
```python
# Source: Existing backend/ollama_client.py, refactored into TranslationBackend

class OllamaBackend(TranslationBackend):
    name = "ollama"
    display_name = "Ollama (Local LLM)"
    supports_glossary = True  # Via prompt injection
    supports_batch = True
    max_batch_size = 25  # Configurable, default from existing batch_size setting

    config_fields = [
        {"key": "url", "label": "Ollama URL", "type": "text", "required": True,
         "default": "http://localhost:11434", "help": "Ollama API endpoint"},
        {"key": "model", "label": "Model", "type": "text", "required": True,
         "default": "qwen2.5:14b-instruct", "help": "Model name as shown in ollama list"},
        {"key": "temperature", "label": "Temperature", "type": "number", "required": False,
         "default": "0.3", "help": "Lower = more deterministic (0.0-1.0)"},
        {"key": "request_timeout", "label": "Timeout (seconds)", "type": "number",
         "required": False, "default": "90"},
        {"key": "max_retries", "label": "Max Retries", "type": "number",
         "required": False, "default": "3"},
    ]

    def translate_batch(self, lines, source_lang, target_lang, glossary_entries=None):
        # Reuses existing _call_ollama, _parse_response, _has_cjk_hallucination
        # Constructs prompt using build_prompt_with_glossary
        ...

    def health_check(self):
        # Reuses existing check_ollama_health
        ...
```

### DeepL Backend
```python
# Source: deepl Python SDK v1.28.0 (https://github.com/DeepLcom/deepl-python)

import deepl

class DeepLBackend(TranslationBackend):
    name = "deepl"
    display_name = "DeepL"
    supports_glossary = True  # Native glossary API
    supports_batch = True
    max_batch_size = 50  # DeepL limit: 50 texts per request, 128KB total

    config_fields = [
        {"key": "api_key", "label": "API Key", "type": "password", "required": True,
         "default": "", "help": "DeepL API key (Free keys end with :fx)"},
    ]

    def __init__(self, **config):
        super().__init__(**config)
        self._client = None
        self._glossary_cache = {}  # {(source, target): glossary_id}

    def _get_client(self):
        if not self._client:
            api_key = self.config.get("api_key", "")
            if not api_key:
                raise RuntimeError("DeepL API key not configured")
            self._client = deepl.DeepLClient(auth_key=api_key)
        return self._client

    def translate_batch(self, lines, source_lang, target_lang, glossary_entries=None):
        client = self._get_client()

        # Map ISO 639-1 to DeepL language codes
        source = _to_deepl_lang(source_lang)
        target = _to_deepl_lang(target_lang)

        kwargs = {"source_lang": source, "target_lang": target}

        # Handle glossary if available
        if glossary_entries and self.supports_glossary:
            glossary = self._get_or_create_glossary(
                source, target, glossary_entries
            )
            if glossary:
                kwargs["glossary"] = glossary

        results = client.translate_text(lines, **kwargs)
        translated = [r.text for r in results]

        return TranslationResult(
            translated_lines=translated,
            backend_name=self.name,
            characters_used=sum(len(l) for l in lines),
        )

    def health_check(self):
        try:
            client = self._get_client()
            usage = client.get_usage()
            plan = "Free" if self.config.get("api_key", "").endswith(":fx") else "Pro"
            return True, f"OK ({plan}, {usage.character.count}/{usage.character.limit} chars)"
        except Exception as e:
            return False, str(e)

    def get_usage(self):
        try:
            client = self._get_client()
            usage = client.get_usage()
            return {
                "characters_used": usage.character.count,
                "characters_limit": usage.character.limit,
                "plan": "Free" if self.config.get("api_key", "").endswith(":fx") else "Pro",
            }
        except Exception:
            return {}

def _to_deepl_lang(iso_code):
    """Map ISO 639-1 to DeepL language codes."""
    # DeepL uses uppercase and some variants (EN-GB, EN-US, PT-BR, PT-PT)
    mapping = {
        "en": "EN",  # Will be EN-US or EN-GB based on context
        "de": "DE",
        "fr": "FR",
        "es": "ES",
        "it": "IT",
        "ja": "JA",
        "zh": "ZH",
        "ko": "KO",
        "pt": "PT-BR",  # Default to Brazilian Portuguese
        "ru": "RU",
        "pl": "PL",
        "nl": "NL",
        "sv": "SV",
        "da": "DA",
        "fi": "FI",
        "cs": "CS",
        "hu": "HU",
        "tr": "TR",
    }
    return mapping.get(iso_code, iso_code.upper())
```

### LibreTranslate Backend
```python
# Source: LibreTranslate API docs (https://docs.libretranslate.com/guides/api_usage/)

import requests

class LibreTranslateBackend(TranslationBackend):
    name = "libretranslate"
    display_name = "LibreTranslate (Self-Hosted)"
    supports_glossary = False  # No native glossary support
    supports_batch = False  # One text per request
    max_batch_size = 1  # Translate one line at a time

    config_fields = [
        {"key": "url", "label": "LibreTranslate URL", "type": "text", "required": True,
         "default": "http://libretranslate:5000", "help": "LibreTranslate API endpoint"},
        {"key": "api_key", "label": "API Key (optional)", "type": "password",
         "required": False, "default": "", "help": "Only needed for public instances"},
        {"key": "request_timeout", "label": "Timeout (seconds)", "type": "number",
         "required": False, "default": "30"},
    ]

    def translate_batch(self, lines, source_lang, target_lang, glossary_entries=None):
        url = self.config.get("url", "").rstrip("/")
        api_key = self.config.get("api_key", "")
        timeout = int(self.config.get("request_timeout", 30))

        translated = []
        for line in lines:
            payload = {
                "q": line,
                "source": source_lang,
                "target": target_lang,
                "format": "text",
            }
            if api_key:
                payload["api_key"] = api_key

            resp = requests.post(
                f"{url}/translate",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            translated.append(data.get("translatedText", line))

        return TranslationResult(
            translated_lines=translated,
            backend_name=self.name,
            characters_used=sum(len(l) for l in lines),
        )

    def health_check(self):
        url = self.config.get("url", "").rstrip("/")
        try:
            resp = requests.get(f"{url}/languages", timeout=10)
            if resp.status_code == 200:
                langs = resp.json()
                return True, f"OK ({len(langs)} languages available)"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)
```

### OpenAI-Compatible Backend
```python
# Source: openai Python SDK (https://github.com/openai/openai-python)

from openai import OpenAI

class OpenAICompatBackend(TranslationBackend):
    name = "openai_compat"
    display_name = "OpenAI-Compatible (OpenAI, Azure, LM Studio, vLLM)"
    supports_glossary = True  # Via prompt injection
    supports_batch = True
    max_batch_size = 25  # Same as Ollama default; LLMs have context limits

    config_fields = [
        {"key": "api_key", "label": "API Key", "type": "password", "required": True,
         "default": "", "help": "API key (or 'lm-studio' for LM Studio)"},
        {"key": "base_url", "label": "Base URL", "type": "text", "required": True,
         "default": "https://api.openai.com/v1",
         "help": "API endpoint (e.g. http://localhost:1234/v1 for LM Studio)"},
        {"key": "model", "label": "Model", "type": "text", "required": True,
         "default": "gpt-4o-mini", "help": "Model name as listed by the endpoint"},
        {"key": "temperature", "label": "Temperature", "type": "number",
         "required": False, "default": "0.3"},
        {"key": "request_timeout", "label": "Timeout (seconds)", "type": "number",
         "required": False, "default": "120"},
        {"key": "max_retries", "label": "Max Retries", "type": "number",
         "required": False, "default": "3"},
    ]

    def __init__(self, **config):
        super().__init__(**config)
        self._client = None

    def _get_client(self):
        if not self._client:
            self._client = OpenAI(
                api_key=self.config.get("api_key", ""),
                base_url=self.config.get("base_url", "https://api.openai.com/v1"),
                timeout=float(self.config.get("request_timeout", 120)),
                max_retries=int(self.config.get("max_retries", 3)),
            )
        return self._client

    def translate_batch(self, lines, source_lang, target_lang, glossary_entries=None):
        client = self._get_client()

        # Build prompt (reuse build_prompt_with_glossary pattern from ollama_client)
        from translation.llm_utils import build_translation_prompt, parse_llm_response

        prompt = build_translation_prompt(
            lines, source_lang, target_lang, glossary_entries
        )

        completion = client.chat.completions.create(
            model=self.config.get("model", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=float(self.config.get("temperature", 0.3)),
        )

        response_text = completion.choices[0].message.content.strip()
        parsed = parse_llm_response(response_text, len(lines))

        if parsed is None:
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                error=f"Line count mismatch in response",
                success=False,
            )

        return TranslationResult(
            translated_lines=parsed,
            backend_name=self.name,
            characters_used=sum(len(l) for l in lines),
        )

    def health_check(self):
        try:
            client = self._get_client()
            models = client.models.list()
            model_names = [m.id for m in models.data[:10]]
            target_model = self.config.get("model", "")
            found = target_model in model_names
            if found:
                return True, f"OK (model '{target_model}' available)"
            return False, f"Model '{target_model}' not found. Available: {model_names}"
        except Exception as e:
            return False, str(e)
```

### Google Cloud Translation Backend
```python
# Source: google-cloud-translate SDK (https://googleapis.dev/python/translation/latest/)

from google.cloud import translate_v3

class GoogleTranslateBackend(TranslationBackend):
    name = "google"
    display_name = "Google Cloud Translation"
    supports_glossary = True  # Native glossary API
    supports_batch = True
    max_batch_size = 1024  # Google supports up to 1024 texts

    config_fields = [
        {"key": "project_id", "label": "Google Cloud Project ID", "type": "text",
         "required": True, "default": ""},
        {"key": "credentials_path", "label": "Service Account JSON Path",
         "type": "text", "required": False, "default": "",
         "help": "Path to service account key file (or set GOOGLE_APPLICATION_CREDENTIALS)"},
        {"key": "location", "label": "Location", "type": "text",
         "required": False, "default": "global", "help": "GCP location (default: global)"},
    ]

    def translate_batch(self, lines, source_lang, target_lang, glossary_entries=None):
        client = translate_v3.TranslationServiceClient()
        parent = f"projects/{self.config['project_id']}/locations/{self.config.get('location', 'global')}"

        response = client.translate_text(
            request={
                "parent": parent,
                "contents": lines,
                "mime_type": "text/plain",
                "source_language_code": source_lang,
                "target_language_code": target_lang,
            }
        )

        translated = [t.translated_text for t in response.translations]

        return TranslationResult(
            translated_lines=translated,
            backend_name=self.name,
            characters_used=sum(len(l) for l in lines),
        )

    def health_check(self):
        try:
            client = translate_v3.TranslationServiceClient()
            parent = f"projects/{self.config['project_id']}/locations/{self.config.get('location', 'global')}"
            response = client.get_supported_languages(
                request={"parent": parent}
            )
            return True, f"OK ({len(response.languages)} languages)"
        except Exception as e:
            return False, str(e)
```

### Database Schema Extension for Backend Metrics
```sql
-- New table: translation_backend_stats (parallels provider_stats)
CREATE TABLE IF NOT EXISTS translation_backend_stats (
    backend_name TEXT PRIMARY KEY,
    total_requests INTEGER DEFAULT 0,
    successful_translations INTEGER DEFAULT 0,
    failed_translations INTEGER DEFAULT 0,
    total_characters INTEGER DEFAULT 0,
    avg_response_time_ms REAL DEFAULT 0,
    last_response_time_ms REAL DEFAULT 0,
    last_success_at TEXT,
    last_failure_at TEXT,
    last_error TEXT DEFAULT '',
    consecutive_failures INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Add backend selection to language_profiles
-- Migration: ALTER TABLE language_profiles ADD COLUMN translation_backend TEXT DEFAULT 'ollama';
-- Migration: ALTER TABLE language_profiles ADD COLUMN fallback_chain_json TEXT DEFAULT '["ollama"]';
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ollama-only translation | Multi-backend with fallback | This phase | Users choose best service per language pair; DeepL for European languages, LLM for anime-specific terms |
| Single prompt template | Per-backend prompts (LLM) + native API (API backends) | This phase | LLM backends use prompts; API backends get clean text |
| Global translation config | Per-profile backend selection | This phase | Different series can use different backends |
| ollama_client.py module functions | TranslationBackend ABC + instances | This phase | Clean separation, testable, extensible |
| Hardcoded hallucination detection | Shared LLM utilities (Ollama + OpenAI) | This phase | CJK detection, line count validation reused across LLM backends |
| DeepL v2 glossary API | DeepL v3 multilingual glossary | 2025 | One glossary supports multiple language pairs |
| deepl.Translator class | deepl.DeepLClient class | 2025 (SDK v1.20+) | DeepLClient is the new recommended entry point |

**Deprecated/outdated:**
- **deepl.Translator:** Replaced by `deepl.DeepLClient` in SDK v1.20+. Use `DeepLClient` for new code.
- **Google Cloud Translation v2 (Basic):** v3 (Advanced) is current; supports glossaries and batch translation that v2 does not.
- **OpenAI Completions API:** Legacy `/v1/completions` is deprecated; use Chat Completions (`/v1/chat/completions`) for all LLM translation.

## Open Questions

1. **Prompt Template Per Backend or Shared**
   - What we know: The existing system has a single prompt template (from prompt_presets). LLM backends (Ollama, OpenAI-compatible) need prompts. API backends (DeepL, LibreTranslate, Google) do not.
   - What's unclear: Should LLM backends share the same prompt template, or should each have its own? Different models may respond differently to the same prompt.
   - Recommendation: Use a shared prompt template system from prompt_presets for now (existing infrastructure), but allow per-backend prompt override as an optional config field. Start simple, extend later.

2. **Glossary Sync Between DeepL and Google**
   - What we know: Both DeepL and Google have native glossary APIs that store glossaries server-side. Sublarr stores glossary entries in the `glossary_entries` table per series.
   - What's unclear: Should Sublarr automatically sync local glossary entries to DeepL/Google glossaries? Or just pass terms per-request?
   - Recommendation: For DeepL, create glossaries on demand (cache the glossary ID). For Google, pass glossary terms per-request if the inline glossary feature is available, otherwise create GCS-based glossaries. Do NOT try to keep all glossary systems in sync -- it is too complex for initial implementation. LLM backends use prompt injection for glossaries (existing pattern works well).

3. **LibreTranslate Performance with Per-Line Translation**
   - What we know: LibreTranslate's `/translate` endpoint handles one text block per request. A 300-line subtitle file means 300 HTTP requests.
   - What's unclear: Can we batch lines into a single text block with newline separators and split the response? Would that preserve line count?
   - Recommendation: Start with per-line translation (safe, guaranteed line count match). Add a config option for "batch mode" that joins lines with `\n`, sends as one request, and splits the response. Test with common LibreTranslate models to verify line preservation.

4. **Existing Ollama Config Migration**
   - What we know: Current config has `ollama_url`, `ollama_model`, `temperature`, `batch_size`, `request_timeout`, `max_retries`, `backoff_base` as Pydantic Settings fields. The new system stores backend config in `config_entries`.
   - What's unclear: Should we migrate existing Pydantic fields to config_entries, or keep them as fallbacks?
   - Recommendation: Keep Pydantic fields as defaults. On first startup after migration, if `backend.ollama.*` keys do not exist in config_entries, populate them from the Pydantic settings values. This ensures existing installations keep working without reconfiguration. The Ollama backend reads from config_entries first, falls back to Pydantic fields.

5. **Translation Config Hash for Re-Translation**
   - What we know: Currently `get_translation_config_hash()` hashes `ollama_model|prompt_template|target_language`. With multi-backend, the hash should include the backend name and its config.
   - What's unclear: How to handle re-translation detection when users switch backends. Should changing backends invalidate all previous translations?
   - Recommendation: Include backend name in the config hash: `backend_name|model_or_service_id|target_language`. Changing backends will naturally produce a different hash, showing all previous translations as "outdated" in the re-translate UI. This is the correct behavior -- users who switch backends likely want re-translation.

## Sources

### Primary (HIGH confidence)
- Sublarr codebase: `backend/ollama_client.py` (current Ollama integration, 339 lines)
- Sublarr codebase: `backend/translator.py` (current translation pipeline, 886 lines)
- Sublarr codebase: `backend/config.py` (current Settings model)
- Sublarr codebase: `backend/db/__init__.py` (schema DDL, 390 lines)
- Sublarr codebase: `backend/db/profiles.py` (language profile operations)
- Sublarr codebase: `backend/providers/base.py` (SubtitleProvider ABC -- pattern reference)
- [DeepL Python SDK v1.28.0](https://github.com/DeepLcom/deepl-python) - Official SDK, glossary API, text translation
- [DeepL API Reference](https://developers.deepl.com/api-reference/translate) - 50 texts/request, 128KB limit
- [LibreTranslate API Docs](https://docs.libretranslate.com/guides/api_usage/) - REST API, /translate endpoint
- [OpenAI Python SDK](https://github.com/openai/openai-python) - base_url parameter for compatible endpoints
- [Google Cloud Translation v3](https://cloud.google.com/translate/docs/intro-to-v3) - glossary support, batch translate

### Secondary (MEDIUM confidence)
- [LM Studio OpenAI Compatibility](https://lmstudio.ai/docs/developer/openai-compat) - OpenAI-compatible endpoint behavior
- [deepl PyPI](https://pypi.org/project/deepl/) - Version 1.28.0, Python 3.9-3.13, requires requests>=2.32.4
- [google-cloud-translate PyPI](https://pypi.org/project/google-cloud-translate/) - Version 3.x, GCS glossary management
- Prior Phase 1 Research: Plugin config storage pattern (`plugin.<name>.<key>` in config_entries)
- Prior Phase 0 Architecture: Application Factory, Blueprint routing, db/ package structure

### Tertiary (LOW confidence)
- LibreTranslate batch translation capability -- No official batch endpoint documented; per-line translation is safe approach
- Google Cloud Translation inline glossary (without GCS) -- needs verification against current API version
- vLLM OpenAI compatibility edge cases -- based on community reports, not official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries are official SDKs from their respective providers; versions verified against PyPI
- Architecture: HIGH - ABC pattern directly mirrors the proven SubtitleProvider pattern from Phase 1; TranslationManager follows ProviderManager pattern
- Backend APIs: HIGH for DeepL, OpenAI (official SDKs with good docs); MEDIUM for LibreTranslate (simple REST, no official Python client); MEDIUM for Google Cloud (SDK is solid but credential management is complex)
- Pitfalls: HIGH - Based on real issues in the existing Ollama integration (CJK hallucination, line count mismatch) and documented API limitations (DeepL 50-text limit, batch size differences)
- Database schema: HIGH - Follows existing patterns (provider_stats table, config_entries namespacing, language_profiles columns)

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (30 days; translation API surfaces are stable, library versions may update but patterns remain valid)
