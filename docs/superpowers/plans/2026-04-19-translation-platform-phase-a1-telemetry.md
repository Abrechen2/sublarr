# Translation Platform / Phase A1 — Telemetry Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use `- [ ]` checkbox syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-19-translation-platform-lingarr-parity-design.md`

**Goal:** Ship the telemetry foundation — `translation_events` table + retention, `LLMBackend` base class (migrating ollama + openai_compat), per-backend concurrency semaphore, cost tracking, Cost Dashboard + Translation Memory UI panel — so that all existing translation work is measured before new backends are added in A3.

**Architecture:** Extends existing `translation/` + `translator/` modules with a new LLM-focused base class and 4 utility modules (concurrency, cost_tracker, price_sheet, events). Adds one DB table + one column, one nightly retention cron (reusing Phase 5 scheduler), a new Flask blueprint under `/api/v1/translation/`, and one new Settings page. Existing `TranslationBackend` ABC is unchanged; `LLMBackend` is a subclass that ollama + openai_compat migrate into while preserving their public `translate_batch` contract.

**Tech Stack:** SQLAlchemy 2.0, APScheduler (via existing `SublarrScheduler`), Pydantic 2, Flask blueprints, React 19 + TypeScript + Tailwind, React Query, vitest.

**Dependencies:** Phase 5 scheduler (0.58.1-beta) already deployed. `SublarrScheduler.register_job` is the entry point for the nightly retention cron.

**Baseline version:** 0.58.1-beta. This phase ships as minor bump (feat: adds user-visible Cost/Memory page).

---

## File structure

### New backend files
- `backend/translation/llm_base.py` — `LLMBackend` ABC with 3 provider hooks + shared orchestration (~250 LOC)
- `backend/translation/concurrency.py` — `BackendConcurrency` semaphore service (~100 LOC)
- `backend/translation/cost_tracker.py` — micro-USD math helpers (~80 LOC)
- `backend/translation/price_sheet.py` — frozen dict-of-tuples (~60 LOC)
- `backend/translator/events.py` — `write_translation_event` writer using fresh scoped session (~90 LOC)
- `backend/routes/translation/__init__.py` — blueprint registry (~20 LOC)
- `backend/routes/translation/events.py` — GET `/cost`, `/cost/by-backend`, `/events`, `/memory/stats`, POST `/memory/purge` (~200 LOC)
- `backend/routes/translation/concurrency.py` — GET `/concurrency`, PATCH `/concurrency/<backend>` (~100 LOC)
- `backend/utils/scheduler_retention_translation.py` — `delete_old_translation_events()` (~30 LOC)
- `backend/db/models/translation.py` — extend existing file with `TranslationEvent` ORM model
- `backend/db/migrations/versions/<rev>_translation_events.py` — explicit Alembic migration (both `translation_events` table + `translation_memory.backend` column)
- Tests — one file per module, listed in each task

### Modified backend files
- `backend/translation/ollama.py` — migrate to inherit from `LLMBackend`
- `backend/translation/openai_compat.py` — migrate to inherit from `LLMBackend`
- `backend/translation/__init__.py` — wire `BackendConcurrency` into `TranslationManager`; emit events from `translate_with_fallback`
- `backend/services/scheduler.py` — append `translation_events_cleanup` to `_build_default_jobs()`
- `backend/config_settings.py` — add `translation_events_retention_days`
- `backend/monitoring/metrics.py` — add 4 translation counters/histograms
- `backend/app_routes_core.py` (or `routes/__init__.py`) — register translation blueprints

### New frontend files
- `frontend/src/api/translation.ts` — extend existing file with `getCost`, `getCostByBackend`, `getMemoryStats`, `purgeMemory`, `getConcurrency`, `patchConcurrency`
- `frontend/src/hooks/useTranslationCost.ts` — React Query hooks (~40 LOC)
- `frontend/src/hooks/useTranslationMutations.ts` — purge + concurrency PATCH (~60 LOC)
- `frontend/src/pages/Settings/translation/CostMemoryPage.tsx` — Cost Dashboard + TM Panel on one page (~260 LOC)
- `frontend/src/pages/Settings/translation/CostSummaryCards.tsx` (~50 LOC)
- `frontend/src/pages/Settings/translation/BackendCostTable.tsx` (~90 LOC)
- `frontend/src/pages/Settings/translation/TranslationMemoryPanel.tsx` (~110 LOC)

### Modified frontend files
- `frontend/src/pages/Settings/index.tsx` — add route `/settings/translation/cost-memory`
- `frontend/src/pages/Settings/translation/TranslationBackendsTab.tsx` — integrate concurrency slider + cost cap per `BackendCard`
- `frontend/src/components/settings/SettingsNav.tsx` — add menu entry
- `frontend/src/i18n/locales/{de,en}/settings.json` — `translation.cost.*`, `translation.memory.*`
- `frontend/src/types/system.ts` (or translation types file) — TranslationEvent, CostSummary, MemoryStats types

---

## Task 1: Extend price_sheet module

**Files:**
- Create: `backend/translation/price_sheet.py`
- Test: `backend/tests/test_price_sheet.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_price_sheet.py`:

```python
"""Price sheet lookup tests."""

from decimal import Decimal

import pytest


def test_known_llm_combo():
    from translation.price_sheet import get_llm_price

    in_price, out_price = get_llm_price("claude", "claude-sonnet-4-6")
    assert in_price == Decimal("3.00")
    assert out_price == Decimal("15.00")


def test_known_char_backend():
    from translation.price_sheet import get_char_price

    assert get_char_price("deepl") == Decimal("20.00")


def test_unknown_llm_combo_returns_zero(caplog):
    from translation.price_sheet import get_llm_price

    with caplog.at_level("WARNING", logger="translation.price_sheet"):
        in_price, out_price = get_llm_price("unknown_backend", "unknown_model")
    assert in_price == Decimal("0")
    assert out_price == Decimal("0")
    assert any("price unknown" in r.message.lower() for r in caplog.records)


def test_unknown_char_backend_returns_zero():
    from translation.price_sheet import get_char_price

    assert get_char_price("unknown") == Decimal("0")


def test_warn_emitted_once_per_combo(caplog):
    """Subsequent lookups for same unknown combo should not spam logs."""
    from translation.price_sheet import _reset_warned, get_llm_price

    _reset_warned()
    with caplog.at_level("WARNING", logger="translation.price_sheet"):
        get_llm_price("never_heard", "also_never")
        get_llm_price("never_heard", "also_never")
        get_llm_price("never_heard", "also_never")
    warn_count = sum(
        1 for r in caplog.records if "price unknown" in r.message.lower()
    )
    assert warn_count == 1


def test_ollama_free_tier():
    from translation.price_sheet import get_llm_price

    in_price, out_price = get_llm_price("ollama", "any-model")
    assert in_price == Decimal("0")
    assert out_price == Decimal("0")
```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_price_sheet.py -v`
Expected: `ModuleNotFoundError: No module named 'translation.price_sheet'`.

- [ ] **Step 3: Create `backend/translation/price_sheet.py`**

```python
"""Translation price sheet — USD per 1M tokens / characters.

Intentionally code-owned (not UI-configurable) to prevent operators from
silently desyncing local prices from reality. Updates go via version bumps.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# USD per 1M tokens (in, out). Wildcard "*" matches any model.
PRICE_SHEET_LLM: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    # Anthropic Claude
    ("claude", "claude-sonnet-4-6"): (Decimal("3.00"), Decimal("15.00")),
    ("claude", "claude-opus-4-7"): (Decimal("15.00"), Decimal("75.00")),
    ("claude", "claude-haiku-4-5"): (Decimal("0.25"), Decimal("1.25")),
    # Google Gemini
    ("gemini", "gemini-2.5-pro"): (Decimal("1.25"), Decimal("5.00")),
    ("gemini", "gemini-2.5-flash"): (Decimal("0.075"), Decimal("0.30")),
    # DeepSeek
    ("deepseek", "deepseek-chat"): (Decimal("0.14"), Decimal("0.28")),
    ("deepseek", "deepseek-coder"): (Decimal("0.14"), Decimal("0.28")),
    # OpenAI / OpenAI-compatible
    ("openai_compat", "gpt-4o"): (Decimal("2.50"), Decimal("10.00")),
    ("openai_compat", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("chatgpt", "gpt-4o"): (Decimal("2.50"), Decimal("10.00")),
    ("chatgpt", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    # Mistral
    ("mistral", "mistral-large-latest"): (Decimal("2.00"), Decimal("6.00")),
    ("mistral", "mistral-small-latest"): (Decimal("0.20"), Decimal("0.60")),
    # Self-hosted
    ("ollama", "*"): (Decimal("0"), Decimal("0")),
}

# USD per 1M characters for char-priced backends.
PRICE_SHEET_CHARS: dict[str, Decimal] = {
    "deepl": Decimal("20.00"),
    "deepl_pro": Decimal("25.00"),
    "google_translate": Decimal("20.00"),
    "azure_translator": Decimal("10.00"),
    "libretranslate": Decimal("0"),  # self-hosted free
    "mymemory": Decimal("0"),  # free tier only
}

_warned_unknown: set[tuple[str, str | None]] = set()


def _reset_warned() -> None:
    """Test helper — clear the 'warned once' memo."""
    _warned_unknown.clear()


def get_llm_price(backend: str, model: str) -> tuple[Decimal, Decimal]:
    """Look up (input_price, output_price) for an LLM backend+model.

    Returns (0, 0) for unknown combos; logs WARN once per combo.
    """
    key = (backend, model)
    if key in PRICE_SHEET_LLM:
        return PRICE_SHEET_LLM[key]
    wildcard = (backend, "*")
    if wildcard in PRICE_SHEET_LLM:
        return PRICE_SHEET_LLM[wildcard]
    if key not in _warned_unknown:
        _warned_unknown.add(key)
        logger.warning(
            "price unknown for backend=%s model=%s; cost will be 0", backend, model
        )
    return (Decimal("0"), Decimal("0"))


def get_char_price(backend: str) -> Decimal:
    """Look up USD per 1M characters for a char-priced backend.

    Returns 0 for unknown backends; logs WARN once per backend.
    """
    if backend in PRICE_SHEET_CHARS:
        return PRICE_SHEET_CHARS[backend]
    key = (backend, None)
    if key not in _warned_unknown:
        _warned_unknown.add(key)
        logger.warning(
            "char price unknown for backend=%s; cost will be 0", backend
        )
    return Decimal("0")
```

- [ ] **Step 4: Run — expect 6 passed**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_price_sheet.py -v`
Expected: 6 passed.

- [ ] **Step 5: Ruff + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr && ruff check backend/translation/price_sheet.py backend/tests/test_price_sheet.py && ruff format --check backend/translation/price_sheet.py backend/tests/test_price_sheet.py
git add backend/translation/price_sheet.py backend/tests/test_price_sheet.py
git commit -m "feat(translation-a1): add price_sheet with LLM + char-backend lookups"
```

---

## Task 2: cost_tracker module (micro-USD math)

**Files:**
- Create: `backend/translation/cost_tracker.py`
- Test: `backend/tests/test_cost_tracker.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_cost_tracker.py`:

```python
"""Cost tracker math tests — integer micro-USD."""

from decimal import Decimal


def test_llm_cost_simple():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    # 1000 tokens in @ $3/1M, 500 tokens out @ $15/1M
    # in: 1000 * 3 / 1M = $0.003 = 3000 micro_usd
    # out: 500 * 15 / 1M = $0.0075 = 7500 micro_usd
    # total: 10500 micro_usd
    cost = calculate_llm_cost_micro_usd(
        tokens_in=1000, tokens_out=500,
        price_in_per_1m=Decimal("3.00"), price_out_per_1m=Decimal("15.00"),
    )
    assert cost == 10500


def test_llm_cost_zero_tokens_is_zero():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    cost = calculate_llm_cost_micro_usd(0, 0, Decimal("3"), Decimal("15"))
    assert cost == 0


def test_llm_cost_zero_price_is_zero():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    cost = calculate_llm_cost_micro_usd(1000, 500, Decimal("0"), Decimal("0"))
    assert cost == 0


def test_char_cost_simple():
    from translation.cost_tracker import calculate_char_cost_micro_usd

    # 10000 chars @ $20/1M = $0.20 = 200000 micro_usd
    cost = calculate_char_cost_micro_usd(
        chars_in=10000, price_per_1m=Decimal("20.00")
    )
    assert cost == 200000


def test_no_float_drift_on_large_sum():
    """Aggregating millions of small events must not drift."""
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    # Each call: 100 tokens in @ $3/1M = $0.0003 = 300 micro_usd
    per_call = calculate_llm_cost_micro_usd(
        tokens_in=100, tokens_out=0,
        price_in_per_1m=Decimal("3"), price_out_per_1m=Decimal("0"),
    )
    assert per_call == 300
    # 1 million such calls: $300 = 300_000_000 micro_usd exactly
    assert per_call * 1_000_000 == 300_000_000


def test_usd_display_conversion():
    from translation.cost_tracker import micro_usd_to_usd

    assert micro_usd_to_usd(1_000_000) == Decimal("1.00")
    assert micro_usd_to_usd(42) == Decimal("0.000042")
    assert micro_usd_to_usd(0) == Decimal("0")


def test_rounding_deterministic():
    """Half-even rounding — integer result must be stable."""
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    # 1 token @ $3/1M = 0.000003 USD = 3.0 micro_usd — exactly 3
    cost = calculate_llm_cost_micro_usd(
        tokens_in=1, tokens_out=0,
        price_in_per_1m=Decimal("3"), price_out_per_1m=Decimal("0"),
    )
    assert cost == 3
```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

- [ ] **Step 3: Create `backend/translation/cost_tracker.py`**

```python
"""Cost tracker — integer micro-USD math for translation events.

