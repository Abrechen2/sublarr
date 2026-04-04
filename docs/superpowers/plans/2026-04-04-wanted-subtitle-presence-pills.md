# Wanted Subtitle Presence Pills — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plain-text "Vorhanden" column in the Wanted table with pill-based subtitle presence indicators that show target-language status and all embedded subtitle streams.

**Architecture:** New `get_all_subtitle_streams()` in `ass_utils.py` scans all embedded streams, stored in a new `embedded_languages` JSON column on `wanted_items`. Frontend renders a `SubtitlePresencePills` component using this data plus the existing `existing_sub` field and `source_language` config setting for sort priority.

**Tech Stack:** Python/SQLAlchemy (backend), Alembic (migration), React 19 + TypeScript (frontend), Vitest (frontend tests), pytest (backend tests)

**Spec:** `docs/superpowers/specs/2026-04-04-wanted-subtitle-presence-pills-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/ass_utils.py` | Add `get_all_subtitle_streams()` |
| Modify | `backend/db/models/core.py` | Add `embedded_languages` column to `WantedItem` |
| Create | `backend/db/migrations/versions/e1f2a3b4c5d6_add_embedded_languages.py` | Alembic migration |
| Modify | `backend/db/repositories/wanted.py` | Pass + parse `embedded_languages` |
| Modify | `backend/db/wanted.py` | Add param to public wrapper |
| Modify | `backend/services/wanted_scanner_core.py` | Detect all streams, pass to upsert (2 call sites) |
| Create | `backend/tests/test_embedded_streams.py` | Unit tests for `get_all_subtitle_streams` |
| Modify | `frontend/src/types/wanted.ts` | Add `embedded_languages` to `WantedItem` |
| Create | `frontend/src/pages/wanted/SubtitlePresencePills.tsx` | Pill display component |
| Create | `frontend/src/test/SubtitlePresencePills.test.tsx` | Component tests |
| Modify | `frontend/src/pages/wanted/WantedTableRow.tsx` | Use pills, add `sourceLanguage` prop |
| Modify | `frontend/src/pages/Wanted.tsx` | Fetch config, pass `sourceLanguage` |
| Modify | `frontend/src/i18n/locales/de/library.json` | Rename `existing_col` |
| Modify | `frontend/src/i18n/locales/en/library.json` | Rename `existing_col` |

---

## Task 1: Add `get_all_subtitle_streams()` to `ass_utils.py`

**Files:**
- Modify: `backend/ass_utils.py` (after line 71, after `has_target_language_stream`)
- Create: `backend/tests/test_embedded_streams.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_embedded_streams.py`:

