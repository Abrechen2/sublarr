# Plan B8 — Waveform Editor (Gold Standard)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan
> task-by-task.

**Spec:** `docs/superpowers/specs/2026-05-02-gold-standard-editor-sync-design.md`
**Prior:** B7 shipped as 0.70.0-beta — multi-engine sync orchestrator.
**Baseline:** 0.82.4-beta → 0.83.0-beta (minor bump, new user-facing surface).
**Scope:** Tier 1 + Tier 2. Tier 3 (ffmpeg.wasm) deferred.

**Goal:** Promote `WaveformTab` from read-only viewer to an editing
surface comparable to Aegisub for the operations a self-hoster
actually performs: drag boundaries, set start/end with click, snap to
keyframes, see the spectrogram, jump with keyboard.

---

## Pre-Flight

- [ ] **Pre-1: Create third-party license registry**

  Create `docs/THIRD-PARTY-LICENSES.md` with current state by running:
  ```bash
  cd backend && pip-licenses --format=markdown --with-urls > /tmp/py_licenses.md
  cd frontend && npx license-checker --production --excludePackages='sublarr@*' --csv > /tmp/js_licenses.csv
  ```
  Combine into a single doc grouped by Python/JS/Binary. Commit. This
  is the canonical reference any Plan B8/B9 dep gets added to.

- [ ] **Pre-2: Wire `license-checker` into pre-deploy gate**

  Add to `Sublarr/CLAUDE.md` "Pre-Deploy Checks" block:
  ```bash
  cd frontend && npx license-checker --production --onlyAllow="MIT;BSD-2-Clause;BSD-3-Clause;Apache-2.0;ISC;LGPL-2.1-or-later;LGPL-2.1+;GPL-3.0;CC-BY-4.0;0BSD;Unlicense"
  ```
  Fail the deploy if the matrix turns red.

---

## File Structure

### Create
- `frontend/src/components/editor/waveform/WaveformEditor.tsx` —
  replaces the existing read-only `WaveformTab.tsx` (kept as wrapper for
  one release for ABI safety, then deleted).
- `frontend/src/components/editor/waveform/useWaveformRegions.ts` —
  hook that owns WaveSurfer + Regions plugin lifecycle and exposes a
  drag-end commit callback.
- `frontend/src/components/editor/waveform/snap.ts` — pure-function
  snap logic given (target_ms, keyframes, neighbors, min_gap_ms).
- `frontend/src/components/editor/waveform/keymap.ts` — Aegisub-style
  shortcut definitions and the help-overlay content.
- `frontend/src/components/editor/waveform/WaveformShortcutHelp.tsx` —
  modal for the `?` overlay.
- `frontend/src/components/editor/waveform/AssKaraokeOverlay.tsx` —
  syllable-level overlay rendered when `format === 'ass'`.