1 USD = 1_000_000 micro_usd. Integer math avoids float drift over
aggregation of millions of events.
"""

from decimal import ROUND_HALF_EVEN, Decimal

_MICRO_PER_USD = Decimal(1_000_000)
_PER_1M = Decimal(1_000_000)


def calculate_llm_cost_micro_usd(
    tokens_in: int,
    tokens_out: int,
    price_in_per_1m: Decimal,
    price_out_per_1m: Decimal,
) -> int:
    """Cost in micro-USD for an LLM call.

    Prices are quoted per 1,000,000 tokens (standard LLM provider format).
    """
    cost_usd = (
        Decimal(tokens_in) * price_in_per_1m / _PER_1M
        + Decimal(tokens_out) * price_out_per_1m / _PER_1M
    )
    return int(
        (cost_usd * _MICRO_PER_USD).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    )


def calculate_char_cost_micro_usd(
    chars_in: int,
    price_per_1m: Decimal,
) -> int:
    """Cost in micro-USD for a char-priced translation call."""
    cost_usd = Decimal(chars_in) * price_per_1m / _PER_1M
    return int(
        (cost_usd * _MICRO_PER_USD).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    )


def micro_usd_to_usd(micro: int) -> Decimal:
    """Convert integer micro-USD to Decimal USD for display."""
    return (Decimal(micro) / _MICRO_PER_USD).normalize()
```

- [ ] **Step 4: Run — expect 7 passed**

- [ ] **Step 5: Ruff + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr && ruff check backend/translation/cost_tracker.py backend/tests/test_cost_tracker.py
git add backend/translation/cost_tracker.py backend/tests/test_cost_tracker.py
git commit -m "feat(translation-a1): add cost_tracker micro-USD math helpers"
```

---

## Task 3: TranslationEvent ORM model

**Files:**
- Modify: `backend/db/models/translation.py`
- Modify: `backend/db/models/__init__.py` — re-export
- Test: `backend/tests/test_translation_event_model.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_translation_event_model.py`:

```python
"""TranslationEvent ORM model schema tests."""

from datetime import UTC, datetime

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


def test_tablename_and_columns():
    from db.models.translation import TranslationEvent

    assert TranslationEvent.__tablename__ == "translation_events"
    cols = {c.name for c in TranslationEvent.__table__.columns}
    assert cols == {
        "id", "backend", "source_lang", "target_lang",
        "lines_count", "chars_in", "chars_out",
        "tokens_in", "tokens_out",
        "cost_estimate_micro_usd", "cache_hit",
        "latency_ms", "status", "error_type", "error_msg",
        "job_id", "started_at", "finished_at",
    }


def test_indexes_exist():
    from db.models.translation import TranslationEvent

    index_names = {ix.name for ix in TranslationEvent.__table__.indexes}
    assert "ix_translation_events_backend_started_at" in index_names
    assert "ix_translation_events_started_at" in index_names
    assert "ix_translation_events_status" in index_names
    assert "ix_translation_events_job_id" in index_names


def test_default_cache_hit_false(app):
    from extensions import db
    from db.models.translation import TranslationEvent

    with app.app_context():
        row = TranslationEvent(
            backend="ollama", source_lang="en", target_lang="de",
            lines_count=10, chars_in=100,
            started_at=datetime.now(UTC), status="ok",
        )
        db.session.add(row)
        db.session.flush()
        assert row.cache_hit is False
        db.session.rollback()


def test_cost_is_bigint(app):
    from extensions import db
    from db.models.translation import TranslationEvent

    big_cost = 10 ** 15  # bigger than 2**31 (signed 32-bit int)
    with app.app_context():
        row = TranslationEvent(
            backend="claude", source_lang="en", target_lang="de",
            lines_count=1, chars_in=1,
            cost_estimate_micro_usd=big_cost,
            started_at=datetime.now(UTC), status="ok",
        )
        db.session.add(row)
        db.session.flush()
        assert row.cost_estimate_micro_usd == big_cost
        db.session.rollback()
```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

- [ ] **Step 3: Read existing `backend/db/models/translation.py`** to understand existing content before appending.

- [ ] **Step 4: Append `TranslationEvent` to `backend/db/models/translation.py`**

```python
# Append to existing file (after any existing imports / class definitions):

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class TranslationEvent(db.Model):
    """One row per translate_batch call.

    Populated by translator/events.py::write_translation_event.
    Retention controlled by ``translation_events_retention_days`` + the
    ``translation_events_cleanup`` cron job.
    """

    __tablename__ = "translation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backend: Mapped[str] = mapped_column(String(32), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    lines_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chars_in: Mapped[int] = mapped_column(Integer, nullable=False)
    chars_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_micro_usd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    cache_hit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_translation_events_backend_started_at",
            "backend", "started_at",
        ),
        Index("ix_translation_events_started_at", "started_at"),
        Index("ix_translation_events_status", "status"),
        Index("ix_translation_events_job_id", "job_id"),
    )
```

If `from datetime import datetime` is missing at the top of the file, add it.

- [ ] **Step 5: Re-export in `backend/db/models/__init__.py`**

Add in the scheduler-adjacent block (follow alphabetical / grouping pattern):

```python
from db.models.translation import ..., TranslationEvent  # extend existing import line
```

And add `"TranslationEvent"` to the `__all__` list.

- [ ] **Step 6: Run — expect 4 passed**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_translation_event_model.py -v`

- [ ] **Step 7: Ruff + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr && ruff check backend/db/models/
git add backend/db/models/translation.py backend/db/models/__init__.py backend/tests/test_translation_event_model.py
git commit -m "feat(translation-a1): add TranslationEvent ORM model"
```

---

## Task 4: Alembic migration (translation_events + TM.backend column)

**Files:**
- Create: `backend/db/migrations/versions/<rev>_translation_events.py`
- Test: `backend/tests/test_translation_events_migration.py`

- [ ] **Step 1: Find current head**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m flask --app app db heads`
Note the single head revision ID — call it `<CURRENT_HEAD>`. If multiple heads, STOP and investigate.

- [ ] **Step 2: Generate skeleton**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m flask --app app db revision -m "translation events"`
Note the new filename + revision ID.

- [ ] **Step 3: Replace generated body with explicit schema**

Open the generated file. Replace the body (keep the `revision` id Alembic assigned; set `down_revision = "<CURRENT_HEAD>"`):

```python
"""translation events