```python
"""Tests for get_all_subtitle_streams in ass_utils."""
import pytest
from unittest.mock import patch


PROBE_EN_ASS_JA_SRT = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264"},
        {"codec_type": "audio", "codec_name": "aac", "tags": {"language": "jpn"}},
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
        {"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "jpn"}},
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "deu"}},
    ]
}

PROBE_EMPTY = {"streams": []}

PROBE_NO_SUBS = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264"},
        {"codec_type": "audio", "codec_name": "aac"},
    ]
}

PROBE_UNKNOWN_CODEC = {
    "streams": [
        {"codec_type": "subtitle", "codec_name": "dvd_subtitle", "tags": {"language": "eng"}},
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
    ]
}

PROBE_DUPLICATE = {
    "streams": [
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
    ]
}


@pytest.fixture(autouse=True)
def mock_lang_tags():
    """Mock _get_language_tags to avoid real config loading."""
    def fake_tags(lang):
        mapping = {
            "de": {"deu", "ger", "de"},
            "en": {"eng", "en"},
            "ja": {"jpn", "ja"},
        }
        return mapping.get(lang, {lang})

    with patch("ass_utils._get_language_tags", side_effect=fake_tags):
        yield


def test_returns_all_non_target_streams():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_EN_ASS_JA_SRT, exclude_language="de")
    langs = {r["lang"] for r in result}
    assert "eng" in langs
    assert "jpn" in langs
    # DE excluded
    assert "deu" not in langs


def test_excludes_target_language():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_EN_ASS_JA_SRT, exclude_language="en")
    langs = {r["lang"] for r in result}
    assert "eng" not in langs
    assert "deu" in langs


def test_formats_correctly():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_EN_ASS_JA_SRT, exclude_language="de")
    by_lang = {r["lang"]: r["format"] for r in result}
    assert by_lang["eng"] == "ass"
    assert by_lang["jpn"] == "srt"


def test_empty_probe_returns_empty():
    from ass_utils import get_all_subtitle_streams
    assert get_all_subtitle_streams(PROBE_EMPTY) == []


def test_no_subtitle_streams_returns_empty():
    from ass_utils import get_all_subtitle_streams
    assert get_all_subtitle_streams(PROBE_NO_SUBS) == []


def test_skips_unknown_codecs():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_UNKNOWN_CODEC)
    # dvd_subtitle is unknown, only ass counts
    assert len(result) == 1
    assert result[0]["format"] == "ass"


def test_deduplicates_same_lang_format():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_DUPLICATE)
    assert len(result) == 1


def test_no_exclude_returns_all():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_EN_ASS_JA_SRT, exclude_language=None)
    assert len(result) == 3  # eng, jpn, deu
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && python -m pytest tests/test_embedded_streams.py -v
```
Expected: `ImportError` or `AttributeError: module 'ass_utils' has no attribute 'get_all_subtitle_streams'`

- [ ] **Step 3: Add `get_all_subtitle_streams` to `backend/ass_utils.py`**

Insert after line 71 (after `has_target_language_stream` function ends):

