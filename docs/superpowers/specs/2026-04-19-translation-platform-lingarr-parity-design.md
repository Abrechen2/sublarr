# Translation Platform — Lingarr Parity Design

**Date:** 2026-04-19
**Status:** Approved design, awaiting implementation plan
**Part of:** V1 competitive-parity initiative (see
`docs/superpowers/specs/2026-04-18-v1-competitive-parity.md`)
**Baseline version:** 0.58.1-beta

## Summary

Extend Sublarr's translation stack from 5 backends to 12 (Lingarr-parity),
introduce persistent cost tracking, surface the existing Translation Memory
in the UI, add a live queue dashboard, and harden concurrency + context
handling for LLM-based backends. Translation becomes a first-class feature
instead of a side-effect of subtitle delivery.

## Decisions taken during brainstorming

| # | Question | Decision |
|---|---|---|
| 1 | Rollout sequencing | Telemetry first (A1), then queue (A2), then new backends (A3/A5), context-windowing in between (A4) |
| 2 | LLM backend abstraction | **`LLMBackend` base class** with 3 provider hooks (`_build_request` / `_call_api` / `_parse_response`). Rejected per-backend copy-paste (too much duplication) and LiteLLM vendor (too heavy for 4-5 backends) |
| — | Cost representation | **Integer micro-USD** (1 USD = 1 000 000) — float aggregation drifts over millions of rows |
| — | Price sheet | Code-owned (`price_sheet.py`), never configurable via UI, updated with version bumps |
| — | Per-backend concurrency | `threading.Semaphore` per backend name (not per instance), configurable via `translation_concurrency_<backend>` |
| — | Context-window policy | Default `lookback=10, lookahead=5` lines for LLM backends only; skipped for char-priced backends |

Guiding principles (per memory `feedback_no_shortcuts`):
design the full correctness surface — lifecycle, persistence, error
handling, observability, retention, security, tests — no
stripped-down MVPs. Applies to every phase of this rollout.

## Scope

### In scope

| Item | Phase |
|---|---|
| `translation_events` table + retention cron | A1 |
| `translation_memory.backend` column + UX | A1 |
| `LLMBackend` base class; `ollama` + `openai_compat` migrated to it | A1 |
| `BackendConcurrency` semaphore service | A1 |
| `cost_tracker` + `price_sheet` modules | A1 |
| Cost Dashboard UI + Translation Memory panel | A1 |
| Admin audit logging on all mutation endpoints | A1 |
| Queue dashboard (`/translation/queue`) + cancellation | A2 |
| Claude, Gemini, DeepSeek backends | A3 |
| Context-window pre-chunking (`context_windower`) | A4 |
| Azure, Mistral, MyMemory, ChatGPT-native backends | A5 |

### Out of scope

- Bazarr-style subtitle-matching improvements → separate Plan B
  (see memory `project_plan_b_subtitle_delivery_quality`).
- Real-time WebSocket push for queue updates — 3-second polling is adequate
  for 1-2 concurrent jobs.
- Provider-agnostic library (LiteLLM) — would pay off only at 20+
  providers; we're adding 7.
- Multi-tenant cost attribution — Sublarr is single-tenant per install.
- Currency conversion — dashboard shows USD everywhere; operators in other
  currencies convert themselves.

## Architecture

### Module layout