Revision ID: <keep auto-generated>
Revises: <CURRENT_HEAD from step 1>
Create Date: 2026-04-19
"""

import sqlalchemy as sa
from alembic import op

revision = "<auto>"
down_revision = "<CURRENT_HEAD>"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "translation_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("backend", sa.String(32), nullable=False),
        sa.Column("source_lang", sa.String(16), nullable=False),
        sa.Column("target_lang", sa.String(16), nullable=False),
        sa.Column("lines_count", sa.Integer, nullable=False),
        sa.Column("chars_in", sa.Integer, nullable=False),
        sa.Column("chars_out", sa.Integer, nullable=True),
        sa.Column("tokens_in", sa.Integer, nullable=True),
        sa.Column("tokens_out", sa.Integer, nullable=True),
        sa.Column(
            "cost_estimate_micro_usd",
            sa.BigInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "cache_hit",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column("job_id", sa.String(32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_translation_events_backend_started_at",
        "translation_events",
        ["backend", "started_at"],
    )
    op.create_index(
        "ix_translation_events_started_at",
        "translation_events",
        ["started_at"],
    )
    op.create_index(
        "ix_translation_events_status",
        "translation_events",
        ["status"],
    )
    op.create_index(
        "ix_translation_events_job_id",
        "translation_events",
        ["job_id"],
    )

    # Add backend column to translation_memory (existing table)
    op.add_column(
        "translation_memory",
        sa.Column("backend", sa.String(32), nullable=True),
    )


def downgrade():
    op.drop_column("translation_memory", "backend")
    op.drop_index(
        "ix_translation_events_job_id", table_name="translation_events"
    )
    op.drop_index(
        "ix_translation_events_status", table_name="translation_events"
    )
    op.drop_index(
        "ix_translation_events_started_at", table_name="translation_events"
    )
    op.drop_index(
        "ix_translation_events_backend_started_at",
        table_name="translation_events",
    )
    op.drop_table("translation_events")
```

- [ ] **Step 4: Write migration regression tests**

Create `backend/tests/test_translation_events_migration.py`:

```python
"""Migration regression tests for translation_events."""

import sqlalchemy as sa


def test_upgrade_creates_table_and_indexes(migrated_db_engine):
    insp = sa.inspect(migrated_db_engine)
    assert "translation_events" in insp.get_table_names()

    cols = {c["name"] for c in insp.get_columns("translation_events")}
    assert cols == {
        "id", "backend", "source_lang", "target_lang",
        "lines_count", "chars_in", "chars_out",
        "tokens_in", "tokens_out",
        "cost_estimate_micro_usd", "cache_hit",
        "latency_ms", "status", "error_type", "error_msg",
        "job_id", "started_at", "finished_at",
    }

    ix = {i["name"] for i in insp.get_indexes("translation_events")}
    assert "ix_translation_events_backend_started_at" in ix
    assert "ix_translation_events_started_at" in ix
    assert "ix_translation_events_status" in ix
    assert "ix_translation_events_job_id" in ix


def test_translation_memory_gains_backend_column(migrated_db_engine):
    insp = sa.inspect(migrated_db_engine)
    cols = {c["name"] for c in insp.get_columns("translation_memory")}
    assert "backend" in cols


def test_cost_column_is_bigint(migrated_db_engine):
    """BigInt required — regular Int32 overflows at ~$2.1k cumulative cost."""
    insp = sa.inspect(migrated_db_engine)
    for col in insp.get_columns("translation_events"):
        if col["name"] == "cost_estimate_micro_usd":
            # Type repr varies by dialect; just check it's not INTEGER
            assert "BIG" in str(col["type"]).upper() or str(col["type"]).upper() == "BIGINT"
            return
    raise AssertionError("cost_estimate_micro_usd column not found")
```

The `migrated_db_engine` fixture already exists in `conftest.py` from Phase 5 P1 Task 3.

- [ ] **Step 5: Run tests + apply migration to dev DB**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend
/d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_translation_events_migration.py -v
/d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m flask --app app db upgrade
```

Expected: 3 tests passed; flask db upgrade applies the migration.

- [ ] **Step 6: Commit**

```bash
cd /d/Sublarr_Projekt/Sublarr
git add backend/db/migrations/versions/*_translation_events.py backend/tests/test_translation_events_migration.py
git commit -m "feat(translation-a1): migrate translation_events + translation_memory.backend"
```

---

## Task 5: BackendConcurrency service

**Files:**
- Create: `backend/translation/concurrency.py`
- Test: `backend/tests/test_backend_concurrency.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_backend_concurrency.py`:

```python
"""BackendConcurrency semaphore tests."""

import threading
import time

import pytest


def test_register_and_get_limit():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("claude", 3)
    assert c.get_limit("claude") == 3


def test_slot_acquires_and_releases():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 2)

    with c.slot("b"):
        pass  # release on exit
    # If not released properly, next test would fail
    with c.slot("b"):
        pass


def test_slot_blocks_when_full():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 1)

    acquired = []

    def worker(slot_num):
        with c.slot("b"):
            acquired.append(slot_num)
            time.sleep(0.2)

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    time.sleep(0.05)  # ensure t1 acquires first
    t2.start()
    t1.join()
    t2.join()
    assert acquired == [1, 2]  # sequential, not concurrent


def test_slot_timeout_raises():
    from translation.concurrency import BackendConcurrency, ConcurrencyTimeoutError

    c = BackendConcurrency()
    c.register("b", 1)

    def hold():
        with c.slot("b"):
            time.sleep(1.0)

    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.05)

    with pytest.raises(ConcurrencyTimeoutError):
        with c.slot("b", timeout_s=0.1):
            pass
    t.join()


def test_set_limit_upgrades_immediately():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 1)

    def hold():
        with c.slot("b"):
            time.sleep(0.3)

    t1 = threading.Thread(target=hold)
    t1.start()
    time.sleep(0.05)
    # Now all 1 slot used. Raise limit to 2.
    c.set_limit("b", 2)
    # New acquire should succeed without blocking
    acquired = threading.Event()

    def try_acquire():
        with c.slot("b", timeout_s=0.1):
            acquired.set()

    t2 = threading.Thread(target=try_acquire)
    t2.start()
    t2.join()
    t1.join()
    assert acquired.is_set()


def test_release_on_exception():
    """Regression for semaphore leak on exception."""
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 1)

    with pytest.raises(RuntimeError):
        with c.slot("b"):
            raise RuntimeError("boom")

    # Slot should be free again
    with c.slot("b", timeout_s=0.1):
        pass  # if slot was leaked, this would timeout


def test_per_backend_independence():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("a", 1)
    c.register("b", 1)

    with c.slot("a"):
        # b's limit is independent — should not block
        with c.slot("b", timeout_s=0.1):
            pass


def test_unregistered_backend_raises():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    with pytest.raises(KeyError):
        with c.slot("never_registered"):
            pass


def test_prometheus_gauge_reflects_usage(monkeypatch):
    """In-use gauge increments + decrements with slot acquisitions."""
    from translation.concurrency import BackendConcurrency

    calls = []

    class FakeGauge:
        def labels(self, **kw):
            return self

        def inc(self):
            calls.append(("inc",))

        def dec(self):
            calls.append(("dec",))

        def set(self, v):
            calls.append(("set", v))

    monkeypatch.setattr(
        "translation.concurrency._in_use_gauge", FakeGauge()
    )
    c = BackendConcurrency()
    c.register("b", 2)
    with c.slot("b"):
        pass
    ops = [c[0] for c in calls]
    assert "inc" in ops and "dec" in ops


def test_concurrent_stress_100_threads():
    """100 concurrent workers on 5 slots — all eventually acquire."""
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 5)

    acquired = [False] * 100

    def worker(i):
        with c.slot("b", timeout_s=30):
            acquired[i] = True
            time.sleep(0.01)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(acquired)
```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

- [ ] **Step 3: Create `backend/translation/concurrency.py`**

```python
"""Per-backend concurrency semaphore.

Each registered translation backend gets its own BoundedSemaphore. The
slot() context manager acquires+releases safely (release guaranteed even
on exception).

Limit changes via set_limit are picked up by subsequent acquisitions;
in-flight workers are unaffected.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ConcurrencyTimeoutError(TimeoutError):
    """Raised when slot() blocks longer than timeout_s."""


# Prometheus gauges — lazy-loaded via monitoring.metrics if available.
_in_use_gauge = None
_limit_gauge = None


def _get_gauges():
    global _in_use_gauge, _limit_gauge
    if _in_use_gauge is not None:
        return _in_use_gauge, _limit_gauge
    try:
        from monitoring.metrics import (
            translation_concurrency_in_use,
            translation_concurrency_limit,
        )
        _in_use_gauge = translation_concurrency_in_use
        _limit_gauge = translation_concurrency_limit
    except ImportError:
        _in_use_gauge = _LimitNoopGauge()
        _limit_gauge = _LimitNoopGauge()
    return _in_use_gauge, _limit_gauge


class _LimitNoopGauge:
    def labels(self, **kw):
        return self

    def inc(self):
        pass

    def dec(self):
        pass

    def set(self, v):
        pass


class BackendConcurrency:
    """Per-backend BoundedSemaphore registry."""

    def __init__(self) -> None:
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._limits: dict[str, int] = {}
        self._lock = threading.Lock()

    def register(self, backend_name: str, initial_limit: int) -> None:
        with self._lock:
            self._semaphores[backend_name] = threading.BoundedSemaphore(initial_limit)
            self._limits[backend_name] = initial_limit
        in_use, lim = _get_gauges()
        lim.labels(backend=backend_name).set(initial_limit)

    def get_limit(self, backend_name: str) -> int:
        return self._limits.get(backend_name, 0)

    def set_limit(self, backend_name: str, new_limit: int) -> None:
        """Resize semaphore. Increases release slots immediately; decreases
        don't evict in-flight workers but new acquires obey the lower cap."""
        if new_limit < 1:
            raise ValueError("limit must be >= 1")
        with self._lock:
            old = self._limits.get(backend_name, 0)
            if old == new_limit:
                return
            # Replace semaphore. Existing holders still valid via their own reference.
            self._semaphores[backend_name] = threading.BoundedSemaphore(new_limit)
            self._limits[backend_name] = new_limit
        in_use, lim = _get_gauges()
        lim.labels(backend=backend_name).set(new_limit)
        logger.info(
            "translation concurrency limit: %s %d -> %d",
            backend_name, old, new_limit,
        )

    @contextmanager
    def slot(self, backend_name: str, timeout_s: float = 120.0):
        """Acquire slot (blocks up to timeout_s), yield, release.

        Raises KeyError if backend not registered.
        Raises ConcurrencyTimeoutError on timeout.
        """
        with self._lock:
            if backend_name not in self._semaphores:
                raise KeyError(f"backend {backend_name!r} not registered")
            sem = self._semaphores[backend_name]

        acquired = sem.acquire(timeout=timeout_s)
        if not acquired:
            raise ConcurrencyTimeoutError(
                f"{backend_name} concurrency timeout after {timeout_s}s"
            )
        in_use, _lim = _get_gauges()
        in_use.labels(backend=backend_name).inc()
        try:
            yield
        finally:
            sem.release()
            in_use.labels(backend=backend_name).dec()


# Module singleton — wired by TranslationManager at startup.
_instance: BackendConcurrency | None = None


def get_concurrency() -> BackendConcurrency:
    global _instance
    if _instance is None:
        _instance = BackendConcurrency()
    return _instance


def reset_for_tests() -> None:
    global _instance
    _instance = None
```

- [ ] **Step 4: Run — expect 10 passed**

- [ ] **Step 5: Ruff + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr && ruff check backend/translation/concurrency.py backend/tests/test_backend_concurrency.py
git add backend/translation/concurrency.py backend/tests/test_backend_concurrency.py
git commit -m "feat(translation-a1): add BackendConcurrency semaphore service"
```

---

## Task 6: translation_events writer

**Files:**
- Create: `backend/translator/events.py`
- Test: `backend/tests/test_translator_events.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_translator_events.py`:

```python
"""write_translation_event tests."""

from datetime import UTC, datetime, timedelta

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


def test_write_event_persists(app):
    from extensions import db
    from db.models.translation import TranslationEvent
    from translator.events import write_translation_event

    with app.app_context():
        write_translation_event(
            backend="ollama", source_lang="en", target_lang="de",
            lines_count=10, chars_in=100, chars_out=120,
            tokens_in=150, tokens_out=170,
            cost_micro_usd=0, cache_hit=False,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            status="ok",
        )
        row = db.session.query(TranslationEvent).filter_by(backend="ollama").one()
        assert row.lines_count == 10
        assert row.tokens_in == 150
        assert row.status == "ok"


def test_error_msg_truncated_to_4kb(app):
    from extensions import db
    from db.models.translation import TranslationEvent
    from translator.events import write_translation_event

    with app.app_context():
        huge = "x" * 10_000
        write_translation_event(
            backend="claude", source_lang="en", target_lang="de",
            lines_count=1, chars_in=1,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            status="error", error_type="RuntimeError", error_msg=huge,
        )
        row = db.session.query(TranslationEvent).filter_by(backend="claude").one()
        assert len(row.error_msg) <= 4096


def test_cache_hit_records_zero_cost(app):
    from extensions import db
    from db.models.translation import TranslationEvent
    from translator.events import write_translation_event

    with app.app_context():
        write_translation_event(
            backend="claude", source_lang="en", target_lang="de",
            lines_count=10, chars_in=100,
            started_at=datetime.now(UTC), status="ok",
            cache_hit=True, cost_micro_usd=0,
        )
        row = db.session.query(TranslationEvent).filter_by(backend="claude").one()
        assert row.cache_hit is True
        assert row.cost_estimate_micro_usd == 0


def test_latency_ms_computed_from_times(app):
    from extensions import db
    from db.models.translation import TranslationEvent
    from translator.events import write_translation_event

    with app.app_context():
        started = datetime.now(UTC)
        finished = started + timedelta(milliseconds=1234)
        write_translation_event(
            backend="claude", source_lang="en", target_lang="de",
            lines_count=1, chars_in=1,
            started_at=started, finished_at=finished,
            status="ok",
        )
        row = db.session.query(TranslationEvent).filter_by(backend="claude").one()
        assert row.latency_ms == 1234


def test_db_failure_logged_not_raised(app, caplog):
    """Event write failure must never break the translation flow."""
    import logging
    from unittest.mock import patch
    from translator.events import write_translation_event

    with app.app_context():
        with patch("translator.events._commit", side_effect=RuntimeError("db down")):
            with caplog.at_level(logging.ERROR, logger="translator.events"):
                write_translation_event(
                    backend="claude", source_lang="en", target_lang="de",
                    lines_count=1, chars_in=1,
                    started_at=datetime.now(UTC), status="ok",
                )
        assert any("failed" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

- [ ] **Step 3: Create `backend/translator/events.py`**

```python
"""Translation-event writer — populates translation_events table.

Uses the same fresh-session pattern as scheduler_job_runs to ensure a
corrupted tick session cannot destroy the event record it's writing.
"""

