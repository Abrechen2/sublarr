# Feature Parity Roadmap — Milestone 0.11.0

**Date:** 2026-02-22
**Scope:** Complete feature parity with Bazarr, TinyMM, and SubtitleEdit
**Priority basis:** Daily usage gaps — Video Sync and Track Display are top pain points

---

## Context

Sublarr already has:
- `get_media_streams()` / `mediainfo_utils.py` — reads all tracks via ffprobe/MediaInfo
- Embedded-sub detection (target language check → `embedded_srt/ass`)
- OCR via Tesseract (PGS/VobSub, single-frame)
- Timing tools: offset shift, speed/framerate, common-fixes, advanced-sync (pysubs2)
- Translation pipeline with LLM, quality scoring, translation memory

Missing vs. Bazarr / TinyMM / SubtitleEdit:
- Full track manifest display + extraction
- Automatic subtitle sync to video audio (Video Angleich)
- Waveform-based manual timing editor
- Batch format conversion (PGS/VobSub → SRT/ASS)
- Improved batch OCR pipeline
- Overlap fix, timing normalization, spell-check, merge/split

---

## Phase 29 — Track Manifest

### Goal
Every episode in SeriesDetail shows all embedded subtitle tracks regardless of target language.
Users see what's in the file and can extract or use tracks as translation sources.

### Backend

```
GET  /api/v1/library/series/<id>/episodes/<ep_id>/tracks
POST /api/v1/library/series/<id>/episodes/<ep_id>/tracks/<index>/extract
POST /api/v1/library/series/<id>/episodes/<ep_id>/tracks/<index>/use-as-source
```

`GET /tracks` calls the already-implemented `get_media_streams()` and returns all subtitle
streams in a normalized format:

```json
[
  {"index": 2, "codec": "ass",               "language": "jpn", "title": "Japanese",   "forced": false},
  {"index": 3, "codec": "subrip",            "language": "eng", "title": "English",    "forced": false},
  {"index": 4, "codec": "subrip",            "language": "eng", "title": "Signs/Songs","forced": true},
  {"index": 5, "codec": "hdmv_pgs_subtitle", "language": "deu", "title": "",           "forced": false}
]
```

`POST /extract` calls the already-implemented `extract_subtitle_stream()` from `ass_utils.py`
and saves the result as a sidecar file next to the video (e.g. `episode.de.ass`).

`POST /use-as-source` extracts and immediately opens the track in SubtitleEditorModal or
sets it as the translation source for the LLM pipeline.

### Frontend

In SeriesDetail episode rows: a track-count icon (e.g. "3 tracks") expands an inline panel
showing the track list. Per track: language badge, format chip (ASS / SRT / PGS / VobSub),
Forced tag if applicable, two action buttons: "Extrahieren" and "Als Quelle nutzen".

### Dependencies
None — `get_media_streams()` and `extract_subtitle_stream()` already exist.

---

## Phase 30 — Video Sync Backend

### Goal
Automatically align subtitle timing against the video's audio track.
Two engines: `ffsubsync` (speech-based, no reference needed) and `alass`
(reference-subtitle-based, faster and more precise when a reference track is available).

### Engines

| Engine | Method | Best for |
|--------|--------|----------|
| ffsubsync | Speech detection via VAD | Dubbed anime, no reference sub |
| alass | Align against reference subtitle | When EN/JP track exists in MKV |

Both added as optional dependencies in `requirements.txt` and `Dockerfile`.
Backend degrades gracefully if not installed (returns 503 with explanation).

### Backend

```
POST /api/v1/tools/video-sync
  body: {
    file_path: str,          # subtitle file to sync
    video_path: str,         # source video
    engine: "ffsubsync" | "alass",
    reference_track_index?: int  # alass only — stream index from Phase 29
  }
  → { job_id: str }

GET /api/v1/tools/video-sync/<job_id>
  → { status, shift_ms?, score?, output_path?, error? }
```

- Runs in `ThreadPoolExecutor` (same pattern as translation jobs)
- Creates `.bak` backup of original subtitle before modifying
- Output: in-place sync with backup, or new `.synced.de.ass` sidecar (configurable)
- Job status emitted via existing Socket.IO channel

---

## Phase 31 — Video Sync Frontend + Auto-Sync

### Frontend

In SeriesDetail episode row, next to the subtitle badge: a "Sync" button.
Opens a modal with:
- Engine selector (ffsubsync / alass)
- Reference track dropdown — populated from Phase 29 track manifest (alass only)
- "Starten" button → shows progress via Socket.IO job events
- Result: shift applied in ms, quality score if available

### Auto-Sync after Download

New settings:
```
auto_sync_after_download: bool   (default: false)
auto_sync_engine: "ffsubsync" | "alass"
```

In `wanted_search.py`: after a successful subtitle download, enqueue a sync job
using the same `ThreadPoolExecutor`. Only runs when `auto_sync_after_download` is enabled.

New Settings tab entry under Translation → Sync.

### Dependencies
Phase 29 (track manifest) required for reference-track dropdown in alass mode.

---

## Phase 32 — Waveform Editor