```
backend/
  translation/
    base.py                    existing; TranslationBackend ABC unchanged
    llm_base.py                NEW ~250 LOC  LLMBackend(TranslationBackend)
    ollama.py                  migrated to LLMBackend
    openai_compat.py           migrated to LLMBackend
    deepl_backend.py           unchanged (char-priced, not LLM)
    google_translate.py        unchanged
    libretranslate.py          unchanged
    claude.py                  NEW A3
    gemini.py                  NEW A3
    deepseek.py                NEW A3
    azure_translator.py        NEW A5 (char-priced; not LLM)
    mistral.py                 NEW A5
    mymemory.py                NEW A5 (free-tier; not LLM)
    chatgpt.py                 NEW A5
    concurrency.py             NEW ~100 LOC  per-backend Semaphore
    cost_tracker.py            NEW ~80 LOC   micro_usd math + retention
    price_sheet.py             NEW ~60 LOC   dict-of-tuples, no UI
    context_windower.py        NEW A4 ~70 LOC
  translator/
    events.py                  NEW ~90 LOC   writes translation_events
    queue_view.py              NEW A2 ~100 LOC
  db/
    models/
      translation.py           extend with TranslationEvent model
    migrations/versions/
      <A1>_translation_events.py        explicit schema + 4 indexes
      <A1>_translation_memory_backend.py extend TM with backend column
  routes/
    translation/
      events.py                NEW A1  GET /cost, /cost/by-backend,
                                       GET /memory/stats, POST /memory/purge
      concurrency.py           NEW A1  GET/PATCH concurrency limits
      queue.py                 NEW A2  GET /queue, POST /cancel
  monitoring/metrics.py        extend with 4 translation_* counters/histograms

frontend/src/
  pages/Settings/translation/
    CostDashboard.tsx          NEW A1 ~220 LOC
    TranslationMemoryPanel.tsx NEW A1 ~160 LOC
    QueueDashboard.tsx         NEW A2 ~200 LOC
    BackendCard.tsx            extend with concurrency slider + cost-cap
  api/translation.ts           extend with events/queue/cost/concurrency
  hooks/
    useTranslationEvents.ts    NEW A1
    useTranslationQueue.ts     NEW A2
    useTranslationCost.ts      NEW A1
    useTranslationMutations.ts NEW A1 (purge, cancel, concurrency PATCH)
```

### Rollout phasing

