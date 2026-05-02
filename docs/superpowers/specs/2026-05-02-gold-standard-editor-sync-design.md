# Spec — Gold Standard: Waveform Editor & Smart Sync

**Status:** Proposed
**Date:** 2026-05-02
**Baseline:** 0.82.4-beta
**Successor of:** Plan B (B1–B7, shipped 0.64.0 → 0.70.0-beta)

---

## Premise

Sublarr ships two features today that work, but ride on the *architecture
tier* and not the *interaction tier*:

1. **Waveform Editor** is a read-only WaveSurfer view inside the
   `SubtitleEditorModal` — cues are overlaid as locked regions, the user
   can play/pause but cannot edit timing on the waveform. Aegisub /
   SubtitleEdit users hit a wall.
2. **Multi-Engine Sync (Plan B7)** runs ffsubsync → alass as a
   sequential fallback chain with a sanity threshold and an audit log,
   but the UI is read-only and the chain is not user-editable. Bazarr
   runs a single engine; Lingarr has none; Subservient's "Smart Sync"
   tries multiple and picks the best.

The user wants **gold standard** for both. Gold standard here means
**Aegisub/SubtitleEdit feature parity in the browser** for editing, and
**parallel-pick-best with confidence scoring + diff preview** for sync.

We do **not** intend to clone Aegisub. We intend to ship the timing
surface a self-hoster needs to fix a misaligned anime episode without
leaving the browser, and to ship the sync surface that gives the user
*reasoned* trust in the result.

## Non-Goals

- ASS karaoke composition from scratch (we display syllables, we don't
  retime them as an authoring tool — that's Aegisub's domain).
- Real-time collaborative editing (single-user web tool).
- Spectrogram-based speaker diarization.
- Replacement of `pysubs2` as the canonical subtitle parser.
- Replacement of the existing sequential-fallback orchestrator —
  parallel-pick-best is **added** alongside, not instead-of.

## Architecture Overview

### Feature 1 — Waveform Editor (Phase B8)

**Frontend module:** `frontend/src/components/editor/waveform/`
A new sub-package that owns the WaveSurfer instance, regions, snap
logic, keyboard map, spectrogram overlay, and write-back to the
canonical Cue Editor state.

**Backend additions:**
- `routes/audio.py` — extend with `/api/v1/audio/keyframes/<video>`
  (ffprobe-based shot/keyframe extraction, cached per video file
  mtime+size hash).
- `services/scene_detector.py` — PySceneDetect wrapper, lazy import,
  graceful degradation.
- `services/audio_visualizer.py` — already has `audio_track_index`
  parameter; expose audio-track listing endpoint.

**State model (single-source-of-truth rule):**
The canonical cue list lives in the `SubtitleEditorModal` React state.
The waveform writes back through a `useCueEditor()` hook — never directly
to a separate ref. Drag operations debounce-commit at drag-end (not
during drag) so the editor table doesn't thrash.

### Feature 2 — Smart Sync (Phase B9)

**Backend module:** `backend/services/sync_engines/` (extends B7 package)
- `parallel_orchestrator.py` — runs configured engines concurrently in a
  ThreadPoolExecutor, computes confidence per result, picks the winner.
- `confidence.py` — confidence metric: cross-correlation between the
  audio energy envelope (already extracted by audio_visualizer) and the
  proposed cue activation timeline. Returns 0.0–1.0.
- `subaligner_engine.py` — new BaseSyncEngine wrapping
  [baxtree/subaligner](https://github.com/baxtree/subaligner) (DNN-based
  drift correction).
- `revert.py` — reads the original subtitle bytes from the
  `sync_job_runs` audit row (we already record the path, but not the
  pre-sync bytes) and restores them.

**Schema additions** (single Alembic migration):
- `sync_job_runs.confidence` — `Float` nullable
- `sync_job_runs.subtitle_bytes_before` — `LargeBinary` nullable
  (compressed via zlib; capped at 256 KB; older rows cleaned by the
  existing `scheduler_history_cleanup` job)
- `series_settings.preferred_sync_engines` — `JSON` nullable (list of
  engine names, e.g. `["alass", "ffsubsync"]`)
- `movie_settings.preferred_sync_engines` — same shape