### Goal
Manual timing adjustment directly in the browser. Audio waveform with subtitle cues
displayed as draggable blocks — like SubtitleEdit's waveform panel, but web-based.

### Backend

```
POST /api/v1/tools/waveform-extract
  body: { video_path: str }
  → { audio_url: str, duration_s: float }
```

- `ffmpeg` extracts audio → Opus (small, fast, browser-native)
- Cached by `(file_path, mtime)` — reuses existing content-hash cache pattern
- Served as a static temp file via Flask

### Frontend

New tab "Waveform" in `SubtitleEditorModal` (alongside existing text editor tab).

- `wavesurfer.js` renders the waveform
- `wavesurfer.js` Regions plugin shows each subtitle cue as a colored region
- Regions are draggable (shift timing) and resizable (adjust in/out points)
- Changes flow back into the existing editor state (same immutable pattern)
- "Speichern" uses existing `POST /tools/save-content`

### Scope
Timing adjustment only — text editing stays in the text editor tab.
No video preview in browser (bandwidth + complexity not justified).

---

## Phase 33 — Format Conversion

### Goal
Convert subtitle formats singly or in batch. Text formats via pysubs2 (already available);
image formats (PGS, VobSub) via the OCR pipeline from Phase 34.

### Backend

```
POST /api/v1/tools/convert
  body: {
    file_path?: str,             # single file
    track_index?: int,           # convert directly from embedded track (Phase 29)
    target_format: "srt" | "ass" | "ssa" | "vtt",
    video_path?: str             # required when track_index is set
  }
  → { output_path: str }
```

Supported conversions:
- ASS ↔ SRT ↔ SSA ↔ WebVTT — via pysubs2
- VobSub → SRT/ASS — OCR pipeline
- PGS → SRT/ASS — OCR pipeline (Phase 34)

### Frontend

- "Konvertieren" button in Phase 29 track panel (per track)
- Batch action in Library and SeriesDetail: select multiple episodes → convert all subs
- Format dropdown in both contexts

---

## Phase 34 — OCR Pipeline (Improved)

### Goal
Batch-OCR an entire PGS or VobSub track directly from an MKV.
Current implementation is frame-by-frame and not batched.

### Changes

- `ffmpeg` extracts the full subtitle stream as image sequence in one pass
- Tesseract runs over all images in batch (parallel workers)
- Language selection exposed: `jpn`, `deu`, `eng` (all already in Dockerfile)
- Post-processing: fix line breaks, normalize quotation marks and special characters
- Output: save as `.srt` sidecar or load directly into SubtitleEditorModal

### Backend

```
POST /api/v1/ocr/batch-extract
  body: { video_path, stream_index, language: "jpn"|"deu"|"eng", output?: "file"|"editor" }
  → { job_id }  # background job, status via Socket.IO
```

---

## Phase 35 — Quality Fixes

### Goal
Extend existing `/tools/` endpoints with fixes that SubtitleEdit applies automatically.
All available as individual endpoint actions and as a batch mode in SeriesDetail.

### New Tools

| Tool | What it does | Engine |
|------|-------------|--------|
| Overlap Fix | Trim end time of cue N if it overlaps cue N+1 | pysubs2 |
| Timing Normalization | Extend cues < 500ms; split cues > 10s | pysubs2 |
| Spell Check | Highlight and optionally fix spelling errors | pyhunspell (hunspell already in Dockerfile) |
| Merge Lines | Merge consecutive cues with gap < 200ms | pysubs2 |
| Split Lines | Split overly long cues at natural sentence boundaries | pysubs2 |

All configurable thresholds (500ms min, 10s max, 200ms merge gap) exposed as settings
with sensible defaults.

### Backend

New endpoints under `/api/v1/tools/`:
```
POST /overlap-fix
POST /timing-normalize   body: { min_ms?, max_ms? }
POST /spell-check        body: { language, fix: bool }
POST /merge-lines        body: { gap_ms? }
POST /split-lines        body: { max_chars? }
```

All follow existing pattern: `file_path` in body, `.bak` backup, returns modified count.

### Frontend

Buttons in SubtitleEditorModal toolbar (individual) + batch action panel in SeriesDetail.

---

## Dependency Graph

```
Phase 29 (Track Manifest)
  └─► Phase 31 (Sync Modal — reference track dropdown)
  └─► Phase 33 (Convert button in track panel)
  └─► Phase 34 (OCR — select stream from track list)

Phase 30 (Sync Backend)
  └─► Phase 31 (Sync Frontend — requires job API)

Phase 32, 33, 34, 35 — independent of each other
```

Recommended implementation order: 29 → 30 → 31 → 32 → 33 → 34 → 35

---

## New Dependencies

| Package | Phase | Notes |
|---------|-------|-------|
| `ffsubsync` | 30 | Optional — graceful degradation if missing |
| `alass` | 30 | Optional — graceful degradation if missing |
| `wavesurfer.js` | 32 | Frontend npm package |
| `pyhunspell` | 35 | Hunspell bindings — hunspell already in Dockerfile |

No breaking changes to existing API. All new endpoints are additive.
