# Design: Subtitle Export & Batch Download (v0.21.0, Features 1+2)

**Date:** 2026-03-11
**Status:** Approved
**Scope:** Single-file subtitle download + series-level ZIP export

---

## Problem

Sublarr writes processed `.ass`/`.srt` sidecars to disk. Currently there is no HTTP way to retrieve those files — users must mount the network share. This blocks browser-based download and script/automation access.

---

## Out of Scope

- Signed/expiring download URLs
- Streaming player subtitle source (Jellyfin handles this natively)
- Per-language filtering on single-file download

---

## Architecture

Two new endpoints added to `backend/routes/subtitles.py`:

```
GET /api/v1/subtitles/download?path=<encoded_path>
GET /api/v1/series/{series_id}/subtitles/export[?lang=<lang>]
```

Both reuse existing infrastructure:
- `is_safe_path()` from `security_utils.py` (path traversal protection)
- Optional API-Key auth from `auth.py` (consistent with all other endpoints)
- `_scan_subtitle_files()` from `export_manager.py` (series subtitle discovery)

---

## Endpoint 1: Single File Download

```
GET /api/v1/subtitles/download?path=<url-encoded-absolute-path>
```

**Logic:**
1. Decode `path` parameter
2. `is_safe_path(settings.media_path, path)` → 403 if outside media root
3. Extension whitelist check: `.ass`, `.srt`, `.vtt`, `.ssa`, `.sub` → 403 otherwise
4. File exists check → 404 if missing
5. `send_file(path, as_attachment=True)`

**Response:** Raw file with `Content-Disposition: attachment; filename=<filename>`

---

## Endpoint 2: Series ZIP Export

```
GET /api/v1/series/{series_id}/subtitles/export[?lang=de]
```

**Logic:**
1. Look up series media path via Sonarr integration (existing pattern)
2. `_scan_subtitle_files(series_path)` → list of `.ass`/`.srt` sidecar paths
3. Optional `lang` filter (e.g. `?lang=de` keeps only `*.de.*` files)
4. Build ZIP in memory (BytesIO), enforce 50 MB cap
5. Return as `application/zip` with `Content-Disposition: attachment; filename=<series-title>.zip`

**ZIP structure:**
```
<series-title>/
  Season 01/
    Episode.S01E01.de.ass
    Episode.S01E02.de.srt
  Season 02/
    ...
```

---

## Security

| Threat | Mitigation |
|--------|------------|
| Path traversal | `is_safe_path()` — 403 if outside `media_path` |
| Arbitrary file read | Extension whitelist (`.ass/.srt/.vtt/.ssa/.sub` only) |
| Filesystem info leak | Generic 403/404, no path in error body |
| ZIP bomb (export) | 50 MB total cap (reuse `archive_utils.py` constant) |
| Unauthenticated access | Inherits global API-Key auth (`auth.py` decorator) |

---

## Frontend Changes

**SeriesDetail page (`SeriesDetail.tsx`):**
- Download icon button next to each sidecar badge in the episode row
  - Calls `GET /api/v1/subtitles/download?path=<encoded>` → browser triggers download
- "Export ZIP" button in series header
  - Calls `GET /api/v1/series/{id}/subtitles/export` → browser triggers ZIP download

**API client (`api/client.ts`):**
- `downloadSubtitle(path: string): string` — returns URL for `<a href>` trigger
- `exportSeriesSubtitles(seriesId: number, lang?: string): string` — returns URL

No new TanStack Query hooks needed (direct URL navigation, not JSON fetch).

---

## Files to Create / Modify

| File | Change |
|------|--------|
| `backend/routes/subtitles.py` | Add 2 new route functions |
| `frontend/src/api/client.ts` | Add 2 URL helper functions |
| `frontend/src/pages/SeriesDetail.tsx` | Download button + Export ZIP button |
| `backend/tests/test_subtitle_export.py` | New test file |

---

## Test Plan

- `test_download_subtitle_valid` — serves file within media_path
- `test_download_subtitle_path_traversal` — 403 on `../../etc/passwd`
- `test_download_subtitle_bad_extension` — 403 on `.py` file
- `test_download_subtitle_missing` — 404
- `test_export_series_zip` — returns valid ZIP with correct structure
- `test_export_series_zip_lang_filter` — only `*.de.*` files included
- `test_export_series_zip_size_limit` — 413 when over 50 MB
