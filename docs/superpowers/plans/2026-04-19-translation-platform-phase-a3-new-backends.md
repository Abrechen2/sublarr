# Translation Platform / Phase A3 — Claude + Gemini + DeepSeek

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]` checkbox syntax.

**Spec:** `docs/superpowers/specs/2026-04-19-translation-platform-lingarr-parity-design.md`
**Prior phase:** `docs/superpowers/plans/2026-04-19-translation-platform-phase-a2-queue.md` (deployed as 0.60.0-beta)

**Goal:** Ship three high-value LLM translation backends (Anthropic Claude, Google Gemini, DeepSeek) on top of the `LLMBackend` base class established in A1. Each backend is a ~120-LOC subclass implementing three hooks. After A3, users can pick from 5 LLM backends (Ollama + OpenAI-compat + new three) plus 3 char-priced backends (DeepL + Google Translate + LibreTranslate).

**Architecture:** Three new subclasses of `LLMBackend` in `backend/translation/`. Each implements `_build_request`, `_call_api`, `_parse_response` per its provider API. Prices already in `price_sheet.py` from A1. Dynamic backend registration via `TranslationManager.register_backend` already wires concurrency + cost tracking + event logging for free.

**Tech Stack:** `anthropic` SDK (Claude), `requests` (Gemini REST + DeepSeek OpenAI-compat), existing `LLMBackend` base.

**Dependencies:** Phase A2 (0.60.0-beta) deployed. `LLMBackend` exists. `price_sheet.py` has Claude/Gemini/DeepSeek entries.

**Baseline version:** 0.60.0-beta. Ships as minor bump → 0.61.0-beta.

---

## File structure

### New backend files
- `backend/translation/claude.py` — `ClaudeBackend(LLMBackend)` (~140 LOC incl. Anthropic API shape)
- `backend/translation/gemini.py` — `GeminiBackend(LLMBackend)` (~130 LOC; REST API, no SDK dep)
- `backend/translation/deepseek.py` — `DeepSeekBackend(LLMBackend)` (~100 LOC; OpenAI-compat shape)
- `backend/tests/test_claude_backend.py` (~10 tests)
- `backend/tests/test_gemini_backend.py` (~10 tests)
- `backend/tests/test_deepseek_backend.py` (~10 tests)

### Modified backend files
- `backend/requirements.txt` — add `anthropic>=0.39`
- `backend/translation/__init__.py` — `TranslationManager.__init__` discovers + registers the three new backends

### Frontend — none (backends discover via existing `/concurrency` endpoint; BackendCard is already generic). i18n adds display-name strings only.

### Modified frontend files
- `frontend/src/i18n/locales/{de,en}/settings.json` — add display-name strings for the three backends if not auto-provided by backend API

---

## Task 1: Add anthropic SDK dep

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1:** Open `backend/requirements.txt`. Add in alphabetical position (between `anidb` or wherever `a`-prefixed packages sit):

```
anthropic>=0.39,<1.0
```

- [ ] **Step 2:** Install in venv.

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a3-backends
/d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt 2>&1 | tail -5
```

- [ ] **Step 3:** Smoke-test import.

```bash
/d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -c "import anthropic; print('anthropic', anthropic.__version__)"
```

Gemini uses plain REST (no SDK added). DeepSeek uses OpenAI-compat endpoint — no new dep.

- [ ] **Step 4:** Commit.

```bash
git add backend/requirements.txt
git commit -m "feat(translation-a3): add anthropic SDK dependency"
```

---

## Task 2: ClaudeBackend

**Files:**
- Create: `backend/translation/claude.py`
- Create: `backend/tests/test_claude_backend.py`