- `frontend/src/components/editor/waveform/__tests__/snap.test.ts`
- `frontend/src/components/editor/waveform/__tests__/useWaveformRegions.test.tsx`
- `backend/services/scene_detector.py` — PySceneDetect lazy wrapper.
- `backend/routes/audio.py` — extend (don't create) with
  `/api/v1/audio/keyframes/<encoded_path>` and
  `/api/v1/audio/scenes/<encoded_path>`.
- `backend/tests/test_scene_detector.py`
- `backend/tests/test_audio_keyframes_route.py`

### Modify
- `frontend/src/components/editor/SubtitleEditorModal.tsx` — swap
  `WaveformTab` import to `WaveformEditor`. Pass `onCueChange` callback
  so drag-end can write back into the modal's cue state.
- `frontend/src/components/editor/WaveformTab.tsx` — temporary thin
  re-export of `WaveformEditor` (one release, then delete).
- `backend/services/audio_visualizer.py` — add `list_audio_tracks(video_path)` returning
  `[{index, codec, channels, language, title}]`.
- `backend/requirements.txt` — add `scenedetect>=0.6.6,<1.0` (BSD-3).
- `frontend/package.json` — `wavesurfer.js@^7.12.5` already pinned;
  no new JS dep, the regions + spectrogram plugins ship with the
  existing package.
- `docs/THIRD-PARTY-LICENSES.md` — add `scenedetect` row.

### Delete
- (eventually, after 1 release of compatibility shim)
  `frontend/src/components/editor/WaveformTab.tsx`

---

## Task 1: Audio-track listing endpoint

- [ ] **Step 1: Extend `audio_visualizer.list_audio_tracks`**

  Add a new top-level function that runs:
  ```bash
  ffprobe -v error -select_streams a -show_entries
    stream=index,codec_name,channels:stream_tags=language,title
    -of json <video>
  ```
  Parse and return a `list[dict]`. Cache result keyed by
  `(video_path, mtime, size)` in an LRU (size 64) — same pattern the
  existing `extract_audio_track` uses.

- [ ] **Step 2: Wire route in `routes/audio.py`**

  ```python
  @bp.route("/audio/tracks/<path:video_path>", methods=["GET"])
  @require_auth
  def list_tracks(video_path: str):
      if not is_safe_path(MEDIA_ROOT, video_path):
          return jsonify({"error": "invalid path"}), 400
      return jsonify({"tracks": list_audio_tracks(video_path)})
  ```

- [ ] **Step 3: Tests**

  Unit-test the parse function with three saved ffprobe JSON fixtures
  (mono, 5.1, multi-track anime). Route test with `is_safe_path` reject.

- [ ] **Step 4: Frontend hook**

  `useAudioTracks(videoPath)` via React Query. Stale-time 1h.

---

## Task 2: Server-side keyframes & scenes

- [ ] **Step 1: ffprobe-based keyframes**

  In `audio_visualizer.py` add `list_keyframes(video_path: str) ->
  list[float]`:
  ```bash
  ffprobe -v error -select_streams v:0
    -show_entries packet=pts_time,flags
    -of csv=p=0 <video> | grep ',K' | cut -d, -f1
  ```
  Cache same as Task 1.

- [ ] **Step 2: PySceneDetect lazy wrapper**

  Create `services/scene_detector.py`:
  ```python
  def detect_scenes(video_path: str) -> list[float]:
      try:
          from scenedetect import detect, ContentDetector
      except ImportError:
          return []
      scenes = detect(video_path, ContentDetector(threshold=27.0))
      return [s[0].get_seconds() for s in scenes]
  ```
  Cache in `/config/cache/scenes/{hash}.json` (hash = sha256 of
  video_path + mtime + size). Cache eviction: existing
  `cleanup` scheduled job already prunes `/config/cache/*`.

- [ ] **Step 3: Routes**

  Two new routes in `routes/audio.py`:
  - `GET /api/v1/audio/keyframes/<path>` → `{"keyframes": [s, s, ...]}`
  - `GET /api/v1/audio/scenes/<path>` → `{"scenes": [s, s, ...]}`

  Both `@require_auth` and gated by `is_safe_path`.

- [ ] **Step 4: Tests**

  - PySceneDetect available: assert non-empty list.
  - PySceneDetect not installed (mock ImportError): assert `[]`.
  - Route negative path traversal.

- [ ] **Step 5: Add license row**

  Append to `docs/THIRD-PARTY-LICENSES.md`:
  ```
  | scenedetect | BSD-3-Clause | https://github.com/Breakthrough/PySceneDetect |
  ```

---

## Task 3: WaveSurfer regions in drag/resize mode

- [ ] **Step 1: Hook scaffold**

  Create `useWaveformRegions.ts` exposing:
  ```ts
  interface Args {
    container: RefObject<HTMLDivElement>
    audioUrl: string | null
    cues: Cue[]
    onCueChange: (idx: number, patch: Partial<Cue>) => void
    enableDrag: boolean
  }
  function useWaveformRegions(args: Args): {
    ws: WaveSurfer | null
    regions: RegionsPlugin | null
    isReady: boolean
    play: () => void; pause: () => void; isPlaying: boolean
  }
  ```

- [ ] **Step 2: Drag-end commit**

  Bind `regions.on('region-update-end', region => {...})`. On commit:
  call `onCueChange(idx, { start: region.start, end: region.end })`.
  Do **not** commit during `region-update` (per-frame drag) — only on
  drag-end.

- [ ] **Step 3: Freeze on drag**

  Maintain a `dragging` boolean ref; while true, ignore prop-driven
  region rewrites in the effect that syncs `cues` → regions. Otherwise
  React state-update during drag will reset the region position
  mid-drag.

- [ ] **Step 4: Tests**

  - Test renders 3 cues, simulates `region-update-end` for cue idx=1
    with `{start: 5.5, end: 7.2}`, asserts `onCueChange` called with
    those values.
  - Test that during a `region-update` event a stale-cue prop does not
    overwrite the in-progress drag.

---

## Task 4: Aegisub click-map + snap

- [ ] **Step 1: Click handler on waveform body**

  In `WaveformEditor.tsx`:
  - L-click on waveform (not on a region): if there's a "selected cue"
    in the cue editor, set that cue's `start` to the click position.
  - R-click: same for `end`.

  Selected-cue plumbed in via prop `selectedCueIdx: number | null` from
  `SubtitleEditorModal`.

- [ ] **Step 2: Snap function**

  Pure function in `snap.ts`:
  ```ts
  function snap(targetMs: number, opts: {
    keyframesMs: number[]; neighborsMs: number[];
    minGapMs: number; toleranceMs: number;
  }): { value: number; snappedTo: 'keyframe' | 'neighbor' | 'none' }
  ```
  Algorithm: find closest of (keyframes ∪ neighbors) within
  `toleranceMs`. If found, return that; else return original. If found
  but the resulting gap to `neighborsMs` would be `< minGapMs`, push to
  exactly `minGapMs`.

- [ ] **Step 3: Apply snap on drag-end and on click**

  Both Task 3's drag-end commit and Task 4's click set should pipe
  through `snap()`. Tolerance defaults: 150 ms keyframe, 80 ms neighbor;
  configurable via Settings (new fields under
  `config_settings.WaveformEditorSettings`).

- [ ] **Step 4: Tests**

  Pure unit-tests on `snap()` for the 8 edge cases (no neighbors, no
  keyframes, both within tolerance pick the nearer, both outside pick
  none, gap-violation push, exact-on-keyframe identity, etc).

---

## Task 5: Keyboard shortcuts + help overlay

- [ ] **Step 1: Keymap**

  In `keymap.ts`:
  ```ts
  export const WAVEFORM_KEYS = {
    ' ': 'playPause',
    's': 'setStart',
    'd': 'setEnd',
    'f': 'splitAtCursor',
    'g': 'mergeWithNext',
    'ArrowLeft': 'seekBack100ms',
    'ArrowRight': 'seekFwd100ms',
    'Shift+ArrowLeft': 'seekBack1s',
    'Shift+ArrowRight': 'seekFwd1s',
    'ArrowUp': 'prevCue',
    'ArrowDown': 'nextCue',
    '+': 'zoomIn',
    '-': 'zoomOut',
    '?': 'showHelp',
  } as const
  ```

- [ ] **Step 2: Wire global hotkeys**

  Use `react-hotkeys-hook` (already a dep — verify in package.json; if
  not, add — MIT licensed). Scope to the modal: shortcuts only fire
  while `SubtitleEditorModal` is open and not in a text input.

- [ ] **Step 3: Help overlay**

  `WaveformShortcutHelp.tsx` — full-screen-ish modal listing every
  keymap entry with its label, grouped by category (Playback, Timing,
  Navigation, Zoom).

- [ ] **Step 4: i18n**

  Add `editor.waveform.shortcut.*` keys to `frontend/src/i18n/locales/en/editor.json`
  and `de/editor.json`.

- [ ] **Step 5: Tests**

  - Render modal, focus body, press `s`, assert `setStart` action
    fired.
  - Render modal with focus inside `<input>`, press `s`, assert
    nothing fired (don't hijack typing).

---

## Task 6: Auto-scroll, zoom, multi-track picker

- [ ] **Step 1: Auto-scroll toggle**

  Use WaveSurfer's `autoScroll` and `autoCenter` options. Expose as a
  toolbar checkbox (default on).

- [ ] **Step 2: Zoom**

  WaveSurfer `ws.zoom(pxPerSec)`. Toolbar slider 1–50, plus `+/-`
  shortcuts.

- [ ] **Step 3: Audio-track dropdown**

  Use `useAudioTracks` from Task 1. Switching track:
  - Call `extractWaveform(videoPath, trackIndex)` (extend the existing
    API to accept track index).
  - Re-load the waveform; preserve current cue regions (no rebuild).

- [ ] **Step 4: Tests**

  Component test: render 3 tracks in dropdown, simulate change,
  assert `extractWaveform` called with new index.

---

## Task 7: Spectrogram toggle

- [ ] **Step 1: Plugin instantiation**

  Import `Spectrogram` from `wavesurfer.js/plugins/spectrogram`. Conditional
  registration: `useEffect` toggles on/off based on a state bool.

- [ ] **Step 2: Toolbar control**

  Toggle button next to zoom slider. Persists per-user via localStorage.

- [ ] **Step 3: Performance budget**

  Spectrogram's FFT can be expensive. Set `fftSamples: 512`, `noverlap:
  256` for the default; expose advanced controls only via Settings →
  Advanced.

- [ ] **Step 4: Tests**

  Component test with `vi.mock` for the plugin; assert that toggling
  attaches/detaches it.

---

## Task 8: Audio scrubbing while dragging

- [ ] **Step 1: Region-update playback**

  On `regions.on('region-update', region => {...})` (per-frame, not
  drag-end), seek the WaveSurfer cursor to `region.start` and play a
  short window (200 ms). Throttle to 30 Hz.

- [ ] **Step 2: Toolbar toggle**

  Default off (it's loud during long drags). Setting persisted in
  user prefs.

- [ ] **Step 3: Tests**

  Mock `ws.seekTo` and `ws.play`; assert correct invocations on
  region-update event.

---

## Task 9: ASS karaoke syllable overlay (Tier 2)

- [ ] **Step 1: Parse syllables**

  Extend the existing subtitle-parse endpoint
  (`/api/v1/subtitles/parse`) to emit, when `format === 'ass'`, the
  per-cue syllable list with timings (use `pysubs2` event override
  parser, look for `\k`, `\K`, `\kf`, `\ko` tags).

- [ ] **Step 2: Render syllables**

  `AssKaraokeOverlay.tsx` — when active cue is ASS, paint vertical
  ticks on the waveform at each syllable boundary, labelled with the
  syllable text.

- [ ] **Step 3: Tests**

  Backend test: feed an ASS line `{\k50}Hel{\k60}lo`, assert two
  syllables with offsets `[0.0, 0.5]` and `[0.5, 1.1]`.

  Frontend test: render component with two syllables, assert two `<g>`
  marker elements present.

- [ ] **Step 4: Note**

  We display, we do not retime syllables. That stays Aegisub's domain.

---

## Task 10: Scene-detection markers (Tier 2)

- [ ] **Step 1: Frontend hook**

  `useSceneMarkers(videoPath)` calls `/api/v1/audio/scenes/<path>` from
  Task 2.

- [ ] **Step 2: Render markers**

  Vertical lines on the waveform at each scene boundary, color
  `var(--accent-dim)` thin. Skip if list is empty (PySceneDetect not
  installed).

- [ ] **Step 3: Snap-to-scene option**

  Extend `snap.ts` opts with `scenesMs: number[]` and a separate
  tolerance default 200 ms.

---

## Task 11: Wire write-back to cue editor + integration tests

- [ ] **Step 1: Modal wiring**

  In `SubtitleEditorModal.tsx`:
  ```tsx
  <WaveformEditor
    subtitlePath={subtitlePath}
    videoPath={videoPath}
    cues={cues}
    selectedCueIdx={selectedCueIdx}
    onCueChange={(idx, patch) => updateCue(idx, patch)}
  />
  ```
  `updateCue` already exists for the existing cue table — reuse it.

- [ ] **Step 2: Undo integration**

  Existing modal has an undo stack (Ctrl+Z). Drag-end commits push
  onto the same stack. Verify that one drag = one undo step (not 60
  per-frame steps).

- [ ] **Step 3: E2E test**

  New Playwright test
  `frontend/e2e/waveform-editor.spec.ts`:
  - Open modal on a fixture episode
  - Drag cue 5's right boundary by 1 second
  - Assert cue editor table shows new end timestamp
  - Press Ctrl+Z
  - Assert original timestamp restored

---

## Task 12: Documentation + release prep

- [ ] **Step 1: User-guide page**

  Create `SublarrWeb/src/content/docs/docs/user-guide/waveform-editor.md`
  with screenshots of all toolbar controls, shortcut table, and
  examples for "drag to resize", "click to set start/end",
  "spectrogram on/off".

- [ ] **Step 2: CHANGELOG**

  Add 0.83.0-beta section to `Sublarr/CHANGELOG.md` highlighting:
  - Editable waveform with drag/resize
  - Aegisub-style click-map
  - Snap to keyframes & neighbor cues
  - Spectrogram, audio-tracks, keyboard shortcuts
  - PySceneDetect optional dep

- [ ] **Step 3: Version bump + deploy**

  Use the `deploy` skill (auto-bumps to 0.83.0-beta, builds, pushes,
  pulls on Cardinal).

- [ ] **Step 4: License-checker pass on deploy**

  The new pre-deploy gate from Pre-2 must be green; if `scenedetect`
  is flagged because pip-licenses doesn't recognise its SPDX, edit
  `THIRD-PARTY-LICENSES.md` manually with verified upstream license.

---

## Future Work (Tier 3, not in this plan)

- **ffmpeg.wasm client-side audio extraction** — saves Cardinal CPU,
  but +30 MB JS bundle and LGPL compliance docs (offer-source link,
  preserve license headers in the dist). Implement only if Cardinal
  CPU contention becomes a real bottleneck.
- **Frame-perfect timing display** (drop-frame timecode for NTSC)
  — Aegisub power-user feature, niche for self-hosters.
- **Onset-detection auto-cue** (machine-suggest cue boundaries from
  audio peaks) — research-grade, defer to a future Phase B10.

---

## Acceptance Test Plan

1. Open `Library → Episode → Edit Subtitle` on an anime episode.
2. Cue 1's start is currently at 14.230 s. Grab the left boundary on
   the waveform, drag to 14.500 s, release. The cue editor table now
   shows `00:00:14,500`. Press Ctrl+Z. Back to `00:00:14,230`.
3. Click on cue 1, then L-click on the waveform at 14.000 s. Cue 1
   start = `00:00:14,000`.
4. Toggle the spectrogram. The frequency view appears within 500 ms.
5. Press `?`. Help overlay lists every shortcut.
6. Switch audio track to Japanese (track 1). Waveform reloads, regions
   stay.
7. Press Space. Playback follows the cursor with auto-scroll.
8. Run `task lint && task test:frontend` — green.
9. Run `cd frontend && npx license-checker --production` — only
   compatible licenses listed.
