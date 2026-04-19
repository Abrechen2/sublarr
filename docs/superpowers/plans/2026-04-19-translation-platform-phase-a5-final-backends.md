# Translation Platform / Phase A5 — Azure + Mistral + MyMemory + ChatGPT

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Spec:** `docs/superpowers/specs/2026-04-19-translation-platform-lingarr-parity-design.md`
**Prior:** Phase A4 shipped as 0.62.0-beta.

**Goal:** Final 4 backends. After A5, Sublarr has 12 translation backends — Lingarr parity reached.

**Architecture:**
- **Mistral** + **ChatGPT** are LLMs → inherit `LLMBackend`, OpenAI-compat shape (like `DeepSeekBackend` from A3)
- **Azure Translator** + **MyMemory** are char-priced → inherit `TranslationBackend` directly (not LLMBackend), use `calculate_char_cost_micro_usd`

**Baseline:** 0.62.0-beta → 0.63.0-beta (final Plan A minor bump).

---

## Tasks (one backend per task, then registration + deploy)

### Task 1: MistralBackend

OpenAI-compat endpoint at `https://api.mistral.ai/v1/chat/completions`, models `mistral-large-latest`, `mistral-small-latest`.

Pattern: near-identical to `DeepSeekBackend` — just different URL + class name + default model. 9 tests, mostly copy-adapt.

**Files:** `backend/translation/mistral.py`, `backend/tests/test_mistral_backend.py`. Commit: `feat(translation-a5): add MistralBackend`.

### Task 2: ChatGPTBackend

OpenAI-compat endpoint at `https://api.openai.com/v1/chat/completions`, default model `gpt-4o-mini`. Distinct from `OpenAICompatBackend` (which accepts any compatible base URL — this one is OpenAI-only).

**Note:** if this duplicates `OpenAICompatBackend` too much, the distinction is: `OpenAICompatBackend` is generic for any OpenAI-compatible self-hosted (LocalAI, OpenRouter, LiteLLM), while `ChatGPTBackend` is the opinionated "just use OpenAI" default. Users who don't want to configure base_url pick ChatGPT.

**Files:** `backend/translation/chatgpt.py`, `backend/tests/test_chatgpt_backend.py`. Commit: `feat(translation-a5): add ChatGPTBackend`.

### Task 3: AzureTranslatorBackend

Char-priced. Inherits `TranslationBackend` directly (NOT LLMBackend).

Endpoint: `https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&to=<target>`
Auth headers: `Ocp-Apim-Subscription-Key: <key>`, `Ocp-Apim-Subscription-Region: <region>`
Request body: `[{"text": "line 1"}, {"text": "line 2"}, ...]`
Response: `[{"translations": [{"text": "...", "to": "de"}]}, ...]`

Cost via `calculate_char_cost_micro_usd(chars_in, price_per_1m=Decimal("10.00"))`.

Config fields: `api_key` (password), `region` (text, default `westeurope`).

**Files:** `backend/translation/azure_translator.py`, `backend/tests/test_azure_translator_backend.py`. ~8-10 tests. Commit: `feat(translation-a5): add AzureTranslatorBackend (char-priced)`.

### Task 4: MyMemoryBackend

Char-priced free tier. Inherits `TranslationBackend`.

Endpoint: `https://api.mymemory.translated.net/get?q=<text>&langpair=<src>|<tgt>` (GET)
Auth: none for free tier (email optional to raise quota)
Per-line: one HTTP call per line (API doesn't do batch). Rate limit on free tier: 1000 words/day per IP.

Cost: 0 (free tier). `calculate_char_cost_micro_usd(chars_in, price_per_1m=Decimal("0"))` always returns 0.

Config fields: `email` (text, optional — raises daily limit when present).

**Files:** `backend/translation/mymemory.py`, `backend/tests/test_mymemory_backend.py`. ~8 tests. Commit: `feat(translation-a5): add MyMemoryBackend (free tier)`.

### Task 5: Register all 4 with TranslationManager

Modify `backend/translation/__init__.py::_register_builtin_backends()` — add 4 more `register_backend` calls, each wrapped in `try/except ImportError` per A3 pattern.

Smoke-test: `mgr.get_all_backends()` shows 12 backends (5 LLM + 7 others).

**Commit:** `feat(translation-a5): register Mistral+ChatGPT+Azure+MyMemory with TranslationManager`.

### Task 6: Acceptance + merge + deploy

- Full suite green
- Merge to master
- Bump to 0.63.0-beta
- Changelog documents all 4 new backends + Plan A completion
- Build + push Docker
- Deploy to Cardinal
- Verify 12 backends in prod
- Cleanup worktree + branch

## Phase A5 acceptance checklist

- [ ] 4 new backend classes, each with ~9 tests (36 total)
- [ ] Mistral + ChatGPT inherit LLMBackend; Azure + MyMemory inherit TranslationBackend
- [ ] Cost tracking: Mistral/ChatGPT via token math, Azure/MyMemory via char math
- [ ] Config fields: all 4 backends have api_key (or email for MyMemory) + optional model/region
- [ ] All 12 backends registered + visible via `mgr.get_all_backends()`
- [ ] No regressions in existing scheduler/translation suites
- [ ] Deployed to prod, health OK

## Plan A complete after A5 ships

After this phase: Sublarr has full Lingarr parity on translation backends, persistent cost tracking, live queue dashboard, concurrency control per backend, context-windowing for LLM coherence. The entire Plan A roadmap (brainstormed 2026-04-19) is shipped.

Next: Plan B (Bazarr-grade subtitle delivery quality, memory `project_plan_b_subtitle_delivery_quality`).