Five independent rollout phases, each shippable on its own. All phases add to
the existing codebase — no scheduled deletions (A1's LLMBackend migration
preserves ollama + openai_compat's public contract, only internal body moves).

| Phase | What ships | Version | Estimated effort |
|---|---|---|---|
| **A1** Telemetry foundation | `translation_events` table, `LLMBackend` base, concurrency semaphore, cost tracking, Cost Dashboard, TM Panel | minor | ~12 tasks |
| **A2** Queue Dashboard | `/translation/queue` endpoint, QueueDashboard page, cancellation | minor | ~8 tasks |
| **A3** Claude + Gemini + DeepSeek | three LLMBackend subclasses + their UI cards + i18n | minor | ~10 tasks |
| **A4** Context-windowing | `context_windower` + `LLMBackend` integration | patch | ~6 tasks |
| **A5** Azure + Mistral + MyMemory + ChatGPT | four new backends (mix of LLM + char-priced) | minor | ~14 tasks |

### Lifecycle wiring

- **Startup:** `TranslationManager.__init__` registers backends. `BackendConcurrency` reads `translation_concurrency_<backend>` from config_entries per registered backend, defaults 3. `cost_tracker` loads price sheet dict.
- **Shutdown:** `BackendConcurrency.shutdown()` releases all held slots (called from `app_shutdown.py` after scheduler shutdown). `TranslationManager` drains in-flight jobs via existing cancellation path.
- **Config save:** settings UI PATCH on `translation_concurrency_<backend>` immediately calls `BackendConcurrency.set_limit` without restart.

### Source-of-truth rules

- **Registered backends:** code (`TranslationManager._backend_classes`). Settings UI enables/disables and supplies credentials but never adds new backends.
- **Per-backend config:** `config_entries` namespace `backend.<name>.<key>` (existing pattern).
- **Concurrency limits:** `config_entries` key `translation_concurrency_<name>`.
- **Prompt presets:** `prompt_presets` table (existing).
- **Glossaries:** `glossary_entries` table (existing).
- **Price sheet:** code (`translation/price_sheet.py`) — never editable at runtime. Operators can't silently desync local prices from reality.
- **Fallback chains:** `language_profiles.fallback_chain` JSON field (existing).

## Data model

### New table — `translation_events`

One row per `translate_batch` call. Populated by
`translator/events.py::write_translation_event` invoked from inside
`LLMBackend.translate_batch` (after each API attempt, success or failure).

| Column | Type | Notes |
|---|---|---|
| `id` | `Integer` PK autoincrement | |
| `backend` | `String(32)` NOT NULL | backend.name, indexed |
| `source_lang` | `String(16)` NOT NULL | ISO 639-1 |
| `target_lang` | `String(16)` NOT NULL | ISO 639-1 |
| `lines_count` | `Integer` NOT NULL | batch size |
| `chars_in` | `Integer` NOT NULL | source chars — char-priced APIs |
| `chars_out` | `Integer` | NULL on failure |
| `tokens_in` | `Integer` | LLM only |
| `tokens_out` | `Integer` | LLM only |
| `cost_estimate_micro_usd` | `BigInteger` NOT NULL default 0 | 1 USD = 1 000 000 |
| `cache_hit` | `Boolean` NOT NULL default `false` | true iff served by TM |
| `latency_ms` | `Integer` | wall-clock |
| `status` | `String(16)` NOT NULL | `ok`/`error`/`timeout`/`circuit_open`/`rate_limit` |
| `error_type` | `String(128)` | exception class name |
| `error_msg` | `Text` | truncated to 4KB before write |
| `job_id` | `String(32)` | FK-less link to translation jobs |
| `started_at` | `DateTime(tz=True)` NOT NULL | |
| `finished_at` | `DateTime(tz=True)` | |

**Indexes:**
- `(backend, started_at)` — per-backend time-series for Cost Dashboard.
- `started_at` — retention `DELETE WHERE started_at < cutoff`.
- `status` — error-rate queries.
- `job_id` — job-scoped lookups.

### Extended table — `translation_memory`

Add nullable column:
- `backend` `String(32) NULL` — which backend produced the cache entry.

Writer populates on new inserts; reader tolerates NULL on pre-existing rows.
Enables "hit-rate per backend" stat on the TM panel.

### Retention policy

- Config: `translation_events_retention_days: int = Field(default=90, ge=7, le=365)`.
- New JobSpec `translation_events_cleanup` (nightly 03:30 UTC) — `delete_old_translation_events()` mirrors `delete_old_job_runs()` pattern from Phase 5.
- Upper bound: 90 days × ~1 000 events/day × ~200 B ≈ 18 MB; negligible.

### Migrations

One Alembic migration per phase, explicit (no autogenerate):
- `<A1>_translation_events.py` — creates `translation_events` + 4 indexes, adds `translation_memory.backend` column.
- `<A2>` — none; queue is transient.
- `<A3>/<A5>` — none; new backends don't add DB columns.

## LLMBackend base class

### Interface

```python
class LLMBackend(TranslationBackend, ABC):
    # subclass declares:
    name: str
    display_name: str
    config_fields: list[ConfigField]
    cost_per_1k_tokens_in: Decimal
    cost_per_1k_tokens_out: Decimal
    default_model: str
    supports_glossary: bool = True
    supports_batch: bool = True
    max_batch_size: int = 50

    # subclass implements:
    @abstractmethod
    def _build_request(self, messages: list[dict], max_tokens: int) -> dict: ...
    @abstractmethod
    def _call_api(self, payload: dict, timeout_s: int) -> dict: ...
    @abstractmethod
    def _parse_response(self, raw: dict) -> LLMResponse: ...

    # base provides (do not override):
    def translate_batch(self, lines, source_lang, target_lang,
                        glossary_entries=None) -> TranslationResult: ...
    def estimate_cost_micro_usd(self, resp: LLMResponse) -> int: ...
```

### `translate_batch` orchestration (in base)

```
1. with BackendConcurrency.slot(self.name, timeout_s=120):  # blocks if full
2.   chunks = context_windower.build_chunks(lines, ...)   # A4; no-op until then
3.   for chunk in chunks:
4.     messages = self._assemble_messages(chunk, glossary, preset)
5.     started = time.monotonic(); started_at = datetime.now(UTC)
6.     try:
7.       payload = self._build_request(messages, max_tokens)
8.       raw = self._call_api(payload, timeout_s=self.timeout_s)
9.       resp = self._parse_response(raw)
10.      self._verify_line_count(resp, chunk)   # retry once on mismatch
11.      cost = self.estimate_cost_micro_usd(resp)
12.      write_translation_event(status="ok", ..., cost=cost)
13.      yield resp.translations
14.    except (Timeout, RateLimitError, ContentFilterError, ApiError) as exc:
15.      write_translation_event(status="...", error_type=type(exc).__name__, ...)
16.      raise   # to translate_with_fallback, which advances chain
```

### Prompt assembly

`_assemble_messages(chunk, glossary, preset)` builds:
1. System message from `preset.system` + glossary-preamble + context sections (Phase A4).
2. User message with batch lines numbered.

Subclasses override only `_build_request` to reshape for their API — e.g. Anthropic splits `system` from `messages`; OpenAI keeps `{role: "system"}` in the list.

### `LLMResponse` dataclass

```python
@dataclass(frozen=True)
class LLMResponse:
    translations: list[str]
    tokens_in: int
    tokens_out: int
    model: str              # actual model id the backend used
    finish_reason: str | None  # 'stop'/'length'/'content_filter'/'tool_use'
    raw_latency_ms: int
```

### Migration of existing backends

`OllamaBackend` and `OpenAICompatBackend` inherit from `LLMBackend`
instead of `TranslationBackend`. Public contract preserved — external
callers see `backend.translate_batch(...)` identically. LOC drops from
~250 → ~130 per backend after migration.

`DeepLBackend`, `GoogleTranslateBackend`, `LibreTranslateBackend` remain
direct `TranslationBackend` subclasses (they're not LLMs — cost model
differs, no context window, no retry-on-line-count).

## Concurrency

### `BackendConcurrency` service

```python
class BackendConcurrency:
    def __init__(self):
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._limits: dict[str, int] = {}
        self._lock = threading.Lock()

    def register(self, backend_name: str, initial_limit: int) -> None: ...
    def set_limit(self, backend_name: str, limit: int) -> None: ...  # resizes
    def get_limit(self, backend_name: str) -> int: ...

    @contextmanager
    def slot(self, backend_name: str, timeout_s: float = 120.0):
        """Acquire slot (blocks up to timeout), yield, release. Raises
        ConcurrencyTimeoutError on timeout."""
```

**Resize semantics:** increasing limit releases N slots immediately. Decreasing limit doesn't evict in-flight workers — they release naturally; next N `acquire` calls block until enough slots free.

**Default per backend:** 3 slots (safe for all API providers; local Ollama can go much higher).

**Cache hits don't count** — `translate_with_fallback` checks TM before `slot(...)` — no semaphore acquire on hit.

### Config wiring

Config field is dynamic:
```python
# config_settings.py registers via a factory:
def _register_concurrency_fields(cls):
    for name in registered_backends():
        cls.__fields__[f"translation_concurrency_{name}"] = Field(
            default=3, ge=1, le=50,
            description=f"Concurrent {name} translation requests."
        )
```

UI: each `BackendCard` shows a slider bound to this config field. Debounced save → `PATCH /api/v1/translation/concurrency/<backend>` → `BackendConcurrency.set_limit`.

### Observability

- Prometheus gauge `translation_concurrency_in_use{backend}` — current active slots.
- Prometheus gauge `translation_concurrency_limit{backend}` — configured limit.
- Logged on each `ConcurrencyTimeoutError` at WARN.

## Cost tracking

### Price sheet

```python
# backend/translation/price_sheet.py
# USD per 1M tokens (in, out)
PRICE_SHEET_LLM: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("claude", "claude-sonnet-4-6"): (Decimal("3.00"), Decimal("15.00")),
    ("claude", "claude-opus-4-7"): (Decimal("15.00"), Decimal("75.00")),
    ("claude", "claude-haiku-4-5"): (Decimal("0.25"), Decimal("1.25")),
    ("gemini", "gemini-2.5-pro"): (Decimal("1.25"), Decimal("5.00")),
    ("gemini", "gemini-2.5-flash"): (Decimal("0.075"), Decimal("0.30")),
    ("deepseek", "deepseek-chat"): (Decimal("0.14"), Decimal("0.28")),
    ("deepseek", "deepseek-coder"): (Decimal("0.14"), Decimal("0.28")),
    ("openai_compat", "gpt-4o"): (Decimal("2.50"), Decimal("10.00")),
    ("openai_compat", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("chatgpt", "gpt-4o"): (Decimal("2.50"), Decimal("10.00")),
    ("mistral", "mistral-large-latest"): (Decimal("2.00"), Decimal("6.00")),
    ("mistral", "mistral-small-latest"): (Decimal("0.20"), Decimal("0.60")),
    ("ollama", "*"): (Decimal("0"), Decimal("0")),  # self-hosted free
}

# USD per 1M characters (char-priced)
PRICE_SHEET_CHARS: dict[str, Decimal] = {
    "deepl": Decimal("20.00"),
    "deepl_pro": Decimal("25.00"),
    "google_translate": Decimal("20.00"),
    "azure_translator": Decimal("10.00"),
    "libretranslate": Decimal("0"),
    "mymemory": Decimal("0"),  # free tier only
}
```

Unknown `(backend, model)` or `backend` → `(0, 0)` with a **once-per-boot WARN log** (not per request).

### Calculation

```python
def calculate_llm_cost_micro_usd(
    tokens_in: int, tokens_out: int,
    price_in_per_1k: Decimal, price_out_per_1k: Decimal,
) -> int:
    cost_usd = (
        Decimal(tokens_in) * price_in_per_1k / Decimal(1_000_000)
        + Decimal(tokens_out) * price_out_per_1k / Decimal(1_000_000)
    )
    return int((cost_usd * Decimal(1_000_000)).quantize(Decimal("1")))

def calculate_char_cost_micro_usd(
    chars_in: int, price_per_1m: Decimal,
) -> int:
    cost_usd = Decimal(chars_in) * price_per_1m / Decimal(1_000_000)
    return int((cost_usd * Decimal(1_000_000)).quantize(Decimal("1")))
```

### Daily cap enforcement

New config field per backend: `translation_cost_cap_daily_micro_usd_<name>`, default `0` (= off). Pre-call check in `LLMBackend.translate_batch`:

```python
today_cost = db.session.scalar(
    sa.select(sa.func.coalesce(sa.func.sum(TranslationEvent.cost_estimate_micro_usd), 0))
    .where(TranslationEvent.backend == self.name)
    .where(TranslationEvent.started_at >= today_utc_midnight)
)
cap = int(get_config_entry(f"translation_cost_cap_daily_micro_usd_{self.name}") or 0)
if cap > 0 and today_cost >= cap:
    raise BudgetCapExceededError(f"{self.name} daily cap ${cap / 1_000_000:.2f} exceeded")
```

Circuit breaker for the backend is held open until UTC midnight. Cap check is cheap (indexed query, ~10ms); acceptable per-call overhead.

## API contract

### Blueprint: `routes/translation/` (new), prefix `/api/v1/translation`

All admin-gated via existing `@require_api_key` middleware.

| Method | Path | Purpose | Status codes |
|---|---|---|---|
| `GET` | `/cost` | Today/7d/30d totals | 200, 401 |
| `GET` | `/cost/by-backend?window=7d` | Per-backend breakdown | 200, 401 |
| `GET` | `/events?backend=X&status=Y&limit=50` | Paginated event list | 200, 401 |
| `GET` | `/memory/stats` | TM row count, size, hit-rate | 200, 401 |
| `POST` | `/memory/purge` | Body `{older_than_days?, backend?}` | 202, 401 |
| `GET` | `/concurrency` | All backends' current limit + in-use | 200, 401 |
| `PATCH` | `/concurrency/<backend>` | Body `{limit: int}` | 200, 400, 401, 404 |
| `GET` | `/queue` | Active + recent jobs (A2) | 200, 401 |
| `POST` | `/queue/<job_id>/cancel` | Best-effort cancel (A2) | 202, 401, 404, 409 |

### Response shapes

**`GET /cost`:**
```json
{
  "today": {"cost_usd": 0.42, "events": 18, "cache_hits": 5},
  "last_7d": {"cost_usd": 3.89, "events": 412, "cache_hits": 102},
  "last_30d": {"cost_usd": 19.23, "events": 2015, "cache_hits": 538}
}
```

**`GET /cost/by-backend?window=7d`:**
```json
{
  "window": "7d",
  "backends": [
    {"backend": "claude", "events": 180, "cost_usd": 1.82, "avg_latency_ms": 1420, "error_rate": 0.011},
    {"backend": "ollama", "events": 340, "cost_usd": 0.00, "avg_latency_ms": 880, "error_rate": 0.003},
    ...
  ]
}
```

**`GET /memory/stats`:**
```json
{
  "rows": 12403, "size_bytes": 4200000,
  "hit_rate_7d": 0.23,
  "last_purge_at": "2026-04-01T03:30:00Z",
  "by_backend": [
    {"backend": "claude", "rows": 3200, "hit_count_7d": 82},
    ...
  ]
}
```

**`GET /queue` (A2):**
```json
{
  "active": [
    {
      "job_id": "abc12345", "file_path": "...", "source_lang": "en", "target_lang": "de",
      "backend": "claude", "progress": {"done": 142, "total": 428, "pct": 33.2},
      "started_at": "...", "eta_seconds": 45,
      "cost_so_far_micro_usd": 12400
    }
  ],
  "recent": [
    {"job_id": "...", "status": "ok", "backend": "claude", "duration_s": 52, "cost_usd": 0.04, "lines": 428}
  ]
}
```

### Admin audit logs

Every mutation endpoint logs at INFO:
```
translation_admin_action job_id=X action=Y backend=Z actor=<first-6-chars-of-api-key>
```

Reuses the same pattern as scheduler mutations (Phase 5). Actions: `purge-memory`, `set-concurrency`, `cancel-job`.

## UI

### Navigation

Extend existing **Settings → Translation** submenu with three new entries:
- **Backends** (existing — extended with concurrency slider + cost-cap field per card)
- **Cost & Memory** (NEW — CostDashboard + TranslationMemoryPanel on one page)
- **Queue** (NEW — A2 — QueueDashboard)
- Presets (existing — unchanged)
- Glossary (existing — unchanged)

### Cost & Memory page layout

```
┌─ Translation · Cost & Memory ──────────────────────────────┐
│                                                            │
│  Today: $0.42 · 7d: $3.89 · 30d: $19.23                   │
│                                                            │
│  ┌─ Per Backend (last 7 days) ────────────────────────────┐│
│  │ Backend       Events  Cost     Avg Latency  Error Rate ││
│  │ claude        180     $1.82    1.4s         1.1%        ││
│  │ ollama        340     $0.00    0.9s         0.3%        ││
│  │ deepl         220     $0.09    0.2s         0.0%        ││
│  │ ...                                                     ││
│  │ [Cost cap: $X/day] slider per row                       ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─ Translation Memory ──────────────────────────────────┐│
│  │ 12,403 rows · 4.2 MB · 23% hit rate (7d)              ││
│  │ Last purge: 2026-04-01                                 ││
│  │ [Purge older than] [30] days  [Purge now]              ││
│  │ (purges can also filter by backend)                    ││
│  └────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─ Cost Timeline (last 30 days) ────────────────────────┐│
│  │  [stacked bar chart: daily cost per backend]           ││
│  └────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────┘
```

Polls `/cost` + `/memory/stats` every **30 seconds**.

### Queue dashboard layout

```
┌─ Translation · Queue ──────────────────────────────────────┐
│  2 active · 18 recent                                      │
│                                                            │
│  ┌─ Active ─────────────────────────────────────────────┐│
│  │ episode.mkv   en→de   claude                         ││
│  │ ████████░░░░░░░░░░░░  33% (142/428)  ~45s · $0.012  ││
│  │ [Cancel]                                             ││
│  │ ─────                                                ││
│  │ movie.mkv     en→de   deepl                          ││
│  │ ████████████████████  100% completing...             ││
│  └──────────────────────────────────────────────────────┘│
│                                                            │
│  Recent (last 5 min):                                     │
│  ✓ show.s01e02.mkv  en→de  claude  12s  $0.04           │
│  ✗ bad.mkv          en→de  claude  (ContentFilter)       │
└────────────────────────────────────────────────────────────┘
```

Polls `/queue` every **3 seconds** while mounted.

### Styling

Pure Tailwind per the A1 policy (memory `project_a1_foundation_2026_04_18`).
Reuse tokens Phase 5 established: `bg-surface`, `bg-elevated`, `bg-error-bg`, `text-error`, `border-border`, `bg-accent`. No new tokens.

### i18n

All strings under `translation.cost.*`, `translation.memory.*`, `translation.queue.*` in both DE and EN locales. Includes toast messages for mutations (`purged_n_rows`, `concurrency_updated`, `job_cancelled`).

## Error handling — failure matrix

### Per-call failures (handled in `LLMBackend.translate_batch`)

| Failure | Detection | Action | Event status |
|---|---|---|---|
| Network error / 5xx | try/except on `_call_api` | semaphore released in `finally`; event written; re-raise to `translate_with_fallback` | `error` |
| Timeout | `requests.Timeout` | same, event `status="timeout"` | `timeout` |
| Rate limit 429 | HTTP status in `_call_api` | budget-manager 429-recovery (existing); event logged | `rate_limit` |
| Content filter refused | `finish_reason == 'content_filter'` | event logged INFO (not error); re-raise as `ContentFilterError` | `error` |
| Line count mismatch | `_verify_line_count` | retry once with stricter prompt; on second fail raise `LineCountMismatchError` | `error` |
| Circuit breaker open | `translate_with_fallback` pre-check | skip backend; synthetic event (no acquire) | `circuit_open` |
| All backends fail | loop exits with `last_error` | raise `AllBackendsFailedError`; job marked `error` | — |
| Concurrency timeout | `BackendConcurrency.slot` 120s wait | log WARN; event `error_type="ConcurrencyTimeout"`; advance chain | `timeout` |
| Budget cap exceeded | pre-call check | raise `BudgetCapExceededError`; circuit breaker opens until UTC midnight | `error` |
| Malformed API key (401) | HTTP 401 | circuit breaker opens with 3600s cooldown; no retry this hour | `error` |

### Startup failures

| Case | Handling |
|---|---|
| `translation_events` table missing | Alembic migration creates before first call |
| Unknown backend in a language profile's fallback chain | `get_backend` returns None; loop skips with WARN |
| Two backend registrations with same `name` | `register_backend` raises `ConfigurationError` at import time |
| Price-sheet entry missing for `(backend, model)` | `calculate_cost` returns 0 + WARN logged ONCE per boot; events still written |

### Runtime config changes

| Change | Propagation |
|---|---|
| Concurrency slider | `BackendConcurrency.set_limit`; in-flight unaffected; next acquire sees new limit |
| Daily cost cap edit | read at call time; no restart |
| Price sheet update | requires version bump/deploy (intentional) |
| Retention days | picked up on next `translation_events_cleanup` fire |
| Prompt preset edit | applies to next job; in-flight job keeps its start-time snapshot |

### Queue edge cases (A2)

| Case | Handling |
|---|---|
| Cancel mid-batch | current batch completes + cost logged; job status `cancelled_after_batch_n`; no further batches |
| Partial API response | `_parse_response` raises `PartialResponseError`; retry once; otherwise mark batch failed, continue with next batch |
| Job outlives process (SIGTERM) | in-memory state lost; `jobs` row with `status=running` older than 5 min reconciled to `interrupted` on next boot |
| Double cancel | second call returns 409 `AlreadyCancelledError` |

### Cross-session integrity

- Costs accumulate monotonically — events never deleted except by retention cron.
- Dashboard aggregates always reproducible from events.
- TM hit attribution: cache-hit event has `cache_hit=true`, `backend=<original writer>`, `cost=0`. Distinguishes "saved by cache" from "no-cost backend used".
- No retroactive cost correction when price sheet updates — historical costs preserve per-request price.

## Testing

Coverage goals: ≥ 80% line coverage on every new module; 100% of failure matrix rows have at least one dedicated test.

### Harness additions

- `mock_llm_backend` fixture — deterministic fake LLM for non-network tests.
- `frozen_cost_clock` fixture — `freezegun` for stable 7d/30d windows.
- `concurrency_tracker` fixture — spy on acquire/release for balance assertions.

Live-API tests gated on `TRANSLATION_LIVE_APIS=1` env; nightly CI only.

### Test budget by phase

| Phase | New unit tests | New frontend | New E2E |
|---|---|---|---|
| A1 | ~50 | ~13 | 0 |
| A2 | ~25 | ~10 | 1 |
| A3 | ~40 | ~6 | 0 |
| A4 | ~20 | ~4 | 0 |
| A5 | ~50 | ~6 | 1 |
| **Total** | **~185** | **~39** | **2** |

### Regression tests tied to documented pitfalls

| Memory | Regression test |
|---|---|
| `feedback_scheduler_timer_leak` | `test_backend_concurrency::test_no_semaphore_leak_on_exception` |
| `feedback_flask_app_context_in_threads` | `test_llm_base_dispatch::test_app_context_entered_on_concurrent_call` |
| `feedback_alembic_pitfalls` | `test_translation_events_migration::test_upgrade_uses_explicit_ddl` |
| `project_stability_session_2026_04_13` | `test_translation_events_model::test_cleanup_uses_session_begin` |
| `feedback_apscheduler_pickle_closure` | N/A — queue is transient, no pickling |

### Runtime budget

- Unit suite: ~185 tests, target < 25s
- Frontend unit: ~39 tests, < 12s
- E2E: 2 specs, ~60-90s (A2 + A5)

## Dependencies & prerequisites

- `anthropic` Python SDK (A3) — `pip install anthropic>=0.39`
- `google-genai` (A3) — `pip install google-genai>=0.3` or direct REST
- DeepSeek uses OpenAI-compat API — no new SDK
- Azure uses `azure-ai-translation-text` (A5)
- Mistral uses OpenAI-compat API — no new SDK
- MyMemory uses plain HTTP GET — no SDK
- No frontend dependencies beyond what's already installed

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Price sheet goes stale | Document in CLAUDE.md: "update `price_sheet.py` on version bumps when providers announce price changes"; link to provider pricing pages |
| Concurrency default too high/low | Expose slider; default 3 is conservative; Prometheus metrics reveal actual usage |
| TM table grows unbounded | Retention cron + manual purge UI; size surfaced on dashboard |
| Live APIs rate-limit us in CI | Tests gate on `TRANSLATION_LIVE_APIS=1`; default CI uses mocks |
| Backend name collision with existing code | Fail-fast on registration; ConfigurationError at import time |
| Migration of ollama/openai_compat breaks consumers | Public `translate_batch` contract preserved; integration tests verify |
| Context-windowing inflates token cost significantly | Cost-capped daily; per-provider observable; can be disabled via `translation_context_enabled=false` |
| UI polling floods API | 3s for queue, 30s for cost; React Query dedupes; `window=X` query param caps server work |

## Rollout plan (high-level)

Implementation plans produced by writing-plans skill will detail each phase.
At a high level:

1. **Phase A1 — Telemetry foundation.** Ships the biggest single piece:
   `LLMBackend` base class, `translation_events` table, cost tracking,
   concurrency service, Cost Dashboard, TM panel. Migrates `ollama` +
   `openai_compat` to LLMBackend (internal only, public contract preserved).
2. **Phase A2 — Queue Dashboard.** In-memory active-jobs tracker,
   `/queue` endpoint, QueueDashboard page, cancellation semantics.
3. **Phase A3 — Claude + Gemini + DeepSeek.** Three LLMBackend subclasses.
4. **Phase A4 — Context-windowing.** Pre-chunker wired into LLMBackend.
5. **Phase A5 — Azure + Mistral + MyMemory + ChatGPT.** Four more backends
   (mix LLM + char-priced).

Each phase is independently shippable and delivers user value.

## Acceptance criteria (full-platform)

- [ ] 12 translation backends registered (5 existing + 7 new).
- [ ] All LLM backends share `LLMBackend` base; prompt / retry / cost / concurrency logic exists in exactly one place.
- [ ] `translation_events` row written for every `translate_batch` call (ok / error / timeout / circuit_open / rate_limit / cache-hit).
- [ ] Cost Dashboard shows today / 7d / 30d aggregates + per-backend breakdown; accurate to exact micro-USD.
- [ ] TM panel shows hit-rate + row-count + byte-size; manual purge works.
- [ ] Queue Dashboard shows live active jobs with progress bars + cancel button; updates every 3s.
- [ ] Concurrency slider per backend immediately resizes semaphore without restart.
- [ ] Daily cost cap enforces per-backend and pauses backend for the rest of UTC day when exceeded.
- [ ] Context windower (LLM only) includes lookback/lookahead in prompt; configurable lookback/lookahead line counts; disabled for non-LLM backends.
- [ ] All 12 backends have "Test connection" in settings.
- [ ] Admin audit log line for every mutation.
- [ ] Prometheus metrics scrape the new translation counters/histograms.
- [ ] `translation_events_retention_days` cleanup cron runs nightly + respects setting changes.
- [ ] All new tests green; no regressions in existing scheduler/provider suites.

## Open questions

None at design time. Implementation questions (exact endpoint names, test file names, `BackendCard` slider component choice) deferred to the per-phase plans.