```python
def get_all_subtitle_streams(ffprobe_data: dict, exclude_language: str | None = None) -> list[dict]:
    """Return all embedded subtitle streams as a list of {lang, format} dicts.

    Args:
        ffprobe_data: dict from get_media_streams / ffprobe JSON output.
        exclude_language: ISO-639-1 code to exclude (typically the target language,
            already tracked separately in existing_sub). None = return all.

    Returns:
        Deduplicated list of dicts with 'lang' (raw language tag) and 'format'
        ('ass' or 'srt'). Unknown codecs (dvd_subtitle, etc.) are skipped.
    """
    exclude_tags: set[str] = set()
    if exclude_language:
        from config import _get_language_tags
        exclude_tags = _get_language_tags(exclude_language)

    seen: set[tuple] = set()
    result: list[dict] = []

    for stream in ffprobe_data.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        lang = stream.get("tags", {}).get("language", "").lower()
        if not lang:
            continue
        if lang in exclude_tags:
            continue
        codec = stream.get("codec_name", "").lower()
        if codec in ("ass", "ssa"):
            fmt = "ass"
        elif codec in ("subrip", "srt"):
            fmt = "srt"
        else:
            continue
        key = (lang, fmt)
        if key not in seen:
            seen.add(key)
            result.append({"lang": lang, "format": fmt})

    return result
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend && python -m pytest tests/test_embedded_streams.py -v
```
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ass_utils.py backend/tests/test_embedded_streams.py
git commit -m "feat: add get_all_subtitle_streams to ass_utils"
```

---

## Task 2: DB Migration — add `embedded_languages` column

**Files:**
- Create: `backend/db/migrations/versions/e1f2a3b4c5d6_add_embedded_languages.py`
- Modify: `backend/db/models/core.py`

- [ ] **Step 1: Find current Alembic head**

```bash
cd backend && python -m alembic heads
```
Note the revision ID printed. Use it as `down_revision` in the migration below.

- [ ] **Step 2: Create migration file**

Create `backend/db/migrations/versions/e1f2a3b4c5d6_add_embedded_languages.py`:

```python
"""Add embedded_languages column to wanted_items.

Revision ID: e1f2a3b4c5d6
Revises: <REPLACE_WITH_HEAD_FROM_STEP_1>
Create Date: 2026-04-04

"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "<REPLACE_WITH_HEAD_FROM_STEP_1>"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.add_column(
            sa.Column("embedded_languages", sa.Text(), nullable=True, server_default="[]")
        )


def downgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.drop_column("embedded_languages")
```

- [ ] **Step 3: Add column to ORM model**

In `backend/db/models/core.py`, find the `WantedItem` class. After the `existing_sub` line (line 75), add:

```python
    embedded_languages: Mapped[str | None] = mapped_column(Text, default="[]")
```

- [ ] **Step 4: Run migration**

```bash
cd backend && python -m alembic upgrade head
```
Expected: `Running upgrade <old> -> e1f2a3b4c5d6, Add embedded_languages column to wanted_items`

- [ ] **Step 5: Verify migration**

```bash
cd backend && python -m alembic current
```
Expected: `e1f2a3b4c5d6 (head)`

- [ ] **Step 6: Commit**

```bash
git add backend/db/migrations/versions/e1f2a3b4c5d6_add_embedded_languages.py backend/db/models/core.py
git commit -m "feat: add embedded_languages column to wanted_items"
```

---

## Task 3: Repository + Public Wrapper — propagate `embedded_languages`

**Files:**
- Modify: `backend/db/repositories/wanted.py`
- Modify: `backend/db/wanted.py`

- [ ] **Step 1: Update `WantedRepository.upsert_wanted_item` signature**

In `backend/db/repositories/wanted.py`, find `upsert_wanted_item` (line 25). Add the new parameter after `subtitle_type`:

```python
    def upsert_wanted_item(
        self,
        item_type: str,
        file_path: str,
        title: str = "",
        season_episode: str = "",
        existing_sub: str = "",
        missing_languages: list = None,
        sonarr_series_id: int = None,
        sonarr_episode_id: int = None,
        radarr_movie_id: int = None,
        standalone_series_id: int = None,
        standalone_movie_id: int = None,
        upgrade_candidate: bool = False,
        current_score: int = 0,
        target_language: str = "",
        instance_name: str = "",
        subtitle_type: str = "full",
        embedded_languages: list = None,
    ) -> tuple:
```

Also add near line 54 (after `langs_json = json.dumps(...)`):

```python
        embedded_json = json.dumps(embedded_languages or [])
```

Then in the **ignored-status update block** (around line 80), add:

```python
                existing.embedded_languages = embedded_json
```

In the **normal update block** (around line 96), add:

```python
                existing.embedded_languages = embedded_json
```

In the **new item INSERT block** (around line 117), add to the `WantedItem(...)` constructor:

```python
            embedded_languages=embedded_json,
```

- [ ] **Step 2: Update `_row_to_wanted` to parse `embedded_languages` JSON**

In `backend/db/repositories/wanted.py`, find `_row_to_wanted` (line 488). After the `missing_languages` parsing block, add:

```python
        if d.get("embedded_languages"):
            try:
                d["embedded_languages"] = json.loads(d["embedded_languages"])
            except json.JSONDecodeError:
                d["embedded_languages"] = []
        else:
            d["embedded_languages"] = []
```

- [ ] **Step 3: Update public wrapper in `backend/db/wanted.py`**

Find `upsert_wanted_item` (line 32). Add `embedded_languages: list = None` parameter and pass it through:

```python
def upsert_wanted_item(
    item_type: str,
    file_path: str,
    title: str = "",
    season_episode: str = "",
    existing_sub: str = "",
    missing_languages: list = None,
    sonarr_series_id: int = None,
    sonarr_episode_id: int = None,
    radarr_movie_id: int = None,
    standalone_series_id: int = None,
    standalone_movie_id: int = None,
    upgrade_candidate: bool = False,
    current_score: int = 0,
    target_language: str = "",
    instance_name: str = "",
    subtitle_type: str = "full",
    embedded_languages: list = None,
) -> tuple:
    """Insert or update a wanted item. Returns (row_id, was_updated)."""
    return _get_repo().upsert_wanted_item(
        item_type,
        file_path,
        title,
        season_episode,
        existing_sub,
        missing_languages,
        sonarr_series_id,
        sonarr_episode_id,
        radarr_movie_id,
        standalone_series_id,
        standalone_movie_id,
        upgrade_candidate,
        current_score,
        target_language,
        instance_name,
        subtitle_type,
        embedded_languages,
    )
```

- [ ] **Step 4: Run backend tests**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/db/repositories/wanted.py backend/db/wanted.py
git commit -m "feat: propagate embedded_languages through repository and public wrapper"
```

---

## Task 4: Scanner — detect all embedded streams

**Files:**
- Modify: `backend/services/wanted_scanner_core.py`

There are **two call sites** in this file — one for movies (~line 341) and one for episodes (~line 619). Update both identically.

- [ ] **Step 1: Add import at top of scanner file**

Find the imports section in `backend/services/wanted_scanner_core.py`. Add (or verify it's not already there):

```python
from ass_utils import get_all_subtitle_streams
```

- [ ] **Step 2: Update movies call site**

Find the movie scanning block around line 355 where `embedded_sub` is set. After the block:

```python
            embedded_sub = None
            if probe_data:
                ...
                embedded_sub = has_target_language_stream(probe_data, target_lang)
                if embedded_sub == "ass":
                    existing = "embedded_ass"
                elif embedded_sub == "srt":
                    existing = "embedded_srt"
```

Immediately after that block (before `title = movie_title`), add:

```python
            embedded_langs = []
            if probe_data:
                embedded_langs = get_all_subtitle_streams(probe_data, exclude_language=target_lang)
```

Then find the `upsert_wanted_item` call for movies and add `embedded_languages=embedded_langs`:

```python
            item_id, was_updated = upsert_wanted_item(
                ...
                embedded_languages=embedded_langs,
            )
```

- [ ] **Step 3: Update episodes call site**

Find the episode scanning block around line 619 where `embedded_sub` is set. Apply the exact same change:

After the `embedded_sub` detection block:
```python
                embedded_langs = []
                if probe_data:
                    embedded_langs = get_all_subtitle_streams(probe_data, exclude_language=target_lang)
```

And add `embedded_languages=embedded_langs` to the `upsert_wanted_item` call for episodes.

- [ ] **Step 4: Run backend tests**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/wanted_scanner_core.py
git commit -m "feat: detect all embedded subtitle streams in wanted scanner"
```

---

## Task 5: Frontend types + i18n

**Files:**
- Modify: `frontend/src/types/wanted.ts`
- Modify: `frontend/src/i18n/locales/de/library.json`
- Modify: `frontend/src/i18n/locales/en/library.json`

- [ ] **Step 1: Add `embedded_languages` to `WantedItem`**

In `frontend/src/types/wanted.ts`, find the `WantedItem` interface (line 3). After `existing_sub: string`, add:

```ts
  embedded_languages: Array<{ lang: string; format: string }>
```

- [ ] **Step 2: Rename column header in DE i18n**

In `frontend/src/i18n/locales/de/library.json`, find line:
```json
"existing_col": "Vorhanden",
```
Replace with:
```json
"existing_col": "Untertitel",
```

- [ ] **Step 3: Rename column header in EN i18n**

In `frontend/src/i18n/locales/en/library.json`, find line:
```json
"existing_col": "Existing",
```
Replace with:
```json
"existing_col": "Subtitles",
```

- [ ] **Step 4: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/wanted.ts frontend/src/i18n/locales/de/library.json frontend/src/i18n/locales/en/library.json
git commit -m "feat: add embedded_languages type field, rename wanted column header"
```

---

## Task 6: `SubtitlePresencePills` component

**Files:**
- Create: `frontend/src/pages/wanted/SubtitlePresencePills.tsx`
- Create: `frontend/src/test/SubtitlePresencePills.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/test/SubtitlePresencePills.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SubtitlePresencePills } from '@/pages/wanted/SubtitlePresencePills'

const noEmbedded: Array<{ lang: string; format: string }> = []
const enAss = [{ lang: 'eng', format: 'ass' }]
const enAssJaSrt = [{ lang: 'eng', format: 'ass' }, { lang: 'jpn', format: 'srt' }]
const threeLangs = [
  { lang: 'eng', format: 'ass' },
  { lang: 'jpn', format: 'srt' },
  { lang: 'fra', format: 'srt' },
]

describe('SubtitlePresencePills', () => {
  it('shows DE ✗ when existingSub is empty', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
      />
    )
    expect(screen.getByText('DE ✗')).toBeTruthy()
  })

  it('shows Kein Sub when nothing embedded', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
      />
    )
    expect(screen.getByText('Kein Sub')).toBeTruthy()
  })

  it('shows DE SRT ↑ for srt existing_sub', () => {
    render(
      <SubtitlePresencePills
        existingSub="srt"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={enAss}
      />
    )
    expect(screen.getByText('DE SRT ↑')).toBeTruthy()
  })

  it('shows DE ↓ ASS for embedded_ass', () => {
    render(
      <SubtitlePresencePills
        existingSub="embedded_ass"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={enAss}
      />
    )
    expect(screen.getByText('DE ↓ ASS')).toBeTruthy()
  })

  it('shows embedded lang pill', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={enAss}
      />
    )
    expect(screen.getByText('ENG ↓ ASS')).toBeTruthy()
  })

  it('shows +N button when more than 2 embedded', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={threeLangs}
      />
    )
    expect(screen.getByText('+1 ▾')).toBeTruthy()
  })

  it('expands overflow on click', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={threeLangs}
      />
    )
    const btn = screen.getByText('+1 ▾')
    fireEvent.click(btn)
    expect(screen.getByText('FRA ↓ SRT')).toBeTruthy()
  })

  it('sorts sourceLanguage first in right group', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={[{ lang: 'jpn', format: 'srt' }, { lang: 'eng', format: 'ass' }]}
      />
    )
    const pills = document.querySelectorAll('[data-testid="embedded-pill"]')
    expect(pills[0].textContent).toBe('ENG ↓ ASS')
    expect(pills[1].textContent).toBe('JPN ↓ SRT')
  })
})
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/test/SubtitlePresencePills.test.tsx
```
Expected: FAIL — component not found.

- [ ] **Step 3: Create `SubtitlePresencePills.tsx`**

Create `frontend/src/pages/wanted/SubtitlePresencePills.tsx`:

```tsx
import { useState } from 'react'

interface EmbeddedLang {
  lang: string
  format: string
}

interface SubtitlePresencePillsProps {
  existingSub: string
  targetLanguage: string
  sourceLanguage: string
  embeddedLanguages: EmbeddedLang[]
}

const PILL_BASE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 6px',
  borderRadius: 4,
  fontSize: 10,
  fontWeight: 700,
  fontFamily: 'var(--font-mono)',
  whiteSpace: 'nowrap',
  border: '1px solid',
}

const PILL_MISS: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(239,68,68,0.1)',
  color: '#ef4444',
  borderColor: 'rgba(239,68,68,0.2)',
}

const PILL_SRT: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(234,179,8,0.12)',
  color: '#eab308',
  borderColor: 'rgba(234,179,8,0.25)',
}

const PILL_EMB: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(16,185,129,0.12)',
  color: '#10b981',
  borderColor: 'rgba(16,185,129,0.25)',
}

const PILL_OTHER: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(29,184,212,0.12)',
  color: '#1db8d4',
  borderColor: 'rgba(29,184,212,0.25)',
}

const PILL_NONE: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(255,255,255,0.04)',
  color: 'var(--text-muted)',
  borderColor: 'rgba(255,255,255,0.07)',
  fontStyle: 'italic',
}

const INLINE_LIMIT = 2

export function SubtitlePresencePills({
  existingSub,
  targetLanguage,
  sourceLanguage,
  embeddedLanguages,
}: SubtitlePresencePillsProps) {
  const [expanded, setExpanded] = useState(false)
  const lang = targetLanguage.toUpperCase()

  // Left pill — target language status
  let leftPill: React.ReactNode
  if (existingSub === 'embedded_ass') {
    leftPill = <span style={PILL_EMB}>{lang} ↓ ASS</span>
  } else if (existingSub === 'embedded_srt') {
    leftPill = <span style={PILL_EMB}>{lang} ↓ SRT</span>
  } else if (existingSub === 'ass') {
    leftPill = <span style={PILL_EMB}>{lang} ASS</span>
  } else if (existingSub === 'srt') {
    leftPill = <span style={PILL_SRT}>{lang} SRT ↑</span>
  } else {
    leftPill = <span style={PILL_MISS}>{lang} ✗</span>
  }

  // Right group — sort sourceLanguage first, then alphabetically
  const sorted = [...embeddedLanguages].sort((a, b) => {
    const aIsSource = a.lang === sourceLanguage || a.lang.startsWith(sourceLanguage)
    const bIsSource = b.lang === sourceLanguage || b.lang.startsWith(sourceLanguage)
    if (aIsSource && !bIsSource) return -1
    if (!aIsSource && bIsSource) return 1
    return a.lang.localeCompare(b.lang)
  })

  const inline = sorted.slice(0, INLINE_LIMIT)
  const overflow = sorted.slice(INLINE_LIMIT)

  const rightContent =
    embeddedLanguages.length === 0 ? (
      <span style={PILL_NONE}>Kein Sub</span>
    ) : (
      inline.map((e, i) => (
        <span key={i} data-testid="embedded-pill" style={PILL_OTHER}>
          {e.lang.toUpperCase()} ↓ {e.format.toUpperCase()}
        </span>
      ))
    )

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
      {leftPill}
      <span
        style={{ width: 1, height: 14, background: 'var(--border)', margin: '0 2px', flexShrink: 0 }}
      />
      {rightContent}
      {overflow.length > 0 && (
        <>
          <button
            onClick={() => setExpanded((e) => !e)}
            style={{
              ...PILL_BASE,
              background: 'rgba(255,255,255,0.06)',
              color: 'var(--text-muted)',
              borderColor: 'rgba(255,255,255,0.1)',
              cursor: 'pointer',
            }}
          >
            +{overflow.length} {expanded ? '▲' : '▾'}
          </button>
          {expanded && (
            <div
              style={{
                width: '100%',
                display: 'flex',
                gap: 4,
                flexWrap: 'wrap',
                marginTop: 4,
                padding: '6px 8px',
                background: 'var(--bg-surface)',
                borderRadius: 4,
                border: '1px solid var(--border)',
              }}
            >
              {overflow.map((e, i) => (
                <span key={i} data-testid="embedded-pill" style={PILL_OTHER}>
                  {e.lang.toUpperCase()} ↓ {e.format.toUpperCase()}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/test/SubtitlePresencePills.test.tsx
```
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/wanted/SubtitlePresencePills.tsx frontend/src/test/SubtitlePresencePills.test.tsx
git commit -m "feat: add SubtitlePresencePills component"
```

---

## Task 7: Wire `SubtitlePresencePills` into `WantedTableRow`

**Files:**
- Modify: `frontend/src/pages/wanted/WantedTableRow.tsx`

- [ ] **Step 1: Add `sourceLanguage` prop to `WantedTableRowProps`**

In `frontend/src/pages/wanted/WantedTableRow.tsx`, find the `WantedTableRowProps` interface (line 160). Add:

```ts
  sourceLanguage: string
```

Also add `sourceLanguage` to the destructured props in the `WantedTableRow` function signature.

- [ ] **Step 2: Add import for `SubtitlePresencePills`**

At the top of `WantedTableRow.tsx`, add:

```ts
import { SubtitlePresencePills } from '@/pages/wanted/SubtitlePresencePills'
```

- [ ] **Step 3: Replace existing_sub cell with `SubtitlePresencePills`**

Find the cell that currently renders the existing_sub text (around line 296-319):

```tsx
<td className="px-3 py-2.5 hidden sm:table-cell">
  <div className="flex items-center gap-1.5">
    <span
      className="text-xs uppercase"
      style={{
        fontFamily: 'var(--font-mono)',
        color: item.existing_sub === 'srt' ? 'var(--warning)' : 'var(--text-muted)',
      }}
    >
      {item.existing_sub || 'none'}
    </span>
    {item.upgrade_candidate === 1 && (
      <span
        className="text-[9px] px-1 py-0.5 rounded font-bold uppercase"
        style={{
          backgroundColor: 'rgba(16,185,129,0.1)',
          color: 'var(--success)',
        }}
      >
        SRT&rarr;ASS
      </span>
    )}
  </div>
</td>
```

Replace the entire `<td>` with:

```tsx
<td className="px-3 py-2.5 hidden sm:table-cell">
  <SubtitlePresencePills
    existingSub={item.existing_sub}
    targetLanguage={item.target_language}
    sourceLanguage={sourceLanguage}
    embeddedLanguages={item.embedded_languages ?? []}
  />
</td>
```

- [ ] **Step 4: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors (TypeScript will flag missing `sourceLanguage` prop in `Wanted.tsx` — fix in Task 8).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/wanted/WantedTableRow.tsx
git commit -m "feat: replace existing_sub text with SubtitlePresencePills in WantedTableRow"
```

---

## Task 8: Pass `sourceLanguage` from `Wanted.tsx`

**Files:**
- Modify: `frontend/src/pages/Wanted.tsx`

- [ ] **Step 1: Add config query to `Wanted.tsx`**

In `frontend/src/pages/Wanted.tsx`, find the imports section. Add:

```ts
import { useQuery } from '@tanstack/react-query'
import { getConfig } from '@/api/settings'
```

(`useQuery` is likely already imported — check first and skip if so.)

- [ ] **Step 2: Add the query inside the component**

In the `Wanted` component function body, add the config query near the top with other queries:

```ts
const { data: config } = useQuery({ queryKey: ['config'], queryFn: getConfig })
const sourceLanguage = config?.source_language ?? 'en'
```

- [ ] **Step 3: Pass `sourceLanguage` to every `WantedTableRow`**

Find all `<WantedTableRow` usages in `Wanted.tsx` and add the prop:

```tsx
<WantedTableRow
  ...
  sourceLanguage={sourceLanguage}
/>
```

- [ ] **Step 4: Run full frontend checks**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run test -- --run
```
Expected: no errors, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Wanted.tsx
git commit -m "feat: fetch source_language from config and pass to SubtitlePresencePills"
```

---

## Task 9: Manual smoke test

- [ ] **Step 1: Start dev server**

```bash
npm run dev
```

- [ ] **Step 2: Open Wanted page**

Navigate to `http://localhost:5173/wanted`.

Check:
- Column header now reads "Untertitel" (DE) or "Subtitles" (EN)
- Items with no embedded subs show `DE ✗ | Kein Sub`
- Items with EN ASS embedded show `DE ✗ | ENG ↓ ASS`
- Items with DE SRT sidecar show `DE SRT ↑ | ...`
- Items with 3+ embedded langs show `+N ▾` button that expands on click

- [ ] **Step 3: Trigger a wanted scan** (or use "Eingebettet scannen") to populate `embedded_languages` for existing items.

- [ ] **Step 4: Final pre-PR checks**

```bash
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sdk.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```
Expected: all green.
