# Wanted Page — Subtitle Presence Pills

**Date:** 2026-04-04  
**Status:** Approved  

## Problem

The "Vorhanden" column in the Wanted page only shows the target-language subtitle status (`none`, `srt`, `ass`, `embedded_ass`, `embedded_srt`) as plain text. This is misleading because:

1. "NONE" implies no subtitle exists at all — but the video file may have embedded subtitles in other languages (e.g. EN ASS in an anime MKV).
2. Users with multiple target languages (e.g. DE + EN) cannot tell from the column which target language a given row refers to.
3. The column name "Vorhanden" (Available) sounds like a general subtitle presence check, not a target-language-specific one.

## Solution

Replace the text display with a **pill-based component** that communicates both the target-language status and available embedded languages in a compact, scannable format.

## Visual Design

The column is renamed to **"Untertitel"** and displays two pill groups separated by a thin vertical divider:

```
[ DE ✗ ] | [ EN ↓ ASS ]  [ +2 ▾ ]
 └─ left ┘   └──────── right ────────┘
```

### Left group — Target language status (always 1 pill)

| Pill | Condition | Color |
|------|-----------|-------|
| `DE ✗` | No target-language sub exists | Red |
| `DE SRT ↑` | SRT sidecar exists, ASS upgrade possible | Yellow |
| `DE ↓ ASS` | Target language embedded, extractable | Green |

The language code matches the row's `target_language` field.

### Right group — Embedded languages

| Pill | Condition | Color |
|------|-----------|-------|
| `EN ↓ ASS` | Another language embedded in the video file | Cyan |
| `Kein Sub` | Nothing embedded at all | Muted grey |
| `+N ▾` | More than 2 additional embedded languages — opens inline dropdown | Muted grey |

The right group shows embedded streams sorted by: configured second-priority language first (e.g. EN), then others alphabetically. Up to 2 pills are shown inline; additional ones collapse into a `+N ▾` dropdown that expands below the cell on click.

### Examples

| Scenario | Pills |
|----------|-------|
| DE missing, EN embedded | `DE ✗` \| `EN ↓ ASS` |
| DE missing, nothing embedded | `DE ✗` \| `Kein Sub` |
| DE SRT sidecar, EN+JA+FR embedded | `DE SRT ↑` \| `EN ↓ ASS` `+2 ▾` |
| DE ASS embedded (extractable), EN embedded | `DE ↓ ASS` \| `EN ↓ ASS` |
| Multiple targets: DE row, JA embedded | `DE ✗` \| `JA ↓ ASS` |
| Multiple targets: EN row, JA embedded | `EN ✗` \| `JA ↓ ASS` |

## Architecture

### Backend

**New field: `embedded_languages`**

Added to the `wanted_items` DB table and returned by the Wanted API:

```python
embedded_languages: list[dict]  # e.g. [{"lang": "en", "format": "ass"}, {"lang": "ja", "format": "srt"}]
```

Stored as JSON in a new `embedded_languages` TEXT column (default `"[]"`).

**Scanner changes (`wanted_scanner_core.py`)**

Currently `has_target_language_stream()` is called to check only the target language stream. New behaviour:
- After `get_media_streams()`, call a new helper `get_all_subtitle_streams(probe_data)` that returns all subtitle streams as `list[{lang, format}]`.
- Exclude the target language from this list (it is already represented in `existing_sub`).
- Store the result in `embedded_languages` when inserting or updating a wanted item.

**Migration**

New Alembic migration: add `embedded_languages TEXT NOT NULL DEFAULT '[]'` to `wanted_items`.

**API**

The existing Wanted list endpoint already serialises all `wanted_items` fields. Adding `embedded_languages` to the serialisation is sufficient — no route changes needed.

### Frontend

**New component: `SubtitlePresencePills`**

Located in `frontend/src/pages/wanted/SubtitlePresencePills.tsx`.

Props:
```ts
interface SubtitlePresencePillsProps {
  existingSub: string          // current field: '', 'srt', 'ass', 'embedded_srt', 'embedded_ass'
  targetLanguage: string       // e.g. 'de'
  embeddedLanguages: Array<{ lang: string; format: string }>
}
```

Logic:
- Left pill derived from `existingSub` + `targetLanguage`.
- Right pills derived from `embeddedLanguages`, sorted with EN first (hardcoded priority — no second-priority concept exists in Sublarr currently), others alphabetically.
- First 2 right pills shown inline; remainder behind `+N ▾` toggle.
- Toggle state is local (`useState`) — no global state needed.

**`WantedTableRow.tsx` changes**

- Replace the `existing_sub` text span + `upgrade_candidate` badge with `<SubtitlePresencePills />`.
- Pass the new `embedded_languages` field from `WantedItem`.
- `WantedItem` interface gains `embedded_languages: Array<{ lang: string; format: string }>`.

**i18n**

- `de/library.json`: rename `existing_col` value from `"Vorhanden"` to `"Untertitel"`.
- `en/library.json`: same key → `"Subtitles"`.

## Out of scope

- Showing embedded language info anywhere other than the Wanted page.
- Changing how `existing_sub` itself is derived — it remains the target-language-only status field.
- Sorting or filtering the Wanted list by embedded language.
- Persisting which embedded languages the user has expanded in the dropdown.