- [ ] **Step 1: Write failing tests** covering:
  - Request shape — system prompt split from messages (Anthropic's unique shape)
  - Cost math uses claude-sonnet-4-6 pricing from price_sheet
  - Token count parsed from `usage.input_tokens` + `usage.output_tokens`
  - Content-filter finish_reason `stop_reason=refusal` → `ContentFilterError`
  - Missing API key → clear `ValueError` at construction
  - `test_api_call_uses_anthropic_client` (mock `anthropic.Anthropic`)
  - Default model `claude-sonnet-4-6`
  - `supports_glossary=True`, `supports_batch=True`, `max_batch_size=50`

Create `backend/tests/test_claude_backend.py`:

```python
"""ClaudeBackend tests — mocked Anthropic client."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings
    reload_settings()
    from app import create_app
    app = create_app(testing=True)
    from extensions import db as sa_db
    with app.app_context():
        sa_db.create_all()
    yield app


@pytest.fixture
def reset_conc():
    from translation.concurrency import reset_for_tests
    reset_for_tests()


def _claude(api_key="sk-test", model="claude-sonnet-4-6"):
    from translation.claude import ClaudeBackend
    return ClaudeBackend(api_key=api_key, model=model)


def test_construction_requires_api_key():
    from translation.claude import ClaudeBackend

    with pytest.raises(ValueError, match="api_key"):
        ClaudeBackend(api_key="", model="claude-sonnet-4-6")


def test_default_model_and_prices():
    from translation.claude import ClaudeBackend

    b = ClaudeBackend(api_key="sk-test", model="claude-sonnet-4-6")
    assert b.name == "claude"
    assert b.default_model == "claude-sonnet-4-6"
    assert b.cost_per_1m_tokens_in == Decimal("3.00")
    assert b.cost_per_1m_tokens_out == Decimal("15.00")
    assert b.supports_glossary is True
    assert b.supports_batch is True
    assert b.max_batch_size == 50


def test_build_request_splits_system_from_messages():
    """Anthropic wants system as a separate param, not inside messages."""
    b = _claude()
    messages = [
        {"role": "system", "content": "translate to de"},
        {"role": "user", "content": "hello"},
    ]
    payload = b._build_request(messages, max_tokens=500)
    assert payload["system"] == "translate to de"
    # messages array must NOT contain the system message
    assert all(m["role"] != "system" for m in payload["messages"])
    assert payload["max_tokens"] == 500
    assert payload["model"] == "claude-sonnet-4-6"


def test_parse_response_extracts_tokens():
    from translation.llm_base import LLMResponse

    b = _claude()
    raw = {
        "content": [{"type": "text", "text": "hallo\nwelt"}],
        "usage": {"input_tokens": 30, "output_tokens": 20},
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
    }
    resp = b._parse_response(raw)
    assert isinstance(resp, LLMResponse)
    assert resp.translations == ["hallo", "welt"]
    assert resp.tokens_in == 30
    assert resp.tokens_out == 20
    assert resp.finish_reason == "end_turn"


def test_parse_response_refusal_surfaces_as_content_filter():
    b = _claude()
    raw = {
        "content": [{"type": "text", "text": "I cannot do that"}],
        "usage": {"input_tokens": 10, "output_tokens": 10},
        "model": "claude-sonnet-4-6",
        "stop_reason": "refusal",
    }
    resp = b._parse_response(raw)
    # Surface as content_filter so LLMBackend raises ContentFilterError
    assert resp.finish_reason == "content_filter"


def test_call_api_uses_anthropic_client():
    b = _claude()
    fake_resp = MagicMock()
    fake_resp.model_dump.return_value = {
        "content": [{"type": "text", "text": "hi"}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
    }
    with patch("translation.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_resp
        mock_cls.return_value = mock_client
        b._client = None  # force re-init
        raw = b._call_api(
            {"model": "claude-sonnet-4-6", "system": "x",
             "messages": [{"role": "user", "content": "y"}],
             "max_tokens": 100},
            timeout_s=60,
        )
    assert raw["content"][0]["text"] == "hi"


def test_cost_calculation_matches_price_sheet():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    b = _claude()
    # 1000 tokens in @ $3/1M = $0.003 = 3000 micro_usd
    # 500 tokens out @ $15/1M = $0.0075 = 7500 micro_usd
    cost = calculate_llm_cost_micro_usd(
        tokens_in=1000, tokens_out=500,
        price_in_per_1m=b.cost_per_1m_tokens_in,
        price_out_per_1m=b.cost_per_1m_tokens_out,
    )
    assert cost == 10500


def test_config_fields_present():
    b = _claude()
    field_names = {f["name"] if isinstance(f, dict) else f.name for f in b.config_fields}
    assert "api_key" in field_names
    assert "model" in field_names


def test_end_to_end_with_mock(app, reset_conc):
    """translate_batch happy path with mocked anthropic."""
    from translation.concurrency import get_concurrency

    get_concurrency().register("claude", 2)
    b = _claude()

    fake_resp = MagicMock()
    fake_resp.model_dump.return_value = {
        "content": [{"type": "text", "text": "hallo\nwelt\ntest"}],
        "usage": {"input_tokens": 30, "output_tokens": 20},
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
    }
    with patch("translation.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_resp
        mock_cls.return_value = mock_client
        b._client = None
        with app.app_context():
            result = b.translate_batch(
                ["hi", "world", "test"],
                source_lang="en", target_lang="de",
            )
    assert result.success is True
    assert result.translated_lines == ["hallo", "welt", "test"]
```

- [ ] **Step 2:** Run — expect FAIL (ImportError).

- [ ] **Step 3:** Create `backend/translation/claude.py`:

```python
"""Anthropic Claude translation backend.

Inherits from LLMBackend; implements the three provider hooks for
Anthropic's Messages API (system param separate from messages list).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import anthropic

from translation.config_fields import ConfigField  # if this exists; otherwise inline
from translation.llm_base import LLMBackend, LLMResponse
from translation.price_sheet import get_llm_price

logger = logging.getLogger(__name__)


class ClaudeBackend(LLMBackend):
    """Anthropic Claude translation backend."""

    name = "claude"
    display_name = "Anthropic Claude"
    default_model = "claude-sonnet-4-6"
    timeout_s = 120
    supports_glossary = True
    supports_batch = True
    max_batch_size = 50

    # Placeholder prices; set per-instance in __init__
    cost_per_1m_tokens_in = Decimal("3.00")
    cost_per_1m_tokens_out = Decimal("15.00")

    config_fields = [
        {"name": "api_key", "type": "password", "label": "API Key", "required": True},
        {"name": "model", "type": "text", "label": "Model", "required": False,
         "default": "claude-sonnet-4-6"},
    ]

    def __init__(self, api_key: str, model: str | None = None, **_: Any) -> None:
        if not api_key:
            raise ValueError("ClaudeBackend: api_key is required")
        self.api_key = api_key
        self._model = model or self.default_model
        self.cost_per_1m_tokens_in, self.cost_per_1m_tokens_out = get_llm_price(
            self.name, self._model
        )
        self._client: anthropic.Anthropic | None = None

    @property
    def model(self) -> str:
        return self._model

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        """Anthropic wants system as a separate top-level param.

        Split the first system message out of the messages list.
        """
        system = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                user_messages.append(m)
        return {
            "model": self._model,
            "system": system,
            "messages": user_messages,
            "max_tokens": max_tokens,
        }

    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        client = self._get_client()
        resp = client.messages.create(
            model=payload["model"],
            system=payload["system"],
            messages=payload["messages"],
            max_tokens=payload["max_tokens"],
            timeout=float(timeout_s),
        )
        return resp.model_dump()

    def _parse_response(self, raw: dict) -> LLMResponse:
        content_blocks = raw.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        lines = text.split("\n")
        usage = raw.get("usage", {})
        stop_reason = raw.get("stop_reason")
        # Map Anthropic-specific refusal to our generic content_filter sentinel
        if stop_reason == "refusal":
            stop_reason = "content_filter"
        return LLMResponse(
            translations=lines,
            tokens_in=int(usage.get("input_tokens", 0)),
            tokens_out=int(usage.get("output_tokens", 0)),
            model=raw.get("model", self._model),
            finish_reason=stop_reason,
            raw_latency_ms=0,
        )

    def health_check(self) -> tuple[bool, str]:
        """Optional: quick API-key-validity check."""
        try:
            self._get_client().messages.create(
                model=self._model,
                system="",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=10,
            )
            return True, "OK"
        except Exception as exc:
            return False, str(exc)
```

If `translation/config_fields.py` doesn't exist with `ConfigField` type, use plain dicts as shown. Read `backend/translation/ollama.py` to see how ollama declares `config_fields` — match whatever shape that uses.

- [ ] **Step 4:** Run tests — expect 9 passed.

- [ ] **Step 5:** Ruff + commit.

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a3-backends
ruff check backend/translation/claude.py backend/tests/test_claude_backend.py
git add backend/translation/claude.py backend/tests/test_claude_backend.py
git commit -m "feat(translation-a3): add ClaudeBackend (Anthropic)"
```

---

## Task 3: GeminiBackend

**Files:**
- Create: `backend/translation/gemini.py`
- Create: `backend/tests/test_gemini_backend.py`

Google Gemini via REST — no SDK dep. Endpoint: `https://generativelanguage.googleapis.com/v1/models/<model>:generateContent`. Auth: API key in query param.

- [ ] **Step 1: Write failing tests** following the same 9-10 test matrix as Claude (adjust for Gemini's `contents: [{role, parts: [{text}]}]` shape + `usageMetadata.promptTokenCount` / `candidatesTokenCount` fields + `finishReason` → "SAFETY" → content_filter mapping).

- [ ] **Step 2:** Create `backend/translation/gemini.py`:

Key points:
- `config_fields`: `api_key`, `model` (default `gemini-2.5-pro`)
- `_build_request`: convert OpenAI-style messages to Gemini's `{contents, systemInstruction}` shape. System messages → `systemInstruction: {parts: [{text}]}`. User messages → `contents: [{role: "user", parts: [{text}]}]`.
- `_call_api`: `requests.post(f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={api_key}", json=payload, timeout=timeout_s)`. Check `resp.raise_for_status()`. Return `resp.json()`.
- `_parse_response`: extract `candidates[0].content.parts[0].text`; split into lines; `tokens_in = usageMetadata.promptTokenCount`, `tokens_out = usageMetadata.candidatesTokenCount`. If `finishReason == "SAFETY"` → `content_filter`.
- `cost_per_1m_tokens_in/out` from `get_llm_price("gemini", model)` in `__init__`.

- [ ] **Step 3:** Run tests, commit.

```bash
git add backend/translation/gemini.py backend/tests/test_gemini_backend.py
git commit -m "feat(translation-a3): add GeminiBackend (Google)"
```

---

## Task 4: DeepSeekBackend

**Files:**
- Create: `backend/translation/deepseek.py`
- Create: `backend/tests/test_deepseek_backend.py`

DeepSeek uses OpenAI-compatible API — essentially same shape as existing `OpenAICompatBackend` but defaults to `api.deepseek.com/v1` and `deepseek-chat` model. Simplest implementation: subclass or parameter the existing OpenAI-compat pattern.

- [ ] **Step 1:** Tests — same matrix, simpler (shape matches OpenAI).

- [ ] **Step 2:** Create `backend/translation/deepseek.py`:

```python
"""DeepSeek translation backend — OpenAI-compatible API."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import requests

from translation.llm_base import LLMBackend, LLMResponse
from translation.price_sheet import get_llm_price

logger = logging.getLogger(__name__)


class DeepSeekBackend(LLMBackend):
    name = "deepseek"
    display_name = "DeepSeek"
    default_model = "deepseek-chat"
    timeout_s = 120
    supports_glossary = True
    supports_batch = True
    max_batch_size = 50

    cost_per_1m_tokens_in = Decimal("0.14")
    cost_per_1m_tokens_out = Decimal("0.28")

    config_fields = [
        {"name": "api_key", "type": "password", "label": "API Key", "required": True},
        {"name": "model", "type": "text", "label": "Model", "required": False,
         "default": "deepseek-chat"},
    ]

    def __init__(self, api_key: str, model: str | None = None, **_: Any) -> None:
        if not api_key:
            raise ValueError("DeepSeekBackend: api_key is required")
        self.api_key = api_key
        self._model = model or self.default_model
        self.cost_per_1m_tokens_in, self.cost_per_1m_tokens_out = get_llm_price(
            self.name, self._model
        )

    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        return {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_response(self, raw: dict) -> LLMResponse:
        msg = raw["choices"][0]["message"]["content"]
        lines = msg.split("\n")
        usage = raw.get("usage", {})
        return LLMResponse(
            translations=lines,
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            model=raw.get("model", self._model),
            finish_reason=raw["choices"][0].get("finish_reason"),
            raw_latency_ms=0,
        )
```

- [ ] **Step 3:** Tests + commit.

---

## Task 5: Register backends with TranslationManager

**Files:**
- Modify: `backend/translation/__init__.py`

- [ ] **Step 1:** Find where existing backends (Ollama, OpenAICompat, DeepL, Google, LibreTranslate) are auto-registered. Add imports + `register_backend` calls for the 3 new backends.

Each registration respects the existing pattern — lazy, tolerates missing API keys (backend is registered but marked `configured=false` until config set).

Example:
```python
from translation.claude import ClaudeBackend
from translation.gemini import GeminiBackend
from translation.deepseek import DeepSeekBackend

# In TranslationManager init or _register_default_backends:
self.register_backend(ClaudeBackend)
self.register_backend(GeminiBackend)
self.register_backend(DeepSeekBackend)
```

- [ ] **Step 2:** Run smoke-test — bootstrap app, assert `/api/v1/translation/concurrency` lists 5 LLM + 3 char = 8 backends.

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a3-backends/backend
SUBLARR_SCHEDULER_ROLE=disabled SUBLARR_DB_PATH=/tmp/sublarr_a3.db /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -c "
from app import create_app
app = create_app(testing=True)
with app.app_context():
    from translation import get_translation_manager
    mgr = get_translation_manager()
    names = [b['name'] for b in mgr.get_all_backends()]
    print('backends:', sorted(names))
"
```

Expected output includes `claude`, `gemini`, `deepseek`, `ollama`, `openai_compat`, `deepl`, `google_translate`, `libretranslate`.

- [ ] **Step 3:** Commit.

---

## Task 6: Frontend i18n for new display names

Backends surface their `display_name` via API so no code-level frontend change needed. But if the frontend has any i18n keys for backend display names, add them.

- [ ] **Step 1:** Grep frontend for existing backend display-name i18n keys (`backend.ollama.name`, etc.). Add entries for claude/gemini/deepseek if a pattern exists. Otherwise — skip this task entirely, the API's `display_name` is used directly.

- [ ] **Step 2:** If nothing to change, skip commit.

---

## Task 7: Acceptance + merge + deploy

- [ ] Full backend suite green (expect 246 + 30 new = 276+).
- [ ] Ruff clean.
- [ ] Frontend typecheck + vitest green.
- [ ] Merge to master.
- [ ] Bump VERSION → 0.61.0-beta.
- [ ] Changelog.
- [ ] Build + push Docker.
- [ ] Deploy to Cardinal.
- [ ] Prod verify: `/api/v1/translation/concurrency` shows 8 backends.
- [ ] Cleanup worktree + branch.

## Phase A3 acceptance checklist

- [ ] ClaudeBackend, GeminiBackend, DeepSeekBackend all registered at startup
- [ ] Each has unit tests (~9-10 per backend, ~30 total)
- [ ] Prices auto-loaded from price_sheet at construction time
- [ ] Each subclass implements 3 LLMBackend hooks correctly
- [ ] Health-check works (or absent gracefully)
- [ ] BackendCard in UI renders with api_key + model fields (auto-generated from config_fields)
- [ ] No regressions in existing scheduler/translation tests