**Frontend additions:**
- `frontend/src/components/sync/SyncDiffView.tsx` — table + waveform
  overlay (reuses the B8 waveform component), apply/cancel.
- `frontend/src/pages/Settings/SyncEnginesTab.tsx` — extend with mode
  switch (sequential | parallel) and a **chain-edit** drag-sortable list.
- `frontend/src/components/sync/SyncRunButton.tsx` — manual run with
  engine selector (single, multi, or "use-show-policy").

## Tier Breakdown (per feature)

### Phase B8 — Waveform Editor Tiers

| Tier | Feature | Effort | License risk |
|---|---|---|---|
| **1** | WaveSurfer Regions in **drag/resize** mode + cue-state write-back | S | none (BSD-3) |
| **1** | Aegisub-map: L-click = set start, R-click = set end | S | none |
| **1** | Snap (keyframes from ffprobe + neighbor-cue boundary + configurable min-gap) | M | none |
| **1** | Keyboard shortcuts (Space, S/D/F/G, ←/→/↑/↓) + `?`-overlay help | S | none |
| **1** | Auto-scroll-on-playback toggle, zoom 1×–50× | S | none |
| **1** | Multi-audio-track picker (Center for Dialog) | S | none |
| **2** | Spectrogram toggle (WaveSurfer `Spectrogram` plugin) | S | none (BSD-3) |
| **2** | Audio scrubbing while dragging | S | none |
| **2** | ASS karaoke syllable overlay (when format=ass) | M | none (`pysubs2` MIT) |
| **2** | Scene-detection markers (PySceneDetect server-side) | M | none (BSD-3) |
| **3** | ffmpeg.wasm client-side audio extraction | L | LGPL-2.1+ (compatible with GPL-3) |

### Phase B9 — Smart Sync Tiers

| Tier | Feature | Effort | License risk |
|---|---|---|---|
| **1** | Orchestrator mode toggle (sequential | parallel) | M | none |
| **1** | Confidence score per engine result | M | none |
| **1** | Diff-view UI (table + waveform overlay) before apply | M | none |
| **1** | Manual sync run with engine-picker | S | none |
| **1** | Per-show / per-movie preferred engines | S | none |
| **2** | `subaligner` engine | M | MIT (compatible) |
| **2** | Selective apply (lock specific lines, e.g. intro/outro) | M | none |
| **2** | Audit-log replay / revert-to-pre-sync-bytes | M | none |
| **3** | WhisperX anchor engine (LLM-grounded re-anchor) | L | BSD-2 lib + heavy GPU dep |

## License Audit (consolidated)

Sublarr is licensed under **GPL-3.0**. All listed dependencies are
compatible because:

| Dep | License | Linkage | Compatible with GPL-3? |
|---|---|---|---|
| `wavesurfer.js@7.x` (already installed) | BSD-3-Clause | npm import (static link) | ✅ |
| `wavesurfer.js/plugins/regions` | BSD-3-Clause | npm import | ✅ |
| `wavesurfer.js/plugins/spectrogram` | BSD-3-Clause | npm import | ✅ |
| `pysubs2` (already installed) | MIT | python import | ✅ |
| `PySceneDetect` (new) | BSD-3-Clause | python import (lazy) | ✅ |
| `subaligner` (new) | MIT | python import (lazy) | ✅ |
| `ffsubsync` (already installed) | MIT | python import | ✅ |
| `alass` (already installed) | GPL-3.0 | **subprocess** (not linked) | ✅ subprocess invocation does not trigger GPL propagation |
| `ffmpeg` (already installed binary) | LGPL-2.1+ (with --enable-gpl: GPL-2+) | **subprocess** | ✅ subprocess does not trigger LGPL/GPL propagation |
| `@ffmpeg/ffmpeg` wasm bundle (Tier 3) | MIT bindings + LGPL-2.1+ FFmpeg core | bundled in static asset | ✅ LGPL-2.1+ is one-way compatible with GPL-3; carry license + offer source link |
| `WhisperX` (Tier 3) | BSD-2-Clause | python import | ✅ |
| `stable-ts` (Tier 3 alternative) | MIT | python import | ✅ |

**Idea-mining vs. code-copying** — Aegisub (BSD-3) and SubtitleEdit
(partial GPL-3) are sources of feature inspiration only. We are not
copying code, UI assets, audio fixtures, or icon glyphs from either
project. Aegisub keyboard shortcuts (Medusa map: S/D/F/G) are user
interaction conventions, not copyrightable.

