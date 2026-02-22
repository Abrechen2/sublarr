# Phase 26-01: Whisper Fallback Threshold -- Implementation Summary

## Overview

Implemented a configurable minimum score threshold for subtitle provider results.
When all provider results fall below this threshold, Sublarr automatically uses
Whisper transcription as a fallback instead of accepting a low-quality source sub.

## Changes Made

### Backend

#### `backend/translator.py`
- Added `_get_whisper_fallback_min_score() -> int` helper that reads
  `whisper_fallback_min_score` from config_entries (0-100, 0 = disabled).
- Updated `_search_providers_for_source_sub()` to return a 3-tuple
  `(path, format, score)` instead of `(path, format)`, so the caller can
  compare the result score against the configured threshold.
- Updated `translate_file()` Case C3/C4/D block:
  - Reads `_min_score` from the helper.
  - If provider result score < threshold (and threshold > 0), marks the result
    as "below threshold" and discards the source subtitle path.
  - Falls through to Case D (Whisper) with an informational log message.
  - Case D logs distinguish between "no source found" and "score below threshold".

#### `backend/whisper/queue.py`
- After successful Whisper transcription, calls `record_subtitle_download()` with
  `source="whisper"` and `score=0` to record the generated subtitle in the
  download history. This enables the upgrade logic: whisper-generated subtitles
  can be replaced by better provider results in subsequent scans.

#### `backend/routes/whisper.py`
- `GET /api/v1/whisper/config`: Added `whisper_fallback_min_score` to the response.
- `PUT /api/v1/whisper/config`: Added `whisper_fallback_min_score` to `allowed_keys`
  so it can be saved via the config endpoint.

#### `backend/db/models/providers.py`
- Added `source: Mapped[Optional[str]]` column to `SubtitleDownload` model
  with default `"provider"`. Values: `"provider"` | `"whisper"`.

#### `backend/db/repositories/providers.py`
- Updated `record_subtitle_download()` to accept optional `source: str = "provider"`.
- Stores the source value in the new column.

#### `backend/db/providers.py`
- Updated `record_subtitle_download()` facade to pass through the `source` param.

#### `backend/db/migrations/versions/f7a8b9c0d1e2_add_source_to_subtitle_downloads.py`
- Alembic migration that adds the `source` TEXT column to `subtitle_downloads`
  with `server_default="provider"` and `render_as_batch=True` for SQLite.

### Frontend

#### `frontend/src/lib/types.ts`
- Added `whisper_fallback_min_score: number` to the `WhisperConfig` interface.

#### `frontend/src/pages/Settings/WhisperTab.tsx`
- Added `whisper_fallback_min_score: 0` to the initial `localConfig` state.
- Syncs `whisper_fallback_min_score` from the server config in the `useEffect`.
- Added a "Fallback Min Score" number input (0-100) in the Whisper Configuration
  section with help text: "When all provider results score below this threshold,
  use Whisper instead. 0 = only when no results at all."

## Behaviour

| Condition | Result |
|-----------|--------|
| `whisper_fallback_min_score = 0` | No change to existing behaviour |
| `min_score > 0`, provider score >= threshold | Use provider source normally (Case C3) |
| `min_score > 0`, provider score < threshold | Skip provider result, fall through to Whisper (Case D) |
| `min_score > 0`, no provider results at all | Fall through to Whisper (existing Case C4/D) |
| Whisper disabled | Log warning, return fail result (existing behaviour) |

## Config Key

The feature is controlled by the config key `whisper_fallback_min_score` stored
in the `config_entries` database table. Default value: `0` (disabled).

## Notes

- Score range depends on the provider scoring system (typically 0-400+ for
  OpenSubtitles-style providers). The threshold is compared directly against
  the integer score returned by `search_and_download_best()`.
- Whisper-generated subtitles are recorded with `source="whisper"` and `score=0`,
  distinguishing them from provider downloads in history queries.
- The `SubtitleDownload.source` column has `server_default="provider"` so
  existing rows are not affected by the migration.