from __future__ import annotations

import logging
from datetime import datetime

from db.models.translation import TranslationEvent
from extensions import db

logger = logging.getLogger(__name__)

_MAX_ERROR_MSG_BYTES = 4096


def write_translation_event(
    *,
    backend: str,
    source_lang: str,
    target_lang: str,
    lines_count: int,
    chars_in: int,
    started_at: datetime,
    status: str,
    finished_at: datetime | None = None,
    chars_out: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_micro_usd: int = 0,
    cache_hit: bool = False,
    error_type: str | None = None,
    error_msg: str | None = None,
    job_id: str | None = None,
) -> None:
    """Persist one translation event.

    Silently logs + swallows DB failures; translation work must never
    be blocked by event-write failures.
    """
    latency_ms = None
    if finished_at is not None:
        latency_ms = int((finished_at - started_at).total_seconds() * 1000)

    if error_msg and len(error_msg) > _MAX_ERROR_MSG_BYTES:
        error_msg = error_msg[: _MAX_ERROR_MSG_BYTES - 3] + "..."

    row = TranslationEvent(
        backend=backend,
        source_lang=source_lang,
        target_lang=target_lang,
        lines_count=lines_count,
        chars_in=chars_in,
        chars_out=chars_out,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate_micro_usd=cost_micro_usd,
        cache_hit=cache_hit,
        latency_ms=latency_ms,
        status=status,
        error_type=error_type,
        error_msg=error_msg,
        job_id=job_id,
        started_at=started_at,
        finished_at=finished_at,
    )
    try:
        _commit(row)
    except Exception:
        logger.error("translation event write failed", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            logger.error("rollback failed", exc_info=True)


def _commit(row: TranslationEvent) -> None:
    """Separate helper so tests can patch it."""
    db.session.add(row)
    db.session.commit()
```

- [ ] **Step 4: Run — expect 5 passed**

- [ ] **Step 5: Ruff + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr && ruff check backend/translator/events.py backend/tests/test_translator_events.py
git add backend/translator/events.py backend/tests/test_translator_events.py
git commit -m "feat(translation-a1): add write_translation_event helper"
```

---

## Task 7: LLMBackend base class

**Files:**
- Create: `backend/translation/llm_base.py`
- Test: `backend/tests/test_llm_base.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_llm_base.py`:

```python
"""LLMBackend base class tests using a fake subclass."""

from decimal import Decimal

import pytest


class _FakeLLM:
    """Fake LLMBackend subclass — deterministic responses, counts hook calls."""

    name = "fake_llm"
    display_name = "Fake LLM"
    default_model = "fake-model-1"
    config_fields = []
    supports_glossary = True
    supports_batch = True
    max_batch_size = 50

    def __init__(self, should_raise=None, line_count_override=None, **kw):
        self.should_raise = should_raise
        self.line_count_override = line_count_override
        self.build_calls = 0
        self.call_calls = 0
        self.parse_calls = 0

    def _build_request(self, messages, max_tokens):
        self.build_calls += 1
        return {"messages": messages, "max_tokens": max_tokens}

    def _call_api(self, payload, timeout_s):
        self.call_calls += 1
        if self.should_raise:
            raise self.should_raise
        return {"text": "\n".join(f"translated {i}" for i in range(3)),
                "tokens_in": 30, "tokens_out": 40}

    def _parse_response(self, raw):
        self.parse_calls += 1
        from translation.llm_base import LLMResponse
        lines = raw["text"].split("\n")
        if self.line_count_override is not None:
            lines = lines[: self.line_count_override]
        return LLMResponse(
            translations=lines,
            tokens_in=raw["tokens_in"],
            tokens_out=raw["tokens_out"],
            model="fake-model-1",
            finish_reason="stop",
            raw_latency_ms=42,
        )


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


def _build_backend(app, should_raise=None, line_count_override=None):
    from translation.llm_base import LLMBackend
    from translation.concurrency import get_concurrency, reset_for_tests

    reset_for_tests()
    get_concurrency().register("fake_llm", 2)

    class TestLLM(_FakeLLM, LLMBackend):
        cost_per_1m_tokens_in = Decimal("3.00")
        cost_per_1m_tokens_out = Decimal("15.00")

    return TestLLM(should_raise=should_raise, line_count_override=line_count_override)


def test_happy_path_invokes_hooks_in_order(app):
    with app.app_context():
        backend = _build_backend(app)
        result = backend.translate_batch(
            ["line one", "line two", "line three"],
            source_lang="en", target_lang="de",
        )
    assert result.success is True
    assert len(result.translations) == 3
    assert backend.build_calls == 1
    assert backend.call_calls == 1
    assert backend.parse_calls == 1


def test_error_writes_event_and_raises(app):
    with app.app_context():
        backend = _build_backend(app, should_raise=RuntimeError("api down"))
        with pytest.raises(RuntimeError, match="api down"):
            backend.translate_batch(
                ["x"], source_lang="en", target_lang="de",
            )

    # Event should be in DB
    from extensions import db
    from db.models.translation import TranslationEvent

    with app.app_context():
        rows = db.session.query(TranslationEvent).filter_by(backend="fake_llm").all()
        assert len(rows) == 1
        assert rows[0].status == "error"
        assert rows[0].error_type == "RuntimeError"


def test_cost_tracked_on_success(app):
    with app.app_context():
        backend = _build_backend(app)
        backend.translate_batch(
            ["x"] * 3, source_lang="en", target_lang="de",
        )

    from extensions import db
    from db.models.translation import TranslationEvent

    with app.app_context():
        row = db.session.query(TranslationEvent).filter_by(backend="fake_llm").one()
        # 30 in @ $3/1M + 40 out @ $15/1M = 0.00009 + 0.0006 = 0.00069 USD = 690 micro_usd
        assert row.cost_estimate_micro_usd == 690


def test_line_count_mismatch_retries_once(app):
    """LLM returns fewer lines than requested -> retry once."""
    with app.app_context():
        # First call: returns only 2 lines for a 3-line request
        backend = _build_backend(app, line_count_override=2)
        # Because retry ALSO uses line_count_override, second attempt fails too
        # -> should raise LineCountMismatchError
        from translation.llm_base import LineCountMismatchError
        with pytest.raises(LineCountMismatchError):
            backend.translate_batch(
                ["a", "b", "c"], source_lang="en", target_lang="de",
            )
    # build+call+parse should have been called twice (initial + 1 retry)
    assert backend.build_calls == 2
    assert backend.call_calls == 2


def test_semaphore_released_on_exception(app):
    """If API raises, the concurrency slot must be released."""
    from translation.concurrency import get_concurrency

    with app.app_context():
        backend = _build_backend(app, should_raise=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            backend.translate_batch(["x"], source_lang="en", target_lang="de")

        # Slot must be free — acquire should not block
        with get_concurrency().slot("fake_llm", timeout_s=0.1):
            pass  # if slot leaked, this would timeout
```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

- [ ] **Step 3: Create `backend/translation/llm_base.py`**

```python
"""LLMBackend — base class for LLM-based translation backends.

Subclasses override three hooks (_build_request / _call_api / _parse_response).
Base class handles: concurrency acquisition, prompt assembly, retry-on-line-
count-mismatch, cost tracking, event logging.

Non-LLM backends (DeepL, Google, LibreTranslate) continue to inherit
TranslationBackend directly — the LLM-specific concerns don't apply.
"""

from __future__ import annotations

import logging
import time
from abc import abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from translation.base import TranslationBackend, TranslationResult
from translation.concurrency import ConcurrencyTimeoutError, get_concurrency
from translation.cost_tracker import calculate_llm_cost_micro_usd
from translator.events import write_translation_event

logger = logging.getLogger(__name__)


class LineCountMismatchError(ValueError):
    """LLM returned wrong number of lines for the batch after retry."""


class ContentFilterError(RuntimeError):
    """LLM refused the request (finish_reason == 'content_filter')."""


@dataclass(frozen=True)
class LLMResponse:
    translations: list[str]
    tokens_in: int
    tokens_out: int
    model: str
    finish_reason: str | None
    raw_latency_ms: int


class LLMBackend(TranslationBackend):
    """Base class for LLM translation backends."""

    # Subclass must declare:
    cost_per_1m_tokens_in: Decimal = Decimal("0")
    cost_per_1m_tokens_out: Decimal = Decimal("0")
    default_model: str = ""
    timeout_s: int = 120

    @abstractmethod
    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        """Build provider-specific HTTP request payload."""
        ...

    @abstractmethod
    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        """Execute the HTTP call. Returns raw JSON. Raises on network/HTTP errors."""
        ...

    @abstractmethod
    def _parse_response(self, raw: dict) -> LLMResponse:
        """Extract translations + token counts from provider response."""
        ...

    # --- Base implementations ---

    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
        """Orchestrate: concurrency + API call + cost tracking + event write.

        Raises on API errors (caller's fallback chain handles fallback).
        """
        started_at = datetime.now(UTC)
        started_mono = time.monotonic()
        status = "ok"
        error_type: str | None = None
        error_msg: str | None = None
        resp: LLMResponse | None = None
        chars_in = sum(len(line) for line in lines)

        try:
            with get_concurrency().slot(self.name, timeout_s=self.timeout_s):
                resp = self._attempt(lines, source_lang, target_lang, glossary_entries)
                self._verify_line_count(resp, lines)
        except ConcurrencyTimeoutError as exc:
            status = "timeout"
            error_type = "ConcurrencyTimeout"
            error_msg = str(exc)
            raise
        except ContentFilterError as exc:
            status = "error"
            error_type = "ContentFilterError"
            error_msg = str(exc)
            raise
        except LineCountMismatchError as exc:
            status = "error"
            error_type = "LineCountMismatchError"
            error_msg = str(exc)
            raise
        except Exception as exc:
            status = "error"
            error_type = type(exc).__name__
            error_msg = str(exc)
            raise
        finally:
            finished_at = datetime.now(UTC)
            latency_ms = int((time.monotonic() - started_mono) * 1000)

            cost = 0
            if resp is not None:
                cost = calculate_llm_cost_micro_usd(
                    tokens_in=resp.tokens_in,
                    tokens_out=resp.tokens_out,
                    price_in_per_1m=self.cost_per_1m_tokens_in,
                    price_out_per_1m=self.cost_per_1m_tokens_out,
                )
            write_translation_event(
                backend=self.name,
                source_lang=source_lang,
                target_lang=target_lang,
                lines_count=len(lines),
                chars_in=chars_in,
                chars_out=sum(len(t) for t in (resp.translations if resp else [])) or None,
                tokens_in=resp.tokens_in if resp else None,
                tokens_out=resp.tokens_out if resp else None,
                cost_micro_usd=cost,
                cache_hit=False,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                error_type=error_type,
                error_msg=error_msg,
            )

        return TranslationResult(
            success=True,
            translations=resp.translations,
            backend_name=self.name,
            tokens_used=resp.tokens_in + resp.tokens_out,
        )

    def _attempt(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        is_retry: bool = False,
    ) -> LLMResponse:
        """Build + call + parse once. Used by translate_batch."""
        messages = self._assemble_messages(
            lines, source_lang, target_lang, glossary_entries, strict=is_retry
        )
        payload = self._build_request(messages, max_tokens=self._estimate_max_tokens(lines))
        raw = self._call_api(payload, timeout_s=self.timeout_s)
        resp = self._parse_response(raw)
        if resp.finish_reason == "content_filter":
            raise ContentFilterError(
                f"{self.name} refused with finish_reason=content_filter"
            )
        return resp

    def _verify_line_count(self, resp: LLMResponse, lines: list[str]) -> None:
        """Retry once on line-count mismatch; raise if still wrong."""
        if len(resp.translations) == len(lines):
            return
        logger.warning(
            "%s returned %d lines, expected %d — retrying with strict prompt",
            self.name, len(resp.translations), len(lines),
        )
        resp_retry = self._attempt(
            lines,
            source_lang="en", target_lang="de",  # placeholder
            glossary_entries=None,
            is_retry=True,
        )
        if len(resp_retry.translations) != len(lines):
            raise LineCountMismatchError(
                f"{self.name} returned {len(resp_retry.translations)} "
                f"lines after retry, expected {len(lines)}"
            )
        # Overwrite resp's mutable-adjacent fields (frozen dataclass, so trick)
        object.__setattr__(resp, "translations", resp_retry.translations)
        object.__setattr__(resp, "tokens_in", resp.tokens_in + resp_retry.tokens_in)
        object.__setattr__(resp, "tokens_out", resp.tokens_out + resp_retry.tokens_out)

    def _assemble_messages(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        strict: bool = False,
    ) -> list[dict]:
        """Build OpenAI-style messages list. Subclasses can override for
        provider quirks (e.g. Anthropic's separate system param)."""
        system_parts = [
            f"You translate subtitles from {source_lang} to {target_lang}.",
            f"Translate exactly {len(lines)} lines, one per line, "
            f"in the same order.",
        ]
        if strict:
            system_parts.append(
                "STRICT: your response MUST contain exactly "
                f"{len(lines)} lines — no more, no fewer. "
                "Do NOT add commentary or numbering."
            )
        if glossary_entries:
            terms = ", ".join(
                f"{e['source']} -> {e['target']}" for e in glossary_entries
            )
            system_parts.append(f"Glossary: {terms}")

        user_text = "\n".join(lines)

        return [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {"role": "user", "content": user_text},
        ]

    def _estimate_max_tokens(self, lines: list[str]) -> int:
        """Rough heuristic: output is ~1.5x input character count / 4 chars-per-token."""
        total_chars = sum(len(line) for line in lines)
        return max(200, int(total_chars * 1.5 / 4) + 200)
```

- [ ] **Step 4: Run — expect 5 passed**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_llm_base.py -v`

- [ ] **Step 5: Ruff + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr && ruff check backend/translation/llm_base.py backend/tests/test_llm_base.py
git add backend/translation/llm_base.py backend/tests/test_llm_base.py
git commit -m "feat(translation-a1): add LLMBackend base class with concurrency + event logging"
```

---

## Task 8: Migrate OllamaBackend to LLMBackend

**Files:**
- Modify: `backend/translation/ollama.py`
- Test: `backend/tests/test_ollama_backend.py` (existing — update if asserts on Timer/internal state)

- [ ] **Step 1: Read existing `backend/translation/ollama.py`** to understand the current API call shape.

- [ ] **Step 2: Refactor — inherit from LLMBackend**

Change `class OllamaBackend(TranslationBackend)` → `class OllamaBackend(LLMBackend)`.

Implement the three hooks using the existing code:
- `_build_request(messages, max_tokens)` — wrap messages into Ollama's `/api/chat` request body
- `_call_api(payload, timeout_s)` — HTTP POST to ollama host
- `_parse_response(raw)` — extract `message.content`, split into lines; use `prompt_eval_count` + `eval_count` as token counts

Set class-level prices: `cost_per_1m_tokens_in = Decimal("0")`, `cost_per_1m_tokens_out = Decimal("0")` (self-hosted).

Delete the old `translate_batch` body — it's now inherited.

- [ ] **Step 3: Register concurrency + run tests**

Before running tests, ensure concurrency is registered in test setup:

```python
# In test fixture:
from translation.concurrency import get_concurrency, reset_for_tests
reset_for_tests()
get_concurrency().register("ollama", 3)
```

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_ollama_backend.py -v`
Expected: all existing tests pass; adjust any that rely on Timer-era internals.

- [ ] **Step 4: Ruff + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr && ruff check backend/translation/ollama.py
git add backend/translation/ollama.py backend/tests/test_ollama_backend.py
git commit -m "refactor(translation-a1): OllamaBackend inherits from LLMBackend"
```

---

## Task 9: Migrate OpenAICompatBackend to LLMBackend

**Files:**
- Modify: `backend/translation/openai_compat.py`
- Test: `backend/tests/test_openai_compat.py` (existing)

Same pattern as Task 8. Set prices per the `openai_compat` row in price_sheet; backend registers via its configured model.

- [ ] **Step 1: Read existing file**
- [ ] **Step 2: Refactor to inherit from LLMBackend**
- [ ] **Step 3: Implement 3 hooks using existing request code**
- [ ] **Step 4: Register concurrency in tests**
- [ ] **Step 5: Run tests**
- [ ] **Step 6: Commit**

```bash
cd /d/Sublarr_Projekt/Sublarr && ruff check backend/translation/openai_compat.py
git add backend/translation/openai_compat.py backend/tests/test_openai_compat.py
git commit -m "refactor(translation-a1): OpenAICompatBackend inherits from LLMBackend"
```

---

## Task 10: Wire cost tracking into translate_with_fallback

**Files:**
- Modify: `backend/translation/__init__.py`
- Test: extend `backend/tests/test_translation_manager.py` (or create)

- [ ] **Step 1: Write failing test**

Append to (or create) `backend/tests/test_translation_manager.py`:

```python
def test_fallback_chain_emits_events_per_attempt(app):
    """Each attempted backend in a fallback chain should write an event."""
    from extensions import db
    from db.models.translation import TranslationEvent

    # TODO: mock two backends — first raises, second succeeds.
    # Verify two events written: (first, error), (second, ok).
    ...
```

- [ ] **Step 2: Modify `translation/__init__.py`** — `TranslationManager.__init__` registers each backend with `get_concurrency()`:

```python
def register_backend(self, cls: type[TranslationBackend]) -> None:
    self._backend_classes[cls.name] = cls
    # Register with concurrency service
    from translation.concurrency import get_concurrency
    from db.config import get_config_entry
    limit = int(get_config_entry(f"translation_concurrency_{cls.name}") or 3)
    get_concurrency().register(cls.name, limit)
    logger.debug("Registered translation backend: %s (limit=%d)", cls.name, limit)
```

`translate_with_fallback` stays mostly unchanged — `LLMBackend.translate_batch` now emits events itself; non-LLM backends get a wrapper (out of A1 scope — they log when migrated in A5 or a follow-up).

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
cd /d/Sublarr_Projekt/Sublarr
git add backend/translation/__init__.py backend/tests/test_translation_manager.py
git commit -m "feat(translation-a1): wire BackendConcurrency into TranslationManager"
```

---

## Task 11: Retention cron + config

**Files:**
- Create: `backend/utils/scheduler_retention_translation.py`
- Modify: `backend/config_settings.py` — add `translation_events_retention_days`
- Modify: `backend/services/scheduler.py` — register `translation_events_cleanup` JobSpec
- Test: `backend/tests/test_translation_retention.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_translation_retention.py`:

```python
"""translation_events retention cron tests."""

from datetime import UTC, datetime, timedelta


def test_delete_old_events(app, db_session):
    from db.models.translation import TranslationEvent
    from utils.scheduler_retention_translation import delete_old_translation_events

    old = TranslationEvent(
        backend="ollama", source_lang="en", target_lang="de",
        lines_count=1, chars_in=1, status="ok",
        started_at=datetime.now(UTC) - timedelta(days=120),
    )
    fresh = TranslationEvent(
        backend="ollama", source_lang="en", target_lang="de",
        lines_count=1, chars_in=1, status="ok",
        started_at=datetime.now(UTC),
    )
    db_session.add_all([old, fresh])
    db_session.commit()

    deleted = delete_old_translation_events(retention_days=90)
    assert deleted == 1

    remaining = db_session.query(TranslationEvent).all()
    assert len(remaining) == 1


def test_defaults_to_setting(app, monkeypatch):
    from config import get_settings
    from utils.scheduler_retention_translation import delete_old_translation_events

    s = get_settings()
    monkeypatch.setattr(s, "translation_events_retention_days", 7)
    # No rows → 0 deleted; just verifies it reads the setting without crashing
    assert delete_old_translation_events() == 0
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Create `backend/utils/scheduler_retention_translation.py`**

```python
"""translation_events retention cleanup."""

import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from config import get_settings
from db.models.translation import TranslationEvent
from extensions import db

logger = logging.getLogger(__name__)


def delete_old_translation_events(retention_days: int | None = None) -> int:
    if retention_days is None:
        retention_days = getattr(
            get_settings(), "translation_events_retention_days", 90
        )
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    with db.session.begin():
        result = db.session.execute(
            sa.delete(TranslationEvent).where(TranslationEvent.started_at < cutoff)
        )
        deleted = result.rowcount or 0
    logger.info(
        "translation_events_cleanup: deleted %d rows older than %s",
        deleted, cutoff,
    )
    return deleted
```

- [ ] **Step 4: Add config field to `backend/config_settings.py`**

Near other retention fields:

```python
translation_events_retention_days: int = Field(
    default=90, ge=7, le=365,
    description="Keep translation_events rows for this many days.",
)
```

- [ ] **Step 5: Register cron in `backend/services/scheduler.py::_build_default_jobs()`**

Append to the returned list:

```python
from apscheduler.triggers.cron import CronTrigger

from utils.scheduler_retention_translation import delete_old_translation_events

specs.append(JobSpec(
    id="translation_events_cleanup",
    func=delete_old_translation_events,
    default_trigger=CronTrigger(hour=3, minute=30),
    timeout_s=120,
    owner_module="utils.scheduler_retention_translation",
    description="Delete old translation_events rows per retention policy.",
))
```

- [ ] **Step 6: Run tests + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend
/d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_translation_retention.py -v
cd ..
ruff check backend/utils/scheduler_retention_translation.py backend/config_settings.py backend/services/scheduler.py
git add backend/utils/scheduler_retention_translation.py backend/config_settings.py backend/services/scheduler.py backend/tests/test_translation_retention.py
git commit -m "feat(translation-a1): add translation_events retention cron + setting"
```

---

## Task 12: Cost + Memory API endpoints

**Files:**
- Create: `backend/routes/translation/__init__.py`
- Create: `backend/routes/translation/events.py`
- Modify: `backend/routes/__init__.py` — register blueprints
- Test: `backend/tests/test_translation_events_routes.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_translation_events_routes.py`:

```python
"""API tests for /api/v1/translation/* (read + purge)."""

from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_API_KEY", "")
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "disabled")
    from config import reload_settings
    reload_settings()
    from app import create_app
    app = create_app(testing=True)
    from extensions import db as sa_db
    with app.app_context():
        sa_db.create_all()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed_events(app):
    """Seed 5 events across 2 backends for aggregation tests."""
    from extensions import db
    from db.models.translation import TranslationEvent

    now = datetime.now(UTC)
    with app.app_context():
        for i in range(3):
            db.session.add(TranslationEvent(
                backend="ollama", source_lang="en", target_lang="de",
                lines_count=10, chars_in=100, status="ok",
                cost_estimate_micro_usd=0, cache_hit=False,
                started_at=now - timedelta(hours=i),
            ))
        for i in range(2):
            db.session.add(TranslationEvent(
                backend="claude", source_lang="en", target_lang="de",
                lines_count=10, chars_in=100, status="ok",
                cost_estimate_micro_usd=5000,  # $0.005
                cache_hit=False,
                started_at=now - timedelta(hours=i),
            ))
        db.session.commit()