**Compliance steps** baked into both phase plans:
1. Each new dep is added with its license marker in `requirements.txt`
   (Python) or `package.json`'s embedded license metadata (JS).
2. `npx license-checker --production --summary` runs in CI; any
   non-`(BSD|MIT|Apache-2.0|ISC|LGPL-*|GPL-3.0)` license fails the build
   and requires manual review.
3. Tier 3 ffmpeg.wasm bundle, when added, ships its `LICENSE.txt`
   alongside the WASM blob in the static dist; about page links to the
   source mirror (LGPL §6 obligation).
4. New backend deps run through `pip-licenses --format=markdown` on
   release day; output is committed to `docs/THIRD-PARTY-LICENSES.md`
   (currently does not exist — will be created in Phase B8 Task 1 as a
   prerequisite).

## Acceptance Criteria (consolidated)

### Phase B8 — done when:
- A user can grab a cue boundary on the waveform, drag it to a new
  position, release, and see the cue editor table reflect the new
  start/end timestamp within 100 ms.
- L-click on a non-cue region of the waveform during a selected cue
  sets that cue's start; R-click sets its end. Snap-to-keyframe is
  applied if within ±150 ms of a keyframe.
- Pressing `?` opens a shortcut overlay enumerating every implemented
  binding.
- The spectrogram toggle reveals the FFT view with no perceptible lag
  on a 24-minute episode.
- All cue edits are reversible via the editor's existing undo stack.

### Phase B9 — done when:
- The user can pick "parallel" mode in `Settings → Sync Engines` and the
  next manual sync run executes both ffsubsync and alass concurrently,
  recording two `sync_job_runs` rows with confidence scores.
- Before applying any sync result, a diff view opens showing
  per-cue-line delta in milliseconds with rows >200 ms highlighted.
- The user can reject the result and the original subtitle bytes are
  preserved (DB row's `subtitle_bytes_before` was never written, so
  there's nothing to revert).
- Per-show engine policy ("always alass for anime") propagates to the
  scheduler — wanted-search-driven syncs respect the override.

## Out-of-Scope (explicit)

- Rebuilding Aegisub karaoke authoring (`\k`, `\K`, `\kf` syllable
  retiming).
- Real-time multi-user editing.
- Cloud-rendered waveform service (everything runs on Cardinal).
- Subtitle re-encoding format conversions inside the waveform editor —
  the editor stays format-faithful; conversion lives in Tools tab.
- Replacement of WaveSurfer with a custom Canvas implementation.

## Risks

1. **WaveSurfer drag handlers race with React state.** Mitigation:
   debounce-commit at drag-end, not during; freeze cue list during
   drag via a `dragging` flag.
2. **PySceneDetect cold-start cost** on long videos (~30s for a 24min
   episode). Mitigation: cache per (video_path, mtime, size) hash;
   compute lazily on first waveform open per video.
3. **subaligner's DNN model bundle is ~50 MB.** Mitigation: do **not**
   bundle in the Docker image; download on first use to `/config/models`
   with a graceful "subaligner unavailable" fallback if the user is
   offline at first run.
4. **Parallel sync resource spike** — running ffsubsync + alass + maybe
   subaligner at once doubles/triples CPU. Mitigation: a per-job
   `Semaphore(2)` so at most 2 engines run concurrently per sync
   request; degrade to sequential when CPU pressure is high (use the
   existing `psutil` pattern from monitoring).
5. **ffmpeg.wasm bundle size** (Tier 3): ~30 MB extra in the dist.
   Mitigation: lazy-load behind a Settings toggle; default off.
6. **WhisperX GPU dep** (Tier 3): Cardinal is CPU-only Unraid.
   Mitigation: drop entirely or proxy through Mac mini Ollama (which
   already runs Whisper). **Decision deferred to a later phase.**

## Plan Files

- `docs/superpowers/plans/2026-05-02-plan-b8-waveform-editor-gold-standard.md`
- `docs/superpowers/plans/2026-05-02-plan-b9-smart-sync-gold-standard.md`

Both phase plans cover Tier 1 + Tier 2. Tier 3 items are documented in
each plan's "Future Work" section but not scheduled.