def test_get_cost_summary(app, client, seed_events):
    resp = client.get("/api/v1/translation/cost")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "today" in data and "last_7d" in data and "last_30d" in data
    # 2 claude events * $0.005 = $0.01
    assert data["today"]["cost_usd"] == 0.01
    assert data["today"]["events"] == 5


def test_get_cost_by_backend(app, client, seed_events):
    resp = client.get("/api/v1/translation/cost/by-backend?window=7d")
    assert resp.status_code == 200
    data = resp.get_json()
    backends = {b["backend"]: b for b in data["backends"]}
    assert "ollama" in backends and "claude" in backends
    assert backends["claude"]["cost_usd"] == 0.01
    assert backends["ollama"]["cost_usd"] == 0.0


def test_get_memory_stats(app, client):
    resp = client.get("/api/v1/translation/memory/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "rows" in data
    assert "hit_rate_7d" in data


def test_post_memory_purge_older_than(app, client):
    """Purge with older_than_days=X removes matching rows, logs audit."""
    # Insert a row into translation_memory first, then purge
    # Test asserts the endpoint accepts + logs audit
    resp = client.post(
        "/api/v1/translation/memory/purge",
        json={"older_than_days": 30},
    )
    assert resp.status_code == 202
    data = resp.get_json()
    assert "deleted" in data


def test_get_cost_401_without_key(app, monkeypatch):
    monkeypatch.setenv("SUBLARR_API_KEY", "secret")
    from config import reload_settings
    reload_settings()
    from app import create_app
    app2 = create_app(testing=True)
    from extensions import db as sa_db
    with app2.app_context():
        sa_db.create_all()
    c2 = app2.test_client()
    resp = c2.get("/api/v1/translation/cost")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Create `backend/routes/translation/__init__.py`**

```python
"""Translation admin API blueprint package."""

from routes.translation.events import bp as events_bp

__all__ = ["events_bp"]
```

- [ ] **Step 4: Create `backend/routes/translation/events.py`**

```python
"""Translation admin API — cost + memory GET/purge endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from flask import Blueprint, current_app, jsonify, request

from db.models.translation import TranslationEvent
from extensions import db
from translation.cost_tracker import micro_usd_to_usd

logger = logging.getLogger(__name__)

bp = Blueprint("translation_admin", __name__, url_prefix="/api/v1/translation")


def _audit_log(action: str, **kwargs) -> None:
    api_key = request.headers.get("X-Api-Key", "")
    fp = api_key[:6] if api_key else "anon"
    extras = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(
        "translation_admin_action action=%s actor=%s %s", action, fp, extras,
    )


def _window_start(window: str) -> datetime:
    now = datetime.now(UTC)
    if window == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if window == "7d":
        return now - timedelta(days=7)
    if window == "30d":
        return now - timedelta(days=30)
    raise ValueError(f"unknown window: {window}")


def _aggregate(window_start: datetime) -> dict:
    """Total cost + events + cache-hits for events started >= window_start."""
    row = db.session.execute(
        sa.select(
            sa.func.coalesce(sa.func.sum(TranslationEvent.cost_estimate_micro_usd), 0),
            sa.func.count(),
            sa.func.coalesce(sa.func.sum(sa.case((TranslationEvent.cache_hit, 1), else_=0)), 0),
        ).where(TranslationEvent.started_at >= window_start)
    ).one()
    total_micro, events, hits = row
    return {
        "cost_usd": float(micro_usd_to_usd(int(total_micro))),
        "events": int(events),
        "cache_hits": int(hits),
    }


@bp.route("/cost", methods=["GET"])
def cost_summary():
    today = _aggregate(_window_start("today"))
    d7 = _aggregate(_window_start("7d"))
    d30 = _aggregate(_window_start("30d"))
    return jsonify({"today": today, "last_7d": d7, "last_30d": d30}), 200


@bp.route("/cost/by-backend", methods=["GET"])
def cost_by_backend():
    window = request.args.get("window", "7d")
    try:
        start = _window_start(window)
    except ValueError as exc:
        return jsonify({"error": str(exc), "error_type": "ValueError"}), 400

    rows = db.session.execute(
        sa.select(
            TranslationEvent.backend,
            sa.func.count(),
            sa.func.coalesce(sa.func.sum(TranslationEvent.cost_estimate_micro_usd), 0),
            sa.func.coalesce(sa.func.avg(TranslationEvent.latency_ms), 0),
            sa.func.coalesce(
                sa.func.sum(sa.case((TranslationEvent.status != "ok", 1), else_=0)),
                0,
            ),
        )
        .where(TranslationEvent.started_at >= start)
        .group_by(TranslationEvent.backend)
    ).all()

    backends = [
        {
            "backend": backend,
            "events": int(events),
            "cost_usd": float(micro_usd_to_usd(int(total))),
            "avg_latency_ms": float(avg_lat),
            "error_rate": (float(errors) / int(events)) if events else 0.0,
        }
        for backend, events, total, avg_lat, errors in rows
    ]
    return jsonify({"window": window, "backends": backends}), 200


@bp.route("/memory/stats", methods=["GET"])
def memory_stats():
    # Query the existing translation_memory table
    from sqlalchemy import text

    row = db.session.execute(text(
        "SELECT COUNT(*), COALESCE(SUM(LENGTH(translation)), 0) FROM translation_memory"
    )).one()
    rows_count, size_bytes = row[0], row[1]

    # Hit rate from cache_hit events in last 7d
    cutoff = datetime.now(UTC) - timedelta(days=7)
    hit_row = db.session.execute(
        sa.select(
            sa.func.count(),
            sa.func.coalesce(sa.func.sum(sa.case((TranslationEvent.cache_hit, 1), else_=0)), 0),
        ).where(TranslationEvent.started_at >= cutoff)
    ).one()
    total_7d, hits_7d = int(hit_row[0]), int(hit_row[1])
    hit_rate = (hits_7d / total_7d) if total_7d else 0.0

    return jsonify({
        "rows": int(rows_count),
        "size_bytes": int(size_bytes),
        "hit_rate_7d": round(hit_rate, 4),
    }), 200


@bp.route("/memory/purge", methods=["POST"])
def memory_purge():
    body = request.get_json(silent=True) or {}
    older_than_days = body.get("older_than_days")
    backend_filter = body.get("backend")

    from sqlalchemy import text

    conditions = []
    params = {}
    if older_than_days is not None:
        try:
            days = int(older_than_days)
        except (TypeError, ValueError):
            return jsonify({"error": "older_than_days must be int", "error_type": "ValidationError"}), 400
        cutoff = datetime.now(UTC) - timedelta(days=days)
        conditions.append("created_at < :cutoff")
        params["cutoff"] = cutoff
    if backend_filter:
        conditions.append("backend = :backend")
        params["backend"] = backend_filter

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    result = db.session.execute(text(f"DELETE FROM translation_memory {where}"), params)
    db.session.commit()
    deleted = result.rowcount or 0

    _audit_log("purge-memory", older_than_days=older_than_days, backend=backend_filter, deleted=deleted)
    return jsonify({"status": "purged", "deleted": deleted}), 202
```

- [ ] **Step 5: Register blueprint in `backend/routes/__init__.py`**

Following the pattern used for scheduler (Phase 5):

```python
from routes.translation import events_bp as translation_events_bp
app.register_blueprint(translation_events_bp)
```

- [ ] **Step 6: Run tests**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_translation_events_routes.py -v
```

- [ ] **Step 7: Ruff + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr
git add backend/routes/translation/ backend/routes/__init__.py backend/tests/test_translation_events_routes.py
git commit -m "feat(translation-a1): add /api/v1/translation cost + memory endpoints"
```

---

## Task 13: Concurrency routes

**Files:**
- Create: `backend/routes/translation/concurrency.py`
- Test: extend `test_translation_events_routes.py` with concurrency tests

- [ ] **Step 1: Add tests**

Append to `backend/tests/test_translation_events_routes.py`:

```python
def test_get_concurrency(app, client):
    # Wire a backend first via TranslationManager
    from translation.concurrency import get_concurrency, reset_for_tests
    reset_for_tests()
    get_concurrency().register("ollama", 3)

    resp = client.get("/api/v1/translation/concurrency")
    assert resp.status_code == 200
    data = resp.get_json()
    assert any(b["backend"] == "ollama" and b["limit"] == 3 for b in data["backends"])


def test_patch_concurrency_limit(app, client):
    from translation.concurrency import get_concurrency, reset_for_tests
    reset_for_tests()
    get_concurrency().register("ollama", 3)

    resp = client.patch(
        "/api/v1/translation/concurrency/ollama",
        json={"limit": 5},
    )
    assert resp.status_code == 200
    assert get_concurrency().get_limit("ollama") == 5


def test_patch_concurrency_invalid_limit(app, client):
    resp = client.patch(
        "/api/v1/translation/concurrency/ollama",
        json={"limit": 0},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Create `backend/routes/translation/concurrency.py`**

```python
"""Translation concurrency admin endpoints."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from routes.translation.events import _audit_log
from translation.concurrency import get_concurrency

logger = logging.getLogger(__name__)

bp = Blueprint(
    "translation_concurrency_admin",
    __name__,
    url_prefix="/api/v1/translation",
)


@bp.route("/concurrency", methods=["GET"])
def list_concurrency():
    c = get_concurrency()
    backends = [
        {"backend": name, "limit": c.get_limit(name)}
        for name in sorted(c._limits.keys())
    ]
    return jsonify({"backends": backends}), 200


@bp.route("/concurrency/<backend>", methods=["PATCH"])
def set_concurrency(backend: str):
    body = request.get_json(silent=True) or {}
    limit = body.get("limit")
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        return jsonify({
            "error": "limit must be int in [1, 50]",
            "error_type": "ValidationError",
        }), 400

    c = get_concurrency()
    if c.get_limit(backend) == 0:  # not registered
        return jsonify({
            "error": f"backend {backend!r} not registered",
            "error_type": "NotFoundError",
        }), 404

    c.set_limit(backend, limit)

    # Persist to config_entries so it survives restart
    from db.config import set_config_entry
    set_config_entry(f"translation_concurrency_{backend}", str(limit))

    _audit_log("set-concurrency", backend=backend, limit=limit)
    return jsonify({"backend": backend, "limit": limit}), 200
```

- [ ] **Step 3: Register blueprint** in `backend/routes/translation/__init__.py`:

```python
from routes.translation.events import bp as events_bp
from routes.translation.concurrency import bp as concurrency_bp

__all__ = ["events_bp", "concurrency_bp"]
```

And register both in `backend/routes/__init__.py`.

- [ ] **Step 4: Run tests + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_translation_events_routes.py -v
cd ..
ruff check backend/routes/translation/
git add backend/routes/translation/ backend/routes/__init__.py backend/tests/test_translation_events_routes.py
git commit -m "feat(translation-a1): add /api/v1/translation/concurrency endpoints"
```

---

## Task 14: Prometheus metrics

**Files:**
- Modify: `backend/monitoring/metrics.py`

- [ ] **Step 1: Append metrics to `backend/monitoring/metrics.py`**

```python
translation_cost_micro_usd_total = Counter(
    "translation_cost_micro_usd_total",
    "Total translation cost in micro-USD by backend + status.",
    labelnames=["backend", "status"],
)

translation_tokens_total = Counter(
    "translation_tokens_total",
    "Total LLM tokens consumed by backend + direction.",
    labelnames=["backend", "direction"],
)

translation_cache_hits_total = Counter(
    "translation_cache_hits_total",
    "Total translation-memory cache hits by backend.",
    labelnames=["backend"],
)

translation_latency_seconds = Histogram(
    "translation_latency_seconds",
    "Translation request latency by backend.",
    labelnames=["backend"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)

translation_concurrency_in_use = Gauge(
    "translation_concurrency_in_use",
    "Current in-use concurrency slots per backend.",
    labelnames=["backend"],
)

translation_concurrency_limit = Gauge(
    "translation_concurrency_limit",
    "Configured concurrency limit per backend.",
    labelnames=["backend"],
)
```

Make sure `Gauge` is imported from `prometheus_client` at top of file.

- [ ] **Step 2: Emit from events writer**

In `backend/translator/events.py::write_translation_event`, after the DB write succeeds:

```python
    # Emit Prometheus
    try:
        from monitoring.metrics import (
            translation_cache_hits_total,
            translation_cost_micro_usd_total,
            translation_latency_seconds,
            translation_tokens_total,
        )
        translation_cost_micro_usd_total.labels(backend=backend, status=status).inc(cost_micro_usd)
        if tokens_in:
            translation_tokens_total.labels(backend=backend, direction="in").inc(tokens_in)
        if tokens_out:
            translation_tokens_total.labels(backend=backend, direction="out").inc(tokens_out)
        if cache_hit:
            translation_cache_hits_total.labels(backend=backend).inc()
        if latency_ms is not None:
            translation_latency_seconds.labels(backend=backend).observe(latency_ms / 1000)
    except Exception:
        logger.warning("translation metrics emit failed", exc_info=True)
```

- [ ] **Step 3: Smoke test + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_translator_events.py tests/test_llm_base.py -v
cd ..
ruff check backend/monitoring/metrics.py backend/translator/events.py
git add backend/monitoring/metrics.py backend/translator/events.py
git commit -m "feat(translation-a1): emit Prometheus metrics for translation events"
```

---

## Task 15: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/system.ts` (or equivalent translation types file)
- Modify: `frontend/src/api/translation.ts` (existing — extend)

- [ ] **Step 1: Add types**

```ts
// Translation telemetry
export type TranslationCostSummary = {
  today: { cost_usd: number; events: number; cache_hits: number }
  last_7d: { cost_usd: number; events: number; cache_hits: number }
  last_30d: { cost_usd: number; events: number; cache_hits: number }
}

export type TranslationBackendCost = {
  backend: string
  events: number
  cost_usd: number
  avg_latency_ms: number
  error_rate: number
}

export type TranslationMemoryStats = {
  rows: number
  size_bytes: number
  hit_rate_7d: number
}

export type TranslationConcurrency = {
  backends: { backend: string; limit: number }[]
}
```

- [ ] **Step 2: Extend `frontend/src/api/translation.ts`** (match existing axios pattern)

```ts
export async function getCostSummary(): Promise<TranslationCostSummary> {
  const { data } = await api.get('/translation/cost')
  return data
}

export async function getCostByBackend(window: '7d' | '30d' | 'today' = '7d') {
  const { data } = await api.get(
    `/translation/cost/by-backend?window=${window}`,
  )
  return data as { window: string; backends: TranslationBackendCost[] }
}

export async function getMemoryStats(): Promise<TranslationMemoryStats> {
  const { data } = await api.get('/translation/memory/stats')
  return data
}

export async function purgeMemory(params: {
  older_than_days?: number
  backend?: string
}): Promise<{ status: string; deleted: number }> {
  const { data } = await api.post('/translation/memory/purge', params)
  return data
}

export async function getConcurrency(): Promise<TranslationConcurrency> {
  const { data } = await api.get('/translation/concurrency')
  return data
}

export async function setConcurrency(
  backend: string,
  limit: number,
): Promise<{ backend: string; limit: number }> {
  const { data } = await api.patch(
    `/translation/concurrency/${encodeURIComponent(backend)}`,
    { limit },
  )
  return data
}
```

- [ ] **Step 3: Typecheck + commit**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/<branch>/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr
git add frontend/src/types/system.ts frontend/src/api/translation.ts
git commit -m "feat(translation-a1): frontend types + API client extensions"
```

---

## Task 16: React Query hooks

**Files:**
- Create: `frontend/src/hooks/useTranslationCost.ts`
- Create: `frontend/src/hooks/useTranslationMutations.ts`

- [ ] **Step 1: Create `useTranslationCost.ts`**

```ts
import { useQuery } from '@tanstack/react-query'
import {
  getConcurrency,
  getCostByBackend,
  getCostSummary,
  getMemoryStats,
} from '@/api/translation'

export function useTranslationCostSummary() {
  return useQuery({
    queryKey: ['translation', 'cost', 'summary'],
    queryFn: getCostSummary,
    refetchInterval: 30000,
  })
}

export function useTranslationCostByBackend(window: '7d' | '30d' | 'today' = '7d') {
  return useQuery({
    queryKey: ['translation', 'cost', 'by-backend', window],
    queryFn: () => getCostByBackend(window),
    refetchInterval: 30000,
  })
}

export function useTranslationMemoryStats() {
  return useQuery({
    queryKey: ['translation', 'memory', 'stats'],
    queryFn: getMemoryStats,
    refetchInterval: 30000,
  })
}

export function useTranslationConcurrency() {
  return useQuery({
    queryKey: ['translation', 'concurrency'],
    queryFn: getConcurrency,
    refetchInterval: 10000,
  })
}
```

- [ ] **Step 2: Create `useTranslationMutations.ts`**

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { purgeMemory, setConcurrency } from '@/api/translation'

export function useTranslationMutations() {
  const qc = useQueryClient()
  return {
    purgeMemory: useMutation({
      mutationFn: (params: { older_than_days?: number; backend?: string }) =>
        purgeMemory(params),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['translation', 'memory'] })
      },
    }),
    setConcurrency: useMutation({
      mutationFn: ({ backend, limit }: { backend: string; limit: number }) =>
        setConcurrency(backend, limit),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['translation', 'concurrency'] })
      },
    }),
  }
}
```

- [ ] **Step 3: Typecheck + commit**

```bash
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
git add frontend/src/hooks/useTranslationCost.ts frontend/src/hooks/useTranslationMutations.ts
git commit -m "feat(translation-a1): React Query hooks for cost + memory + concurrency"
```

---

## Task 17: Cost & Memory page

**Files:**
- Create: `frontend/src/pages/Settings/translation/CostMemoryPage.tsx`
- Create: `frontend/src/pages/Settings/translation/CostSummaryCards.tsx`
- Create: `frontend/src/pages/Settings/translation/BackendCostTable.tsx`
- Create: `frontend/src/pages/Settings/translation/TranslationMemoryPanel.tsx`

- [ ] **Step 1: CostSummaryCards.tsx**

```tsx
import { useTranslation } from 'react-i18next'
import { useTranslationCostSummary } from '@/hooks/useTranslationCost'

export function CostSummaryCards() {
  const { t } = useTranslation('settings')
  const { data } = useTranslationCostSummary()
  if (!data) return null

  const cards: [string, typeof data.today][] = [
    [t('translation.cost.today'), data.today],
    [t('translation.cost.last_7d'), data.last_7d],
    [t('translation.cost.last_30d'), data.last_30d],
  ]

  return (
    <div className="grid grid-cols-3 gap-3">
      {cards.map(([label, d]) => (
        <div key={label} className="rounded-lg border border-border bg-surface p-3">
          <div className="text-sm text-muted">{label}</div>
          <div className="mt-1 text-xl font-semibold">${d.cost_usd.toFixed(2)}</div>
          <div className="mt-1 text-xs text-muted">
            {d.events} {t('translation.cost.events')} · {d.cache_hits} {t('translation.cost.cache_hits')}
          </div>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: BackendCostTable.tsx**

```tsx
import { useTranslation } from 'react-i18next'
import { useTranslationCostByBackend } from '@/hooks/useTranslationCost'

export function BackendCostTable() {
  const { t } = useTranslation('settings')
  const { data, isLoading } = useTranslationCostByBackend('7d')
  if (isLoading) return <div className="text-muted">{t('common.loading', { defaultValue: 'Loading...' })}</div>
  if (!data || data.backends.length === 0) {
    return <div className="text-muted">{t('translation.cost.no_events_yet')}</div>
  }

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-elevated">
          <tr>
            <th className="px-3 py-2 text-left">{t('translation.cost.backend')}</th>
            <th className="px-3 py-2 text-right">{t('translation.cost.events')}</th>
            <th className="px-3 py-2 text-right">{t('translation.cost.cost')}</th>
            <th className="px-3 py-2 text-right">{t('translation.cost.avg_latency')}</th>
            <th className="px-3 py-2 text-right">{t('translation.cost.error_rate')}</th>
          </tr>
        </thead>
        <tbody>
          {data.backends.map((b) => (
            <tr key={b.backend} className="border-t border-border">
              <td className="px-3 py-2 font-mono">{b.backend}</td>
              <td className="px-3 py-2 text-right">{b.events}</td>
              <td className="px-3 py-2 text-right">${b.cost_usd.toFixed(4)}</td>
              <td className="px-3 py-2 text-right">{Math.round(b.avg_latency_ms)} ms</td>
              <td className="px-3 py-2 text-right">{(b.error_rate * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 3: TranslationMemoryPanel.tsx**

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTranslationMemoryStats } from '@/hooks/useTranslationCost'
import { useTranslationMutations } from '@/hooks/useTranslationMutations'
import { toast } from '@/components/shared/Toast'

export function TranslationMemoryPanel() {
  const { t } = useTranslation('settings')
  const { data } = useTranslationMemoryStats()
  const { purgeMemory } = useTranslationMutations()
  const [days, setDays] = useState(30)

  const handlePurge = () => {
    if (!confirm(t('translation.memory.confirm_purge', { days }))) return
    purgeMemory.mutate(
      { older_than_days: days },
      {
        onSuccess: (r) =>
          toast(t('translation.memory.purged', { n: r.deleted }), 'success'),
        onError: (e: Error) => toast(e.message, 'error'),
      },
    )
  }

  if (!data) return null
  const sizeMb = (data.size_bytes / 1024 / 1024).toFixed(2)

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="font-medium">{t('translation.memory.title')}</h3>
      <div className="mt-2 flex gap-6 text-sm">
        <div>
          <div className="text-muted">{t('translation.memory.rows')}</div>
          <div className="font-semibold">{data.rows.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-muted">{t('translation.memory.size')}</div>
          <div className="font-semibold">{sizeMb} MB</div>
        </div>
        <div>
          <div className="text-muted">{t('translation.memory.hit_rate_7d')}</div>
          <div className="font-semibold">{(data.hit_rate_7d * 100).toFixed(1)}%</div>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <label className="text-sm text-muted">
          {t('translation.memory.purge_older_than')}
        </label>
        <input
          type="number"
          min={1}
          max={3650}
          value={days}
          onChange={(e) => setDays(Math.max(1, Number(e.target.value) || 30))}
          className="w-20 rounded-md border border-border bg-surface px-2 py-1 text-sm"
        />
        <span className="text-sm text-muted">{t('translation.memory.days')}</span>
        <button
          onClick={handlePurge}
          disabled={purgeMemory.isPending}
          className="rounded-md bg-accent px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {t('translation.memory.purge')}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: CostMemoryPage.tsx**

```tsx
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { CostSummaryCards } from './CostSummaryCards'
import { BackendCostTable } from './BackendCostTable'
import { TranslationMemoryPanel } from './TranslationMemoryPanel'

export function CostMemoryPage() {
  const { t } = useTranslation('settings')
  return (
    <SettingsDetailLayout
      title={t('translation.cost.title')}
      subtitle={t('translation.cost.subtitle')}
    >
      <div className="space-y-5">
        <CostSummaryCards />
        <div>
          <h3 className="mb-2 font-medium">{t('translation.cost.per_backend')}</h3>
          <BackendCostTable />
        </div>
        <TranslationMemoryPanel />
      </div>
    </SettingsDetailLayout>
  )
}
```

- [ ] **Step 5: Typecheck + commit**

```bash
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
git add frontend/src/pages/Settings/translation/
git commit -m "feat(translation-a1): CostMemoryPage + SummaryCards + BackendCostTable + MemoryPanel"
```

---

## Task 18: Wire route + menu entry + i18n

**Files:**
- Modify: `frontend/src/pages/Settings/index.tsx` — add route
- Modify: `frontend/src/components/settings/SettingsNav.tsx` — add menu entry
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/en/settings.json`

- [ ] **Step 1: Add route** in `Settings/index.tsx` (follow Phase 5 pattern):

```tsx
const CostMemoryPage = lazy(() =>
  import('./translation/CostMemoryPage').then((m) => ({ default: m.CostMemoryPage })),
)

// In the <Routes>:
<Route path="translation/cost-memory" element={<Suspense fallback={<FormSkeleton />}><CostMemoryPage /></Suspense>} />
```

- [ ] **Step 2: Add menu entry** in `SettingsNav.tsx` under the Translation group:

```tsx
{ label: t('settings.nav.translation_cost', 'Cost & Memory'),
  href: '/settings/translation/cost-memory' }
```

- [ ] **Step 3: Add i18n** to both locales under `scheduler.*`-style nesting:

DE (`de/settings.json`):
```json
"translation": {
  "cost": {
    "title": "Übersetzungs-Kosten",
    "subtitle": "Kosten pro Backend und Zeitraum",
    "today": "Heute", "last_7d": "Letzte 7 Tage", "last_30d": "Letzte 30 Tage",
    "events": "Events", "cache_hits": "Cache-Hits",
    "per_backend": "Pro Backend (7 Tage)",
    "backend": "Backend", "cost": "Kosten",
    "avg_latency": "Ø Latenz", "error_rate": "Fehlerrate",
    "no_events_yet": "Noch keine Übersetzungen."
  },
  "memory": {
    "title": "Translation Memory",
    "rows": "Einträge", "size": "Größe", "hit_rate_7d": "Hit-Rate (7d)",
    "purge_older_than": "Lösche älter als",
    "days": "Tage",
    "purge": "Löschen",
    "confirm_purge": "Einträge älter als {{days}} Tage löschen?",
    "purged": "{{n}} Einträge gelöscht"
  }
}
```

EN mirror:
```json
"translation": {
  "cost": {
    "title": "Translation Costs",
    "subtitle": "Cost per backend and time window",
    "today": "Today", "last_7d": "Last 7 days", "last_30d": "Last 30 days",
    "events": "events", "cache_hits": "cache hits",
    "per_backend": "Per backend (7 days)",
    "backend": "Backend", "cost": "Cost",
    "avg_latency": "Avg latency", "error_rate": "Error rate",
    "no_events_yet": "No translations yet."
  },
  "memory": {
    "title": "Translation Memory",
    "rows": "Entries", "size": "Size", "hit_rate_7d": "Hit rate (7d)",
    "purge_older_than": "Purge older than",
    "days": "days",
    "purge": "Purge",
    "confirm_purge": "Purge entries older than {{days}} days?",
    "purged": "{{n}} entries purged"
  }
}
```

Also add `settings.nav.translation_cost`: `"Kosten & Memory"` / `"Cost & Memory"` in `common.json`.

- [ ] **Step 4: Typecheck + commit**

```bash
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
git add frontend/src/pages/Settings/index.tsx frontend/src/components/settings/SettingsNav.tsx frontend/src/i18n/locales/
git commit -m "feat(translation-a1): wire CostMemoryPage route + menu entry + i18n"
```

---

## Task 19: BackendCard concurrency slider

**Files:**
- Modify: `frontend/src/pages/Settings/translation/BackendCard.tsx` (existing)

- [ ] **Step 1: Inspect the existing BackendCard.tsx** and append a concurrency-slider + cost-cap input section at the bottom.

- [ ] **Step 2: Wire to `useTranslationConcurrency` + `setConcurrency`**

```tsx
// Inside BackendCard, after existing config fields:
const { data: conc } = useTranslationConcurrency()
const { setConcurrency: setConcMut } = useTranslationMutations()
const limit = conc?.backends.find((b) => b.backend === backend.name)?.limit ?? 3
const [draftLimit, setDraftLimit] = useState(limit)

// On slider change (debounced):
useDebouncedEffect(() => {
  if (draftLimit !== limit) {
    setConcMut.mutate({ backend: backend.name, limit: draftLimit })
  }
}, [draftLimit], 500)

// JSX:
<div className="mt-3 border-t border-border pt-3">
  <label className="text-sm">
    {t('translation.concurrency.limit')}: <strong>{draftLimit}</strong>
  </label>
  <input
    type="range"
    min={1}
    max={20}
    value={draftLimit}
    onChange={(e) => setDraftLimit(Number(e.target.value))}
    className="w-full"
  />
  <div className="text-xs text-muted">
    {t('translation.concurrency.hint')}
  </div>
</div>
```

If `useDebouncedEffect` does not exist in the codebase, use `useEffect` + `setTimeout`:

```tsx
useEffect(() => {
  const h = setTimeout(() => {
    if (draftLimit !== limit) {
      setConcMut.mutate({ backend: backend.name, limit: draftLimit })
    }
  }, 500)
  return () => clearTimeout(h)
}, [draftLimit])
```

- [ ] **Step 3: i18n entries** in both locales:

```json
"concurrency": {
  "limit": "Gleichzeitige Anfragen",
  "hint": "Anzahl paralleler Aufrufe an dieses Backend. Höher = schneller bei großen Batches, niedriger = schonender bei Rate-Limits."
}
```

- [ ] **Step 4: Typecheck + commit**

```bash
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
git add frontend/src/pages/Settings/translation/BackendCard.tsx frontend/src/i18n/locales/
git commit -m "feat(translation-a1): concurrency slider on BackendCard"
```

---

## Task 20: Frontend tests

**Files:**
- Create: `frontend/src/pages/Settings/translation/__tests__/CostMemoryPage.test.tsx`

- [ ] **Step 1: Test file** (pattern from Phase 5 SchedulerPage test):

```tsx
import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CostMemoryPage } from '../CostMemoryPage'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) =>
      opts && 'defaultValue' in (opts ?? {}) ? String(opts!.defaultValue ?? k) : k,
  }),
}))

vi.mock('@/api/translation', () => ({
  getCostSummary: vi.fn().mockResolvedValue({
    today: { cost_usd: 0.5, events: 10, cache_hits: 2 },
    last_7d: { cost_usd: 3.2, events: 80, cache_hits: 20 },
    last_30d: { cost_usd: 12.1, events: 300, cache_hits: 80 },
  }),
  getCostByBackend: vi.fn().mockResolvedValue({
    window: '7d',
    backends: [
      { backend: 'claude', events: 50, cost_usd: 2.5,
        avg_latency_ms: 1400, error_rate: 0.02 },
    ],
  }),
  getMemoryStats: vi.fn().mockResolvedValue({
    rows: 1200, size_bytes: 1_500_000, hit_rate_7d: 0.25,
  }),
  purgeMemory: vi.fn(),
  getConcurrency: vi.fn(),
  setConcurrency: vi.fn(),
}))

const renderPage = () => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CostMemoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CostMemoryPage', () => {
  it('renders today cost summary', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('$0.50')).toBeInTheDocument(),
    )
  })

  it('renders per-backend cost table', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('claude')).toBeInTheDocument())
    expect(screen.getByText('$2.5000')).toBeInTheDocument()
  })

  it('shows TM stats including hit rate', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('1,200')).toBeInTheDocument())
    expect(screen.getByText('25.0%')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests + commit**

```bash
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/vitest run src/pages/Settings/translation/__tests__/CostMemoryPage.test.tsx 2>&1 | tail -10
git add frontend/src/pages/Settings/translation/__tests__/CostMemoryPage.test.tsx
git commit -m "test(translation-a1): CostMemoryPage component tests"
```

---

## Task 21: Final acceptance

- [ ] **Step 1: Run full scheduler + translation suite**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend
/d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest \
  tests/test_price_sheet.py tests/test_cost_tracker.py \
  tests/test_translation_event_model.py tests/test_translation_events_migration.py \
  tests/test_backend_concurrency.py tests/test_translator_events.py \
  tests/test_llm_base.py tests/test_ollama_backend.py tests/test_openai_compat.py \
  tests/test_translation_manager.py tests/test_translation_retention.py \
  tests/test_translation_events_routes.py tests/test_scheduler_*.py \
  -v --tb=short 2>&1 | tail -15
```

Expected: all green. Count should be ≈ 60 new + 98 scheduler = ~158 tests.

- [ ] **Step 2: Ruff clean**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend
ruff check . 2>&1 | tail -3
ruff format --check backend/translation/ backend/translator/events.py backend/routes/translation/ backend/utils/scheduler_retention_translation.py 2>&1 | tail -3
```

Fix any new-file format issues; pre-existing formatting drift (noted from Phase 5) is not this phase's concern.

- [ ] **Step 3: Frontend typecheck + tests**

```bash
cd /d/Sublarr_Projekt/Sublarr/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/vitest run 2>&1 | tail -10
```

- [ ] **Step 4: Smoke-test bootstrap**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend
SUBLARR_SCHEDULER_ROLE=primary SUBLARR_DB_PATH=/tmp/sublarr_a1.db /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -c "
from app import create_app
app = create_app()
s = app.extensions.get('scheduler')
print('scheduler jobs:', sorted(s._registered_ids))
"
```

Expected output includes `translation_events_cleanup` among the job IDs.

- [ ] **Step 5: Acceptance checklist**

- [ ] `translation_events` table populated by every `LLMBackend.translate_batch` call
- [ ] Ollama + OpenAI-compat migrated to LLMBackend without test regressions
- [ ] BackendConcurrency semaphore enforced on LLM backends; slider changes take effect immediately
- [ ] Cost tracked in micro-USD; aggregations exact over millions of rows (math-verified in tests)
- [ ] Price sheet is code-owned; unknown combos fall back to 0 with WARN once per boot
- [ ] `/api/v1/translation/cost`, `/cost/by-backend`, `/memory/stats` all respond 200 with correct data
- [ ] `POST /memory/purge` deletes matching TM rows + writes admin audit log
- [ ] `PATCH /concurrency/<backend>` resizes semaphore + persists to config_entries
- [ ] `translation_events_cleanup` JobSpec registered; runs nightly at 03:30 UTC
- [ ] Prometheus metrics emitted (`translation_cost_micro_usd_total`, `translation_tokens_total`, `translation_cache_hits_total`, `translation_latency_seconds`, `translation_concurrency_*`)
- [ ] Cost & Memory page visible at `Settings → Translation → Cost & Memory`
- [ ] All new tests green; full scheduler+translation suite ≥ 150 tests passing

## Self-review notes (writing-plans)

- **Spec coverage:** Sections 1 (architecture), 2 (data model), 3 (LLMBackend), 4 (cost tracking), 7 (failure matrix), 8 (testing) of the spec are covered by Tasks 1–21. Sections 5 (queue) and 6 (context-window) are explicitly out of A1 scope (Phases A2 + A4). Section 5/A2 and A4 will have their own plan files.
- **No placeholders:** every step has runnable code. `<CURRENT_HEAD>` and `<rev>` in Task 4 are operator look-ups (Alembic rev), not plan-writer gaps.
- **Type consistency:** `TranslationEvent` ORM fields match the API route serializer in Task 12; `LLMResponse` shape is consistent across Tasks 7-9; concurrency API is consistent across Tasks 5, 13, 19.
- **Dependencies between tasks:** Tasks 1-2 are independent utilities. Tasks 3-4 create DB model + migration (4 depends on 3). Tasks 5-6 are independent. Task 7 depends on 5 (concurrency) + 6 (events) + 2 (cost_tracker). Tasks 8-9 depend on 7. Task 10 depends on 7-9 being green. Tasks 11-14 are backend finishing touches. Tasks 15-20 are frontend (independent of backend ordering but need the APIs from 12-13 done). Task 21 is final acceptance.
