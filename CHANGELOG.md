# Changelog

All notable changes to Sublarr are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.86.6-beta] - 2026-05-03

### Fixed
- **Waveform sync-scroll: borderLeftColor via inline-style** — Tailwind v4 kept overriding the left-border colour through the `border-border` shorthand on this row, regardless of whether we used `border-l-{token}`, `border-l-[#hex]`, or `[border-left-color:#hex]` arbitrary-property syntax. The class string carried the right utility, but the computed style stayed at the gray `--border` token. Worked around with an inline `style={{ borderLeftColor }}` — CSS specificity rules guarantee inline-style beats any class selector, so the cyan/amber stripes now actually render. Permitted by the project's "Tailwind-can't-reach" inline-style escape hatch.

## [0.86.5-beta] - 2026-05-03

### Fixed
- **Waveform sync-scroll: arbitrary-property border-left-color** — 0.86.4's `border-l-[#hex]` arbitrary VALUE syntax also failed to override `border-border`'s shorthand color in Tailwind v4 (computed `borderLeftColor` stayed at the gray `--border` token even though the class string carried the hex). Switched to arbitrary PROPERTY syntax `[border-left-color:#hex]` which emits the CSS rule directly and is no longer subject to shorthand overrides. The colored left stripes (cyan for in-viewport / active, amber for now-playing) should now render reliably.

## [0.86.4-beta] - 2026-05-03

### Fixed
- **Waveform sync-scroll: visible left-border stripe** — 0.86.3's `border-l-[var(--accent-dim)]` arbitrary value didn't resolve through Tailwind v4 (computed border stayed at the default gray `--border` token), so the left-stripe distinction between in-viewport and out-of-viewport rows was missing. Switched to hex literals (`#0a7089` for in-viewport stripe, `#1DB8D4` for active selection, `#f59e0b` for now-playing) so the borders are guaranteed to render. The cyan-tinted background already landed correctly in 0.86.3.

## [0.86.3-beta] - 2026-05-03

### Changed
- **Waveform sync-scroll: cyan-tinted band + active-row ring** — 0.86.2's `bg-elevated` switch made the in-viewport rows technically distinguishable, but the ~14-RGB-unit difference vs the dark cue-list container was still too subtle to read at a glance against the spectrogram-lit modal. Replaced with explicit cyan-tinted backgrounds via Tailwind v4 arbitrary values (`bg-[rgba(29,184,212,0.06)]` for in-viewport, hover `0.14`) plus a `border-l-[var(--accent-dim)]` stripe — guaranteed-visible regardless of any token-resolution edge cases. Active selection also gains a `ring-2 ring-inset ring-[var(--accent)]` so the bright cyan now-selected cue is unambiguous. Now-playing keeps its amber band.

## [0.86.2-beta] - 2026-05-03

### Changed
- **Waveform sync-scroll: visible tint + list-follows-wave + playhead highlight** — 0.86.0–.1's "subtle" `bg-surface/60` tint was effectively invisible against the dark `bg-primary` cue list, so editors couldn't see the in-viewport flag the wave was actually computing for them. Three concrete upgrades:
  - **Visible in-viewport tint.** Switched from `bg-surface/60` to `bg-elevated` plus a 4 px `border-l-accent-dim` stripe — the rows currently visible on the wave now form a clear band in the list. Active selection keeps its bright `border-l-accent` so it stays the unambiguous focus.
  - **Auto-follow when the wave scrolls.** When the wave's visible window changes (zoom, manual scroll, programmatic seek), the list auto-scrolls so the first in-viewport cue lands at the top of the list lane. Suppressed for ~3 seconds after any user wheel/pointerdown on the list itself, so reading ahead isn't yanked away whenever the wave moves.
  - **Now-playing highlight** while audio plays. New `playheadSec` state, exposed by `useWaveformRegions` via WaveSurfer's `timeupdate` event (throttled to 10 Hz so playback doesn't trigger 60 list re-renders per second). The cue containing the playhead picks up a warning-tinted `bg-warning-bg + border-l-warning` band — visually distinct from both the active selection and the in-viewport set, so editors can audit what they're hearing right now even when no cue is selected.

## [0.86.1-beta] - 2026-05-03

### Fixed
- **Sync-scroll highlight flagged ALL cues as "in viewport"** — 0.86.0's WaveSurfer `scroll`-event subscription only fires on user-initiated scrolls, not on programmatic `ws.zoom()` calls. The seed-on-ready fallback measured the wrapper width BEFORE the post-ready zoom had applied (when the wave still fits the full audio in the container width), so `visibleRange` degenerated to `[0, total_duration]` — every cue passed the intersection test, the entire list lit up as "visible", and the feature looked like a no-op. Replaced the seed with a real scroller-bound effect: native `scroll` event + `ResizeObserver` on both wrapper and scroller, recomputed after every zoom change inside a `requestAnimationFrame` so layout has flushed. Verified in prod with E01 of Witch Hat Atelier (285 cues, 23 min audio): `inViewportCount` now reflects the actual ~10–25 cues currently on screen instead of all 285.

## [0.86.0-beta] - 2026-05-03

### Added
- **Waveform editor — clean wave + lock-by-default + Undo/Redo/Save + full-height list + sync-scroll** — five interlocking refinements that turn the Stacked-Lanes layout from "draggable rectangles plus a list" into a real production-ready timing surface:
  - **Region labels removed from the wave.** With 285+ cues per episode, dimmed labels overlaid on tightly-packed regions still produced an unreadable wall of letters. Cue text now lives only in the list lane below the wave; regions are pure timing rectangles. The wave is for audio reading, the list is for text reading — separate surfaces, separate jobs.
  - **Locked by default.** The Waveform tab opens read-only — drag, resize, L/R click-set and S/D hotkeys are inert until the editor explicitly clicks the **Gesperrt → Entsperrt** toolbar toggle. Protects against the "I just wanted to scroll, I didn't want to retime cue 47" footgun. The unlock state visualises with a warning-tinted button so the editor can see at a glance whether they're in look-mode or touch-mode.
  - **Undo / Redo / Save buttons in the toolbar.** Each waveform-driven cue-timing edit now pushes the previous content onto a per-modal undo stack; Undo pops back, Redo reapplies. Clear-on-fresh-edit semantics, so the user can't fork timelines. Save POSTs the dirty content to `/tools/content` directly from the Waveform tab — no more tab-hop to CodeMirror to persist a region drag. Save button stays disabled while there are no unsaved changes and shows an inline spinner during the round-trip.
  - **Cue list fills the full remaining height.** The 5-row visible cap is gone; the list now grows with the modal via `flex-1 min-h-0`. Toolbar / active-cue card / wave keep their fixed heights at the top, the list lane absorbs everything below — typically ~25 rows visible on a 1080p screen vs 5 before.
  - **Sync-scroll highlight.** WaveSurfer's `scroll` event drives a `visibleRange: [startSec, endSec]` state that flows into the cue list. Rows whose `[start, end]` intersect the current wave viewport pick up a soft `bg-surface/60` tint and a faint left-border, so the editor can see at a glance which cues are visible on the wave right now without losing the active selection's accent highlight. Click on a row still seeks the wave to that cue's start (origin guard prevents the fight-the-user auto-scroll).

### Tests
- 1 `useWaveformRegions` test rewritten to assert no `content` is painted on regions; 1 modal-suite mock extended to cover `useSaveSubtitle`. Total frontend suite: 1023 tests, all green.

## [0.85.0-beta] - 2026-05-03

### Added
- **Waveform Stacked-Lanes layout** — restructures the Waveform tab from a "dashboard" layout (active-cue card above the wave + 12-control toolbar wedged below the wave) to a "control → focus → context" linear workflow. The toolbar now sits at the top (DAW convention; the editing zone — wave + list — stays together at the bottom for short mouse-travel), the active-cue card stays directly above the wave for "what am I timing right now" focus, and a new synchronized 5-row `WaveformCueList` lane appears underneath. Region labels overlaid on the wave dim from ~0.95 to ~0.55 alpha — the wave is no longer the primary text-reading surface, so labels remain only as faint navigation anchors during a drag. The new "Liste" toolbar toggle collapses the list when the editor wants the full ~250 px wave height back; preference persists in `localStorage` alongside the other waveform prefs. Cue list rows auto-scroll the active row into view on selection-change with an origin flag that suppresses the scroll when the user just clicked a row themselves — avoids the classic scroll-fight from bidirectional selection feedback loops. Read-only first pass; inline text editing, add/delete/split/merge UI affordances are layered in subsequent steps.

### Tests
- 11 new tests for `WaveformCueList` covering render / select / scroll / quality-dot semantics; 1 existing `useWaveformRegions` test updated to match the new dimmed-span content contract. Total waveform suite: 122 tests, all green.

## [0.84.1-beta] - 2026-05-03

### Fixed
- **Waveform audio blocked by CSP in production** — The Content-Security-Policy header had no `media-src` directive, so it fell back to `default-src 'self'` and blocked every `blob:` URL. WaveSurfer fetches the extracted audio from `/api/v1/tools/waveform-audio/`, wraps it in `URL.createObjectURL()`, and feeds the resulting blob into an internal `<audio>` element — which the browser charges against `media-src`, not `connect-src`. The Waveform tab in the subtitle editor was therefore unusable on prod; only the local Vite dev server, which emits no CSP, hid the bug. Added `media-src 'self' blob:` to the CSP. Verified locally with a same-origin blob: probe on `<audio>.src` — `loadstart` fires, console clean.

## [0.84.0-beta] - 2026-05-03

### Added
- **Waveform editor — Gold-Standard Edition** — seven UX upgrades that turn the Waveform tab from "draggable rectangles on audio" into a real Aegisub-class timing editor:
  - **Active-cue text bar** above the wave shows the currently selected cue's `Cue N / total`, start/end timecodes (`HH:MM:SS.mmm`), duration, and the cue text rendered multiline with ASS override tags stripped and `\N` converted to real newlines. When no cue is selected, hint copy invites the editor to pick one — no more tab-switching to know what you're aligning.
  - **Per-region text labels** — every region now carries a one-line label (truncated to 60 chars, override tags stripped, line breaks collapsed) drawn directly inside the region. Drag commits move the label with the region.
  - **Visible keyframe markers** — new toolbar pill ("Keyframes") paints thin teal vertical lines at every keyframe so the snap targets are no longer invisible. Default off because keyframes are dense (~one per 0.5 s); persisted in `localStorage`. Aside, the toolbar status now shows `Snap: N keyframes` when the toggle is on.
  - **Vertical amplitude zoom (1×–5×)** — toolbar slider drives WaveSurfer's `barHeight`, scaling the wave's visual amplitude so quiet dialogue (whispers, ambient narration) becomes editable without re-encoding. Persisted.
  - **Pitch-preserving playback rate (0.5×–2×)** — toolbar slider wired to `setPlaybackRate(rate, true)` (`preservesPitch=true`). Aegisub-style slow-mo audition for fast dialogue. Persisted.
  - **Gap/overlap quality markers** — pure helper `gapOverlap.detectGapsAndOverlaps()` scans adjacent cue pairs and paints red bars along the bottom for overlaps (`next.start < prev.end`) and amber bars for tight gaps (`< 80 ms`). Always-on by default; tooltips name the offending cue pair. On Archer S01E01 with 797 cues this surfaces 587 quality signals — exactly the kind of thing the editor wants flagged.
  - **Sticky time-axis ruler** — `TimelinePlugin` pinned above the canvas with primary labels every 5 s and secondary every 1 s. Stays in sync with horizontal zoom; removes the "where am I in the episode" friction during long zoom-in sessions.

### Tests
- 32 new unit tests across 4 new test files: `cueTextDisplay.test.ts` (16), `WaveformActiveCueBar.test.tsx` (7), `gapOverlap.test.ts` (8), `useWaveformRegions` (1 added for label propagation). 111 total in the waveform module — 0 regressions.

## [0.83.1-beta] - 2026-05-02

### Fixed
- **Waveform tab unreachable from SeriesDetail** — Three regressions blocked Plan B8's Waveform Editor end-to-end on the per-pill action menu, so 0.83.0's gold-standard timing surface was inaccessible in practice. Fixed in one commit:
  - `SeriesDetail.tsx` never threaded `videoPath` into `SubtitleEditorModal`, so the modal's `MODE_TABS` always suppressed the Waveform tab. `videoPath` now flows through `onPreviewSub` / `onEditSub` from `SeasonGroup`, carrying `ep.file_path` to the modal.
  - `ffmpeg` refused libopus at 22 050 Hz — Opus only accepts 8/12/16/24/48 kHz. Switched the waveform extract to 24 kHz so audio extraction stops failing on every real-world video. CI never caught this because tests mocked `subprocess.run`.
  - WaveSurfer.js issues its own internal fetch for the audio URL, bypassing our axios interceptor, so `/api/v1/tools/waveform-audio/` returned 401 forever. That single GET is now auth-exempt — the route already constrains lookups to a `.opus` file under `tempfile.gettempdir()` with high-entropy filenames, matching the existing OpenAPI / webhook exemptions.

## [0.83.0-beta] - 2026-05-02

### Added
- **Waveform editor — gold-standard subtitle timing surface** — the `Waveform` tab inside the subtitle editor modal is no longer a read-only viewer; it's now an Aegisub-class editing surface. Drag a region's left or right edge to retime a cue, drag the whole region to shift it (duration preserved), or use the new Aegisub L/R click-map to set the selected cue's start (left-click) and end (right-click) at the clicked time. Every drag-end and click commit snaps to the nearest video keyframe (within 150 ms) or neighbor cue boundary (within 80 ms), with ties broken in favor of the keyframe — the same convention Aegisub and SubtitleEdit use because keyframes are stronger anchors than nearby cue ends. A configurable minimum gap (default 80 ms) prevents accidentally collapsing a cue to zero duration. Snap targets come from new `GET /api/v1/audio/keyframes` and `GET /api/v1/audio/scenes` endpoints, both backed by the existing media-path security gate; PySceneDetect is an optional dependency, so installations without it just see no scene markers instead of an error.
- **Aegisub-style keyboard surface** — Space toggles play/pause; `S` and `D` set the selected cue's start and end at the playhead (snapped); `F` and `G` will split or merge cues once the parent modal exposes those callbacks; arrow keys nudge the playhead by 100 ms (1 s with Shift); Up/Down step the cue selection; `+` / `-` step zoom multiplicatively; `?` opens a help overlay listing every binding grouped by category. Bindings are scoped so typing in a text field never hijacks them, and the help overlay disables the global keymap while it's open so its own ESC dismisses it cleanly. EN + DE i18n keys ship under `editor.waveform.shortcut.*`.
- **Zoom + auto-center + audio-track picker** — toolbar slider (1–50 px/sec) drives `ws.zoom()` with the same multiplicative step the `+/-` keys use. An auto-center checkbox keeps the playhead centred during playback. When the underlying video has more than one audio track, a dropdown lets the user pick (e.g. JPN dialog vs. EN dub), and `POST /api/v1/tools/waveform-extract` now accepts an optional `track_index` to extract that specific audio stream. The backend cache key includes the track index so per-track extracts don't clobber each other; switching tracks back and forth is near-instant after the first extract per stream.
- **Spectrogram overlay (opt-in)** — pill button on the toolbar registers WaveSurfer's spectrogram plugin lazily so users who never toggle it on don't pay the FFT cost. Defaults match the plan's performance budget (`fftSamples=512`, Mel scale, 80 px tall) — cheap enough for live editing, plenty of detail for picking syllables out of dialogue. Preference persists in `localStorage`.
- **Audio scrubbing while dragging (opt-in)** — when enabled, dragging a region edge plays a 200 ms window around the moving boundary so the user can hear what they're aligning to without releasing the mouse. Throttled internally to ~30 Hz so a long drag doesn't become a zipper noise. Direction-aware: end-edge drags play `[end - 0.2, end]`; start- and whole-region drags play around `start`. Off by default (it's loud during long drags), preference in `localStorage`.
- **Scene-detection markers + snap-to-scene** — when PySceneDetect is installed, scene-cut boundaries paint as thin amber vertical lines on the waveform, anchored to percentage-of-duration so they stay aligned across zoom. Scene cuts also now act as a third snap pool (default tolerance 200 ms): drag-end and click commits compare keyframes, scenes, and neighbour cues by absolute distance and pick the closest hit, with ties broken in priority order keyframe > scene > neighbour. Hard cuts thus become explicit "stop here" anchors without ever overriding a tighter keyframe match.
- **ASS karaoke syllable overlay** — when the active cue is an ASS karaoke line (`\k`, `\K`, `\kf`, `\ko` overrides), the waveform paints a thin purple tick per syllable on top of the audio. New backend module `services/ass_karaoke.py` parses the syllable timings out of `event.text` (override-tags intact) and `routes/tools/parse` attaches them to ASS cues. Display only — Sublarr deliberately does not retime karaoke; that workflow stays in Aegisub. Eight backend parser tests + seven frontend overlay tests cover every variant including pre-tag content drops, zero-duration syllables, and tags interleaved with `\b1`-style override blocks.
- **Cue write-back from the waveform** — every drag-end, click-set, and S/D hotkey commits flows through `applyCueTiming(content, format, idx, start, end)`, a pure helper that rewrites a single cue's timing inside the SRT or ASS text body without re-stringifying the rest of the file. Multi-line text bodies, ASS Dialogue commas inside the Text field, CRLF vs LF endings, and SSA aliases are all preserved. VTT and unknown formats throw `UnsupportedFormatError`, which the modal surfaces as a polite toast and falls back to read-only behaviour. Drag commits land in the existing modal `content` state and respect the existing Save flow; CodeMirror-undo integration of waveform commits is documented as a follow-up since it requires sharing the edit history across two child components.

### Backend
- New `services/scene_detector.py` lazily imports PySceneDetect and exposes `detect_scenes(video_path, threshold=27.0)`. New `services/audio_visualizer.list_audio_tracks(video_path)` and `list_keyframes(video_path)` wrap `ass_utils.get_media_streams` and a fresh `_run_ffprobe_keyframes` boundary for testability. `requirements.txt` adds `scenedetect>=0.6.6,<1.0` (BSD-3-Clause); the import is lazy + optional so a stripped install just degrades the markers feature.
- `POST /api/v1/tools/waveform-extract` accepts an optional non-negative integer `track_index` and validates it at the boundary (rejects strings, bools, and negatives with HTTP 400). When present, ffmpeg is invoked with `-map 0:a:<idx>` and the audio cache key gains the track index dimension.

### Frontend
- New `components/editor/waveform/` module: `WaveformEditor.tsx` (replaces `WaveformTab` as the canonical editing surface; legacy import remains as a thin wrapper for one release), `useWaveformRegions.ts` (owns WaveSurfer + Regions + Spectrogram lifecycle, drag-end snap pipeline, L/R click-map, scrub-on-drag, zoom + auto-center + scene markers), `snap.ts` (pure snap helper), `applyCueTiming.ts` (pure cue-timing rewrite for SRT/ASS), `keymap.ts` + `WaveformHotkeys.tsx` + `WaveformShortcutHelp.tsx` (Aegisub keymap surface), and `WaveformAudioTrackPicker.tsx` (multi-track dropdown). The module ships 67 unit tests covering every snap branch, both click directions, drag-end edge detection, whole-region duration preservation, zoom + autoCenter + spectrogram + scrub gating, scene-marker positioning + cleanup, audio-track picker label/dispatch, hotkey dispatch + form-tag skip, help-overlay rendering + close behaviour, and SRT/ASS write-back including CRLF preservation and intra-text commas.
- `SubtitleEditorModal.tsx` switches its waveform tab from `WaveformTab` to `WaveformEditor` and wires `onCueChange` (writes through `applyCueTiming` into the modal's content buffer + marks unsaved), `selectedCueIdx`, and `onSelectAdjacentCue` so the keyboard Up/Down stepping has something to drive.

### Licenses
- All new dependencies are GPL-3.0-compatible: `scenedetect` (BSD-3-Clause). The frontend `wavesurfer.js@^7.12.5` Spectrogram plugin and Regions plugin ship with the existing package — no new JS dependency.

### Deferred
- **CodeMirror-undo integration of waveform commits** — drag commits enter the modal's content state but not the CodeMirror history, so Ctrl+Z inside the Edit tab won't roll back a waveform-driven retime. Will share the undo machinery in B9-era work.
- **E2E Playwright spec for the waveform editor** — relies on a fixture episode in CI; deferred to follow-up release.

## [0.82.4-beta] - 2026-05-02

### Fixed
- **Phantom subtitle tracks in Plex/Emby/Jellyfin** — Repair backups produced by the subtitle processor were written next to the active sub as `<base>.<lang>.bak.<ext>`. Media servers parse the segment immediately preceding `.srt` as a language code, and `bak` is the ISO-639-2/3 code for Bashkir, so every backup surfaced as a phantom "Bashkir (SRT)" track in the player UI. Backups now land in a hidden `<dir>/.sublarr/backups/` subdir media servers don't index. Pre-existing sibling-located backups remain readable via a fallback path resolver, so undo and bak-exists endpoints keep working until migration. Each successful restore opportunistically migrates the layout (one less file for the migration script). Adds `backend/scripts/migrate_subtitle_baks.py` for idempotent, dry-run-capable bulk migration.

## [0.82.3-beta] - 2026-05-01

### Changed
- **Settings page width and Health rail position** — the global content max-width was 1380 px which left wide monitors with large empty margins. Bumped to 1680 px so the list-detail-rail layouts have room to breathe. The `CollectionLayout` health rail moved from a 240-px sidebar column into a full-width strip beneath the list+detail row, and `HealthRail` itself now lays its cards out in a responsive 1/2/3/4-column grid (depending on viewport) instead of a single vertical stack. Net effect on `/settings/providers`: the detail pane gets the full available width, and the health items spread horizontally instead of piling up in a narrow column on the right.

## [0.82.2-beta] - 2026-05-01

### Fixed
- **Provider settings page health rail dominated by disabled providers** — `/settings/providers` rendered an "unhealthy" badge with a red X for every configured-but-disabled provider, so 18 off providers crowded out signals from the 9 active ones. The right rail now skips disabled providers entirely; only real conditions on active providers (rate-limited, circuit-open, unhealthy) appear there.
- **Provider detail pane duplicated the on/off state** — the toggle button already shows "Aktiviert" / "Deaktiviert", but the row directly below repeated the same state in a status pill. Hide that pill when the provider is plainly disabled with nothing else to report (no auto-disable, no test result, no error message), so the toggle is the single source of truth.
- **"Provider hinzufügen" button competed with the detail title** — the long button label squeezed into the narrow list-column header next to the detail's "Subf2m" title. Switched to an icon-only `+` button (24×24) with the original aria-label / title preserved for accessibility.

## [0.82.1-beta] - 2026-05-01

### Fixed
- **Upgrade scan respected `upgrade_enabled` only at the scheduler interval, not at runtime** — `services/scheduler.py` left the `upgrade_scan` job paused when `upgrade_enabled=False`, but `upgrade_scheduler._execute_scan()` itself never read the flag. A manual one-shot fire via `/api/v1/scheduler/upgrade_scan/run-now` (or any future code path that calls the tick directly) would still scan the library, find low-score downloads, and re-queue them — silently violating the user's explicit "no upgrades" preference. The scan now bails out at the top of `_execute_scan` with `{"queued": 0, "skipped": 0}` when the flag is `False`, so scheduled and ad-hoc invocations behave identically.

## [0.82.0-beta] - 2026-05-01

### Added
- **Anonymous OpenAPI discovery** — `GET /api/docs` (Swagger UI) and `GET /api/v1/openapi.json` are now exempt from the X-Api-Key gate, so power users can browse the full API surface without manually injecting a header. The Swagger UI still requires the key for "Try it out" calls via the standard Authorize flow, so authenticated endpoints remain protected.
- **Reusable Pydantic components** — `backend/schemas/api_components.py` introduces the first five domain models (`ErrorResponse`, `WantedItem`, `LanguageProfile`, `CleanupRule`, `SubtitleSidecar`) and registers each one in the OpenAPI spec under `#/components/schemas/<ClassName>` via `pydantic.model_json_schema()`. Routes can now reference shared shapes via `$ref` instead of inlining them, and the same models become the foundation for upcoming request-validation decorators and frontend codegen.

## [0.81.2-beta] - 2026-05-01

### Fixed
- **Single-item extract mislabeled stream language** — `POST /api/v1/wanted/<id>/extract` was reimplementing the legacy single-stream extractor inline and named the output sidecar after the wanted item's `target_language` (e.g. `de`) instead of the actual source stream's language. An English embedded stream landed at `*.de.ass` even though it contained English content. The route now delegates to the same `services.embedded_extractor` pipeline that the auto-extract drain and batch-probe use, so every text-based stream gets extracted and labelled by its own source language, off-target sidecars get trashed, and the response includes the same `extracted_count` / `sidecars_trashed` counters as the auto path. Legacy `stream_index` and `target_language` request fields are silently accepted for backward compat but no longer alter behaviour.

## [0.81.1-beta] - 2026-05-01

### Fixed
- **"API Key needed" on subtitle process/undo/restore actions** — Eight helpers in `api/system/tools.ts` (`processSubtitle`, `undoProcessSubtitle`, `checkBakExists`, `getInterjections`, `putInterjections`, `processSeries`, `processLibraryAll`, `updateSeriesProcessingConfig`) called bare `fetch()` against `/api/v1/...`, bypassing the axios request interceptor that injects the `X-Api-Key` header. With API-key auth enabled the per-pill HI removal / Common Fixes / Restore actions and the series/library batch-process buttons all returned 401 "API key required". All eight now route through the shared `api` axios instance, so the auth header is attached consistently.

## [0.81.0-beta] - 2026-05-01

### Changed
- **Clean episode/pill action split** — The per-episode `⋯` dropdown stopped duplicating sidecar-bound actions that the per-pill `⋯` already covered. Vorschau, Timing anpassen, Auto-Sync, Video-Sync and Health-Check now live exclusively on the language pill (no more `firstSubPath` heuristic that picked an arbitrary sub for the user). The episode menu keeps only genuinely episode-scoped actions: Vergleichen, Embedded Tracks, Interactive Search, History.
- **Pill timing opens the full sync modal** — The pill's "Timing anpassen" entry now opens the four-tab `SyncControls` modal (offset + speed + framerate + chapter) instead of the offset-only inline panel. Single timing entry point, full feature surface.

## [0.80.0-beta] - 2026-05-01

### Added
- **Subtitle backup management page** — Dedicated `/settings/cleanup/subtitle-backups` view, reachable from a footer link on the Cleanup settings page. Lists every `.bak.<ext>` file with language pill, modifier badges (HI/FORCED/SDH/CC), parent video, file size, age, and orphan status. Supports filtering (All / Orphans), per-row Restore (atomic swap-rename, never destructive) and Delete, plus bulk actions for purging orphans, purging aged backups (using `subtitle_bak_retention_days`) and a dry-run preview.
- **Compact per-pill action menu** — The dense per-language sidecar row in the series view is now `[Lang][Health][×][⋯]` (~8 controls instead of ~22). All static actions (Vorschau, Editor, Download, NFO exportieren, HI entfernen, Common Fixes, Timing, Restore) live in the per-pill `⋯` dropdown, so the row stays readable when an episode has many languages or modifier variants.

### Fixed
- **Atomic swap-rename for `/tools/process/undo`** — Restore previously did a destructive `move(bak → active)`, overwriting the post-process active sidecar with no way to redo. The endpoint now performs a 3-step atomic swap (`active → tmp`, `bak → active`, `tmp → bak`) using `os.replace`, with rollback on failure. The `.bak` file then holds the prior active state, so a second undo is a free re-undo with no data loss. When no active sidecar exists, falls back to a single rename.

### Changed
- **Removed redundant "Untertitel bearbeiten" from episode action row** — The legacy stand-alone Edit-link picked the first sidecar by deterministic order and duplicated the per-pill `Editor` action that now lives in every sidecar's `⋯` dropdown. Dropping the redundant link removes a confusing hot-spot from the episode header.

## [0.79.0-beta] - 2026-05-01

### Added
- **Subtitle backup (`.bak`) lifecycle** — Full management for the `.bak.srt`/`.bak.ass` files left behind by HI removal, common-fixes, and credit-removal in `subtitle_processor.apply_mods`. Backups no longer leak into the active sidecar list, a new `old_subtitle_baks` cleanup rule purges orphans (no parent video AND no active sub) immediately and TTL-aged backups after `subtitle_bak_retention_days` (default 30d). New `GET/POST /api/v1/library/subtitle-backups[/cleanup]` endpoints expose the same data to the UI.
- **Subtitle modifier badges** — Series and movie views now render small `HI`/`FORCED`/`SDH`/`CC` badges next to language sidecars so the user can see at a glance which variants exist for each track. The unmodified sidecar is always preferred as the "primary" entry.

### Changed
- **Single source-of-truth filename parser** — `subtitle_filename.py` replaces the per-call regexes that previously parsed sidecar names in `dedup_engine` and `scan_subtitle_sidecars`. The new suffix-stripper correctly handles nested modifiers like `ep.en.hi.bak.srt` (previously parsed as language="bak").

## [0.78.0-beta] - 2026-05-01

### Added
- **Auto-extract now keeps only wanted languages** — The scheduler-driven embedded-subtitle extraction (drained every ~2 min for items in the Wanted list) now extracts every text-based subtitle stream the container offers and trashes any sidecar whose language is not in the active profile's `target_languages` (plus `source_language` when auto-translation is enabled). Previously it only picked one "best" stream and never cleaned up non-target sidecars, so users with `wanted_auto_extract=true` saw the bare one-stream behaviour even though their profile said "keep de+en, trash the rest". The auto path and the UI Batch-Probe action now share a single `services.embedded_extractor` pipeline. Trash semantics are recoverable: both the container backup and trashed sidecars land under `remux_trash_dir` (`.sublarr/trash`), nothing is hard-deleted.

## [0.77.3-beta] - 2026-05-01

### Fixed
- **Path-traversal in `/api/v1/remux/backups/{restore,delete}`** — Both endpoints called `is_safe_path` with the arguments reversed, so the gate asked "is the trash dir inside the user-supplied path?" instead of the other way round. With `backup_path=/` (or any prefix of a trash dir) the check passed, then `os.replace("/", video_path)` would attempt to move the entire filesystem root. Switched all four sites to the standard `is_safe_path(candidate, base)` order, matching every other call in the codebase.
- **Symlink bypass in `/tools/video-sync` / `/tools/auto-sync` / `/tools/auto-sync/bulk`** — Manual `os.path.abspath().startswith(media_prefix)` checks did not resolve symlinks, so a symlinked file inside `media_path` that targeted `/etc/passwd` would pass the gate. All three endpoints now use `is_safe_path` (which calls `realpath`), and `auto-sync/bulk` additionally validates Sonarr-supplied paths so a compromised Sonarr can't advertise paths outside the configured library root.
- **Media-server PUT clobbered stored secrets** — `GET /mediaservers/instances` masks `api_key` / `token` / `password` as `***abcd`; the `PUT` endpoint used to write that masked string back as the new secret. The endpoint now detects the mask format and re-merges with the previously stored value so a UI round-trip no longer destroys credentials.
- **Media-server SSRF surface** — `url` field on both `/mediaservers/test` and `PUT /mediaservers/instances` now goes through `validate_service_url`, rejecting `file://`, `ftp://`, link-local IPs, and cloud-metadata IPs at the boundary.
- **Media-server arbitrary kwargs into server class** — `cls(**config)` accepted any JSON keys; `/mediaservers/test` now whitelists kwargs against the type's declared `config_fields[].key` set so callers cannot smuggle debug or admin attributes into the constructor.
- **Media-server limits** — 10/min Flask-Limiter cap on `/mediaservers/test`; cap of 32 instances per `PUT`.
- **`/api/v1/search?limit=abc` 500 → graceful fallback** — Route did `int(request.args.get("limit", 20))` without try/except; switched to `type=int` (silently coerces invalid input back to the default) and added a `max(1, ...)` floor so negative limits don't drift into SQLite "limit -5" territory.
- **`/search/rebuild-index` rate-limited** — Index rebuild walks every series/episode/subtitle row; now capped at 3/min in addition to authentication.

## [0.77.2-beta] - 2026-05-01

### Fixed
- **Notifications — filters + quiet hours actually applied** — Filter rules and quiet-hours blocks were read from settings but the gate functions returned the unfiltered result; both now short-circuit delivery as configured.
- **Backup — auto-backup settings wired into scheduler** — `backup_auto_enabled`, `backup_auto_interval_hours`, `backup_auto_retention_count`, `backup_auto_destination` were ignored by `start_backup_scheduler`; the scheduler now reads all four and runs the configured cadence.
- **Wanted scanner — no longer relaunches on every settings save** — Each save spawned an unscheduled daemon that bypassed slow-mode and backlog-reserve gating.
- **Whisper — four silent gaps** — Enabled toggle now honoured at the queue boundary; orphan jobs are DELETEd; the breaker no longer holds stale state across restarts; a `Semaphore(0)` deadlock on shutdown is gone.
- **Subtitle Tools — `/tools/convert` path-traversal gap** — Endpoint now goes through `is_safe_path` before touching the filesystem.
- **Cleanup — two path-traversal holes + 367 LOC orphan code dropped** — `/cleanup/non-target-subs` no longer accepts a body `media_path` override that bypasses the security gate.
- **Translation — `translation_enabled` flag now respected** — Six endpoints read the flag for responses but never gated submission; the flag is now enforced before queueing.
- **Marketplace — installed plugins actually load** — ZIP installs landed at `<name>/provider.py` but the loader only scanned the top level; loader now walks the package directory and DB sync mirrors uninstall.
- **Blacklist — Plan B3 hash dimension wired in** — The hash-blacklist code was implemented but unreachable; SHA-256 now computed and inserted on every successful download.
- **Integrations export — last secret-leak gaps closed** — JSON export keyword-only mask leaked Discord/Slack tokens, DB/Redis DSN, instance api_keys; mask now consults the canonical secret list.
- **Profiles + glossary + presets — four hardening fixes** — Cross-DB UNIQUE detection, TSV CSV-injection guard on import, type coercion on profile fields, bulk-import row cap.
- **API keys — three hardening fixes** — ZIP-bomb guard on `/import`, 400 instead of 500 on bad-shape config, CSV row cap.
- **System logs / support export — drifted secret mask** — DB DSN, Apprise URLs, `*_instances_json` were leaking through the support-export path; replaced with the canonical mask.
- **Authentication — `/auth/bootstrap` api_key leak** — With `ui_auth` disabled and `api_key` set, the endpoint returned the key. Bootstrap now returns the safe shape.
- **Onboarding — non-string profile crashes `/system/setup/complete`** — Non-dict / non-string payloads triggered an unhashable `TypeError` → 500; endpoint now returns a clean 400.
- **Health / diagnostics — auth-exempt endpoints rate-limited** — `/health` and `/update` were unauthenticated and uncapped; both now have rate caps and `/health` no longer leaks detail when `api_key` is unset.
- **Scoring — empty fansub group entries** — `"" in some_string` is True, so an empty preferred/excluded entry matched every release; entries are now filtered before comparison.
- **Activity / history — search events visible + indexed PK ordering** — `VALID_EVENT_TYPES` was missing `"search"` so `?type=search` returned 400 even though rows existed; `ORDER BY` now uses the indexed primary key `id DESC` instead of a dropped index.
- **Subtitle providers — `/providers/health` envelope mismatch** — Backend returned `{providers: [...]}` but frontend declared `Record<name, {circuit_state, rate_limited}>`; the StatusBar throttled warning and ProvidersCollectionView health rail were dead. Types and consumers now match the real backend shape.
- **Scheduler — manual run-now overlap silently dropped** — When a manual `/run-now` collided with a scheduled tick, the per-job lock returned without writing history, leaving "Run Now" toasts for executions that never happened. The collision now records a `skipped_overlap` row.
- **Dashboard / stats — `success_rate` + `downloads_today`** — StatusStripe's success-rate widget rendered "—" forever and the today widget rendered "+0" forever; the repo never set either field. `/stats` now returns both.
- **Library views — series-detail score lookups under SQLAlchemy 2.x** — Three subtitle/wanted lookups built `?`-placeholder queries with positional lists, which SQLAlchemy 2.x rejects on every backend; debug-level catch-alls hid the failure. Migrated to `text() + bindparam(expanding=True)` and promoted catches to WARN.
- **Audit follow-ups: rate-limits + pagination + scheduler init-pause** — `/providers/test/<provider>` and scheduler admin endpoints (run-now / pause / resume / PATCH / reset-default) get Flask-Limiter caps; pagination guards clamp `page>=1` and `per_page<=200` so `?page=0` no longer returns SQLite garbage / Postgres 500; `pause`/`resume` returns 503 `SchedulerInitialisingError` during the brief startup-paused window instead of a misleading 409.
- **Audit follow-ups: rerank throttle + budget refund + multi-key fallthrough** — `/rerank` defaults `force=false` so the 1h throttle is respected; `ProviderBudgetManager.refund()` accepts `key_id` and decrements the per-key counter; providers without a `rate_limits` ClassVar but with pool rows now consult `KeySelector.pick()` instead of falling through to singleton creds.
- **Audit follow-ups: `/library` mixed-mode + path-based extras filter** — Standalone fallback augments per-side instead of all-or-nothing, so Sonarr-managed series + standalone-scanned movies no longer drop the standalone half. Title-blacklist replaced with a path-segment heuristic — real movies titled "Sample" kept; sidecar files inside Sample/, Trailer/, Featurette/ folders filtered out.

### Tests
- +9 regression tests across the audit cycle: stats summary (`downloads_today` / `success_rate`), `/providers/health` envelope shape, scheduler `skipped_overlap` on overlap, subtitle-score expanding-bindparams query, mixed-mode standalone fallback, path-based extras filter (3 cases).

## [0.77.1-beta] - 2026-04-29

### Fixed
- **Orphan webhook settings page** — `WebhooksPage.tsx` was unreachable duplicate code; the same content already lived inline inside the rendered `SystemHooksPage`. Extracted that section into a shared `WebhooksSection` component, deleted the orphan, migrated its test.
- **Webhook pipeline died silently on uncaught exceptions** — The daemon thread spawned by `_spawn_pipeline` had no top-level error handling, so import errors / DB failures / SocketIO crashes silently killed the worker and the UI never learned the pipeline aborted. Added a wrapping try/except that logs the traceback and emits a new `webhook_failed` SocketIO event so the frontend can react.

### Changed
- **Per-route rate limit on incoming webhooks** — Sonarr / Radarr / Jellyfin webhook endpoints now enforce `30 requests/minute` per source IP. A misconfigured Sonarr hot-loop (or a leaked API key) would otherwise spawn unbounded daemon threads, each sleeping for the full `webhook_delay_minutes`. 30/min comfortably absorbs legitimate traffic on heavy libraries while killing pathological loops.

### Tests
- Webhook test that mocked `threading.Thread` globally now patches the spawn helper directly instead — the global `Thread` patch collided with `flask_limiter`'s use of `threading.Timer` for in-memory expiry.

## [0.77.0-beta] - 2026-04-29

### Added
- **Standalone Folder Manager in Connections** — Enable toggle, watched-folder list, add/edit/delete actions, and a per-folder scan trigger now live directly in Settings → Connections → Standalone-Modus. Previously the toggle and folder list lived in an orphan tab that was never rendered, leaving standalone mode unconfigurable through the UI.
- **Per-folder scan trigger** — A new `▶` button on each watched folder runs a one-off scan of just that folder via `POST /api/v1/standalone/folders/<id>/scan`, instead of forcing a full library sweep.

### Changed
- **Standalone scan interval is now scheduler-driven** — A new `standalone_scan` APScheduler job replaces the previous threading-based interval. Setting `standalone_scan_interval_hours = 0` pauses the job cleanly without leaking timers.
- **Live reload on folder/config changes** — Adding, editing, or deleting a watched folder reloads the StandaloneManager immediately; saving any `standalone_*` / `sonarr_*` / `radarr_*` setting reconfigures the watcher and reschedules the scan job in place. No server restart needed for either path.
- **Symlink paths are normalised on save** — POSTing or PATCHing a watched folder now stores the canonical `realpath`, so symlink/junction targets are recorded consistently regardless of which alias the user typed.
- **Better series root detection** — The scanner now uses common-parent detection instead of `os.path.dirname`, so season-foldered shows pin to the series directory rather than to a season subfolder.

### Fixed
- **`scan_series` actually rescans the series** — The manager-level fallback no longer hits a broken `hasattr` branch; both the API and the manager call the real `StandaloneScanner.scan_series` implementation.
- **`last_scan_at` is always stamped** — The timestamp now updates on both the empty-folder early-return and the end of a normal scan, so the UI reflects scan activity even when nothing changed.
- **Empty default-profile `target_languages` logged** — The scanner emits a warning instead of silently skipping language seeding when the default profile has no target languages configured.
- **`standalone_skip_extras` default mismatch** — The frontend toggle default is now aligned with the backend default (true), so first-load no longer shows the toggle as OFF before any save has happened.

### Tests
- +6 backend tests for the picklable scheduler tick, hot-reload of the StandaloneManager, and the `update_watched_folder_last_scan` repository wrapper.
- +3 backend tests for `realpath` normalisation, the new `scan_series` return shape, and folder hot-reload triggers on CRUD.
- +3 backend tests for the empty-profile warning and `last_scan_at` stamping on both empty and populated folders.
- Frontend `ConnectionsSettings.test.tsx` extended with `useApi` hook mocks for the folder manager.

### Internal
- CI release gate is now RC-aware (prevents accidental `:latest`/`:stable`/`X.Y.Z` publication when an RC build is in flight).
- **i18n cleanup (caught in RC UAT)** — `connections.standalone.desc_auto`/`desc_inactive` no longer point users to the now-deleted `Advanced → Library Sources` tab; they now refer to the folder manager rendered directly below the description.

## [0.76.9-beta] - 2026-04-28

### Fixed
- **`Sprachen & Profile` leaking into EN-mode Settings sidebar** — `SettingsNav.tsx` resolves `t('settings.nav.languages', 'Sprachen & Profile')` for the Subtitles → Languages & Profiles entry. The 0.76.4 i18n full-coverage pass added 19 of the 20 nav keys used by the component but missed this specific one, so EN users saw the German inline-default fallback between otherwise-translated siblings. Adds `settings.nav.languages` to both `en/common.json` ("Languages & Profiles") and `de/common.json` ("Sprachen & Profile"). Caught during post-deploy Playwright UAT against Cardinal.

## [0.76.8-beta] - 2026-04-28

### Changed
- **Faster wanted-search ticks on large libraries** — Two N+1 query hot paths now use single batched queries: the per-series wanted-items lookup used by the min-attempts prefix in every wanted-search tick (`WantedRepository.get_wanted_by_series_bulk`), and the per-provider account-pool fetch behind `GET /api/v1/system/budget` (`ProviderAccountPoolRepository.get_enabled_grouped`). Both collapse from one-query-per-X to one-query-total; no behaviour change, just better scaling on large libraries and provider-pool counts.

### Fixed
- **Caplog test pollution from Alembic env.py** — `backend/db/migrations/env.py` now passes `disable_existing_loggers=False` to `fileConfig()`. Previously the default `True` silently disabled pytest's caplog handler for every test that ran alphabetically after a migration test, masking nine assertions in the full suite. Pure CI hygiene — no runtime impact.
- **Three V1 test-suite gaps** — Collapsed a nested `with` in `test_new_providers_batch2.py` (Ruff SIM117), added `PUT /api/v1/language-profiles/assign-bulk` to the route-safety guard, wrapped `SchedulerPage.test.tsx` in `QueryClientProvider`. Full backend suite now 4546 passed, 4 skipped, 0 failed.

### Docs
- **20 settings gaps closed in the Wiki** — `wiki_audit_settings.py` now reports 212/212 fields documented (was 192/212). Coverage added for the V1 budget manager, v0.71 embedded-SDH gating + foreign-track cleanup, Phase A4 translation context window, the Subtitle Automation queue, and wanted-search pacing. New `Settings → Scheduler & Automation` page in both EN and DE locales. Fixed `providers.md` prose typo: "16 native" → "22 native" (29 total stays correct).

## [0.76.7-beta] - 2026-04-27

### Fixed
- **Slow-mode bypass in wanted search filter** — Items that exhausted `wanted_max_search_attempts` should re-enter the search rotation roughly once every 30 days via the `no_result_slow` slow-mode contract that `record_search_outcome` already sets, but the eligibility filter `_filter_eligible` kept the hard `search_count < max` cap and silently dropped them. The filter now honours items at or above the cap when their `failure_kind == 'no_result_slow'` AND their `retry_after` window has elapsed; other failure kinds (provider_error etc.) still respect the cap. A new Alembic migration `f3d8e9c2a4b1` retroactively promotes legacy frozen items (search_count >= 3, failure_kind NULL, retry_after NULL) into the slow-mode contract, spreading the retry instants over the next 30 days via `id % 30` so the resurrected items don't all hit the providers in one tick. 2032 stuck items on Cardinal will rejoin the rotation. Eleven new tests pin the contract on both the legacy and adaptive paths.

## [0.76.6-beta] - 2026-04-26

### Changed
- **Profiles & Overrides UI rolled back.** The new dedicated Profiles & Overrides settings page has been removed in favor of the previous Language Profiles tab under Settings → Subtitles → Languages. The per-series and per-movie profile selectors as well as bulk profile assignment in the Library remain intact. The backend overrides API and database schema are kept untouched, so the feature can be revisited with a redesigned UI later without another migration.

## [0.76.5-beta] - 2026-04-26

### Fixed
- **i18n full-coverage pass.** A static audit caught 111 keys referenced by code but never defined in any locale file. 9 of them leaked raw keys to the UI in EN+DE (the FirstRun wizard's `language_step.*` and `automation_step.*` labels) and are now fully localized in `onboarding.json`. The other 102 fallback-pattern keys (English fallback that never translated to German) are now defined in en + de across `common`, `settings`, `library`, `statistics`, and `activity` namespaces — covers `common.{close, cancel, save, saving, loading}`, `status.scanning`, `cleanup_detail.*`, the entire `settings.X.Y` description / summary tree (providers / hooks / notifications.quietHours / system / translation / subtitles.fansubPreferences / automation.pipeline), `series_settings_panel.cleanup_*`, chart titles, and more. EN/DE parity verified at 100% across all 10 namespace files (2611 defined keys total).

## [0.76.4-beta] - 2026-04-26

### Fixed
- **Mojibake repair in en/de UI strings** — the Trash page expand/collapse arrows now show ▼ / ▲ instead of `â–¼` / `â–²`. Same root cause fixed for the horizontal-ellipsis (…), em-dash (—), right-arrow (→), and the math `≥` glyph in 7 strings per language.
- **Wanted page no longer leaks raw i18n keys** — the `wanted` and `wanted_extra` namespaces never existed in `activity.json`. 47 wanted.* keys + 3 wanted_extra.* keys added in en + de so column headers, status labels, action buttons, and the legend localize correctly.
- **Settings sidebar finally honours the language switcher** — 19 missing `settings.nav.*` keys plus `settings.categories.profiles.title` were falling through to inline German fallbacks. Defined the full set in en + de so labels like "App & Oberfläche", "Bereinigung", and "Untertitel-Automation" properly translate.
- **Activity sidebar label** — was "Translations" in EN, confusing because the page is multi-tab (Queue / Translations / History / Blacklist). Renamed to "Activity" to match the page's own title.
- **`wanted_search_complete` event** is now registered in `events.catalog` so the recurring `emit_event called with unknown event` warning in prod logs goes away and the SocketIO bridge propagates the event to connected clients.
- **Bottom-nav "99+" badge no longer overlaps adjacent items** — re-anchored the Wanted-tab badge to the icon corner via `left-full -translate-x-1/2`, with `max-w-[28px]` and `pointer-events-none` so it can't bleed into the next slot or steal taps.
- **Default profile renamed in production DB** from "Standart" → "Standard". One-shot SQL fix on Cardinal; fresh installs already used "Default" so no seed change needed.

## [0.76.3-beta] - 2026-04-26

### Fixed
- **Profiles & Overrides — Global default and Profile selections now show their settings.** A regression in the empty-state guard hid the detail panel whenever no series or movie had explicit overrides yet, even though Global and Profile scopes always have settings to view and edit. The "No overrides yet" hint is now a small banner above the detail panel rather than a panel-replacement.

### Removed
- **Empty Languages settings page** (`/settings/subtitles/languages`). The page rendered a blank shell since the 0.73 inheritance refactor moved language profiles + per-language defaults to `/settings/profiles`. Sidebar entry "Sprachen & Profile" is gone, the Cmd+K search index drops the orphan, and `/settings/subtitles/languages` now redirects to `/settings/profiles` so any external bookmark still lands somewhere useful.

## [0.76.2-beta] - 2026-04-26

### Added
- **Section TOC navigation on every migrated Settings page** — sticky right-side navigation jumps between sections inside General, About, Automation, Connections, Notifications, Translation, Providers, Subtitles (Scoring/Format/Automation), Hooks, System Hooks, and System.
- **New `/settings/system/diagnostics` sub-page** — observability + maintenance tools (Log Viewer, Disk Monitoring, Cache Management, Integrations, Migration) split out from the main System page so each side stays focused. Cross-link on `/settings/system` points to it.
- **Tooltips on truncated tree items** in Profiles & Overrides — long series/movie/profile names are now readable on hover.

### Changed
- **15 Settings pages migrated to the template scaffold** — every major Settings page now uses one of the three Codex-blessed layouts (FormLayout with section TOC, CollectionLayout for master-detail lists, or RulesLayout for inheritance pages). The right-side TOC enforces a 6-section cap per page; pages that exceed it are split into sub-pages (System, Translation).
- **EN copy in Profiles & Overrides clarified** — "Remove overrides" reads cleaner than the prior "Remove from overrides", confirm text disambiguates series-vs-movie, empty-state mentions both.
- **Dead Events & Hooks redirect deleted from `/settings/system`** — was a stub left over from a Q1 reorganization that just linked to `/settings/notifications`. The actual events have always lived there.

### Tests
- Settings page test mocks upgraded to real-i18n lookup so titleKey-based assertions resolve through the actual `en/settings.json` instead of returning raw keys.

## [0.76.1-beta] - 2026-04-26

### Fixed
- **Series and movies created via the `Subtitle settings →` button no longer show as `#<id>` placeholders in the Profiles & Overrides tree.** They previously had no row in `search_series` / `wanted_items` / `standalone_series`, so the title-lookup fell through to a placeholder. The endpoint now consults a cached Sonarr `/api/v3/series` map (and Radarr `/api/v3/movie` for movies) for any eligible-but-titleless ID — one HTTP call per Arr instance per 5 min, errors swallowed silently so reachability problems never break the tree. Same fallback applied to `/resolved/series/<id>` and `/resolved/movie/<id>` detail-pane headers.

## [0.76.0-beta] - 2026-04-26

### Added
- **Bulk LanguageProfile assignment in the Library page (Phase C).** The Library table and grid now support multi-select via checkboxes; once one or more series are selected, a sticky toolbar appears with a profile dropdown ("Set profile…") that bulk-assigns the chosen profile to every selected item in one round-trip. Selection resets automatically when switching between the Series and Movies tabs. Backend: new `PUT /api/v1/language-profiles/assign-bulk` endpoint (`{type, arr_ids, profile_id}` → `{assigned, failed[]}`) loops the existing single-assign helper so the client can surface partial failures. Reuses the existing `selectedSeries` state already in place from the batch-search flow — no parallel selection model.
- **Tab-switch clears bulk selection** so the Series-tab IDs don't leak into a Movies-bulk-action.

### Changed
- **Library batch-search error path** now surfaces a toast instead of `console.error`-only, matching the rest of the file's UX style.

## [0.75.0-beta] - 2026-04-26

### Added
- **LanguageProfile selector on every Series and Movie detail page (Phase B).** The previously read-only profile pill in `SeriesSettingsPanel` is now an interactive `<select>` dropdown listing every configured language profile (the default profile is suffixed with ★). Picking a different profile fires `PUT /api/v1/language-profiles/assign` and the page refetches. The Phase A `Subtitle settings` card on `MovieDetailPage` gains the same selector above the navigation button. Backend now exposes `profile_id` alongside `profile_name` in both the standalone-series and Sonarr-managed series API responses, and in the movie detail response.

### Changed
- **`useAssignProfile` invalidations widened** so the source page actually re-renders after a profile change (previously only the `/scopes` tree refetched, leaving the dropdown out-of-sync until a manual reload).

## [0.74.0-beta] - 2026-04-26

### Changed
- **Profiles & Overrides UX inverted: SeriesDetail and MovieDetail are now the entry-point for creating per-series/movie overrides.** Previously `/settings/profiles` listed every series Sublarr knew about (~288 on a typical install) which made the tree noisy and the "where do I configure?" answer unclear. Now the page only shows series and movies that have been explicitly added — either via a profile assignment or via a settings row created from the new entry-point. Each SeriesDetail page gains a `Subtitle settings →` button (in `SeriesSettingsPanel`); each MovieDetail page gains a matching card-button. Clicking it idempotently POSTs `/api/v1/profiles-overrides/<type>/<id>/create-override` and navigates to the Settings page with `?scope=<type>:<id>&from=/library/series/<id>` (or `/movies/<id>`). The Settings page renders a `← Back to <name>` link at the top of the detail pane when `from` is present.
- **`/api/v1/profiles-overrides/scopes` filtered to explicit overrides only.** Series IDs now come exclusively from `series_settings` rows and `series_language_profiles` mappings (not `search_series`, `wanted_items` or `standalone_series`); same for movies. Title lookup still uses the broader cache so display names are pretty.

### Added
- **`POST /api/v1/profiles-overrides/<type>/<id>/create-override`** — idempotent. Inserts an empty `series_settings` / `movie_settings` row so the scope appears in the tree without setting any values.
- **`DELETE /api/v1/profiles-overrides/<type>/<id>`** — drops the entire settings row (the inverse of create-override). Surfaced in the UI as the new `Remove series from overrides` button at the footer of the detail pane (alongside the existing `Reset all overrides` which only NULLs the override columns but keeps the row).
- **Empty-state hint** on `/settings/profiles` when no series/movies have explicit overrides yet — guides the user to open a Library entry and use the new entry-point.
- **Centralised navigation helpers** in `frontend/src/lib/routes.ts` (`profilesScopeUrl`, `seriesDetailUrl`, `movieDetailUrl`) so future Settings-route restructuring touches one file.

### Deferred to Phase B / C (separate releases)
- LanguageProfile selector inside SeriesDetail / MovieDetail ("which profile does this series use").
- Bulk profile-assignment in the Library / Movies list (multi-select toolbar action).

## [0.73.2-beta] - 2026-04-26

### Fixed
- **Clicking a series in the Profiles & Overrides tree 404'd.** The `/resolved/series/<id>` endpoint required a `SeriesLanguageProfile` mapping or a `SeriesSettings` row to consider a series "known", but `/scopes` (after the 0.73.1 fix) lists every series that exists in `search_series`, `wanted_items` or `standalone_series` even without a mapping or settings row — so the tree showed series you couldn't open. Both `/resolved/series/<id>` and `/resolved/movie/<id>` now check the same broader source set as `/scopes` and look up titles from `search_series` / `standalone_series` / `standalone_movies` instead of the non-existent master tables.

## [0.73.1-beta] - 2026-04-26

### Fixed
- **Profiles & Overrides scope tree was empty.** `GET /api/v1/profiles-overrides/scopes` queried a non-existent `series` / `movies` master table and silently returned an empty list, so the new page only showed Global + Profile nodes — every Series/Movie scope was unreachable. Sublarr does not own that table (Sonarr/Radarr do), so the endpoint now aggregates series and movie IDs from `search_series`, `standalone_series` / `standalone_movies`, `wanted_items`, `series_settings` / `movie_settings` and the profile-mapping tables, falling back to `#<id>` when no cached title is available.
- **"overridden" pill made no sense at Global scope.** Every row at the Global scope was tagged `overridden`, which is contradictory — Global is the default, not an override. The `InheritanceRow` primitive now supports five honest states (`default`, `set`, `inherited`, `overridden`, `n/a`) and the Profiles & Overrides detail pane picks the right one per (scope, field): Global rows are tagged `default`, profile-only fields show `set here` instead of `overridden`, and series-only fields viewed at Profile scope are tagged `n/a` and greyed out (no Override button).

## [0.73.0-beta] - 2026-04-26

### Added
- **Profiles & Overrides Settings page.** New top-level `/settings/profiles` route renders the Codex Template C (RulesLayout) scope tree (Global → LanguageProfile → Series/Movie). Browse what each setting resolves to at every scope, override per-series and per-movie inline. Twelve inheritable settings are exposed: `cleanup_foreign_tracks`, `forced_preference`, `hi_preference`, `forced_scoring`, `target_languages`, `cutoff_language`, `must_contain`, `must_not_contain`, `audio_exclude_languages`, `preferred_audio_track_index`, `priority_override` and `min_attempts_per_day`.
- **Per-movie override table.** New `movie_settings` table mirrors `series_settings` (minus the anime-specific `absolute_order`). Movies can now override the same twelve fields as series — previously only Sonarr-managed series had any overrides.
- **Eight new `series_settings` override columns.** `forced_preference_override`, `hi_preference_override`, `forced_scoring_override`, `target_languages_override`, `cutoff_language_override`, `must_contain_override`, `must_not_contain_override`, `audio_exclude_languages_override`. NULL means inherit from the assigned LanguageProfile (which inherits from the global config).
- **`/api/v1/profiles-overrides/` blueprint.** Eight endpoints: `GET /scopes` (full tree), `GET /resolved/<type>/<id>` (4 variants for global/profile/series/movie), `PATCH /series/<id>` and `PATCH /movie/<id>` to set or clear an override, plus matching `POST .../reset` endpoints to wipe all overrides at once. PATCH bodies are Pydantic-validated against per-field whitelists (enums, ISO-2 language codes, JSON arrays).
- **Settings template trio complete.** General is now the FormLayout reference, Providers the CollectionLayout reference, Profiles & Overrides the RulesLayout reference. Three Codex layout templates plus shared primitives (InheritanceRow, BudgetBar, ApiKeyField, ConnectionTest, HealthRail, TriStateToggle) are ready for every future Settings page migration via the Hybrid-Ratchet rule (any new or touched page MUST use a template).

### Changed
- **General Settings → FormLayout.** Refactored as the first Template B reference page with section anchors and scroll-spy navigation. No behaviour change.
- **Providers Settings → CollectionLayout.** Master-list of providers on the left, inline detail editor on the right, optional health rail derived from `useProviderHealth`. Replaces the legacy tile-grid + modal-on-click flow. Drag-drop reorder still works; selection is URL-addressable via `?id=`. Global provider tuning (Marketplace, Anti-Captcha, Cache, Download Limits, Engine) keeps its existing layout below the new collection view for now.
- **Profile CRUD absorbed into the new page.** Add/Edit/Delete profile actions live in the scope-tree header menu of the Profiles & Overrides page. The old standalone `/language-profiles` route 301-redirects to `/settings/profiles`, and the `LanguageProfilesTab` inside Subtitles-Settings has been removed.

### Fixed
- **Latent crash on providers without `config_fields`.** Defensive null-fallback added to the new inline provider editor; the bug was masked by the legacy modal-on-click pattern, but matters now that the inline detail renders on every page-load.

### Tests
- 36 new backend tests across resolver, schemas, routes, models and migration files.
- ~24 new frontend tests across hooks, primitives, widgets and the new page.

## [0.72.0-beta] - 2026-04-24

### Added
- **Per-series foreign-track cleanup override.** The Series Settings Panel now exposes a three-state toggle (Inherit / Always / Never) for the `cleanup_foreign_tracks` policy. Inherit follows the global default from Settings → Subtitle Automation; Always/Never force the per-series behavior. The 'Inherit' label also shows the resolved effective state ('Inherit (on)' / 'Inherit (off)') so users see what the global default currently produces without having to leave the page. Backed by a new tri-state validator on `PATCH /api/v1/series/<id>/settings` that strictly rejects non-boolean values (including integer coercions).
- **Series-detail API surfaces the cleanup policy.** `GET /api/v1/library/series/<id>` now returns two new fields: `cleanup_foreign_tracks_override` (the raw `SeriesSettings` column value — `true`/`false`/`null` meaning inherit) and `cleanup_foreign_tracks_effective` (the resolved policy after applying the global default via `services.foreign_track_cleanup.should_cleanup_foreign_tracks`). Works for both Sonarr-managed and standalone-library series.

### Fixed
- **Dashboard StatusStripe no longer shows 'Paused' 99% of the time.** Previously the stripe label used a 2-state boolean (`is_scanning || is_searching`), so the brief scan/search windows flipped to 'Active' and the rest of the time showed 'Paused' — which users read as 'automation is disabled'. Replaced with a 3-state machine (`active` / `idle` / `paused`) that reads the real `wanted_scanner` + `wanted_search` scheduler-job state. 'Idle' is the new honest label for 'armed, waiting for next run' — shown with `var(--text-muted)` grey. 'Paused' is now reserved for the genuine case where both jobs are manually paused — shown with `var(--warning)` yellow to signal a deliberate user action. The real-time running state keeps the green pulse. New i18n keys: `statusStripe.idle` ('READY' / 'BEREIT'), plus a screen-reader-friendly `aria-live='polite'` region and `aria-label` with the full state.

### Tests
- +15 new tests (4 pytest for series-detail response shape, 6 pytest + 6 RTL for the per-series cleanup override, 3 RTL for the SubtitleAutomationPage status card that shipped in 0.71.0, 6 RTL for the 3-state StatusStripe logic).

## [0.71.1-beta] - 2026-04-24

### Fixed
- **Subtitle Automation migration is now idempotent.** The 0.71.0 `subtitle_automation_schema` Alembic migration used unguarded `CREATE TABLE` / `ADD COLUMN` statements that failed on re-runs against a partially-upgraded database. Added `IF NOT EXISTS` guards on table creation plus column-existence checks via `inspector.get_columns()` before the `ALTER TABLE ... ADD COLUMN` so the migration can be re-applied safely.
- **Wanted-scanner soft-timeout false alarms on large libraries.** Full library scans on ~3000-item libraries routinely run 30+ min and tripped the 600 s monitoring timeout even though the scan itself completed successfully (observed 2026-04-24 on prod: full scan completed in 2246 s with +4 added, ~2967 updated, -10 removed — but `scheduler_job_runs` recorded a spurious `timeout` status 27 min earlier). The `wanted_scanner` job timeout has been raised from 600 s to 3600 s. No functional change to the scan itself — this only stops the monitoring layer from flagging successful long scans as failures.

## [0.71.0-beta] - 2026-04-21

### Added
- **Subtitle Automation — unified pipeline for embedded extract, SDH, and cleanup.** New Settings → Automation → Subtitle Automation page exposes a master toggle plus granular sub-toggles for the drain worker, SDH source tolerance, and foreign-track cleanup. When enabled, the scanner enqueues newly-discovered embedded tracks into a new persistent `subtitle_automation_queue` table; the drain worker (registered as APScheduler job `subtitle_automation`, default cadence 2 min, configurable) pulls rows and extracts embedded subtitles into sidecars with exponential backoff on failure (5m → 15m → 1h → 6h → 24h, capped). `FileNotFoundError` treated as terminal failure (no retry). Live status card shows queue counts (`pending/running/failed/done`), last run, last error, and a one-click Run-now button.
- **Persistent drain queue with atomic claim.** New `SubtitleAutomationQueueRepository` exposes `enqueue` (idempotent by `wanted_item_id`; re-enqueue of a `done` row resets to `pending`), `claim_next` (optimistic-lock transition to `running`, works on both SQLite and Postgres without dialect-specific SQL), `mark_done`, `mark_failed(error, next_retry_at)`, and `get_counts`.
- **SDH source tolerance.** `is_sdh_stream` helper in `ass_probe.py` detects SDH/CC/HI via word-boundary regex on track titles plus the ffprobe `disposition.hearing_impaired` flag. `EmbeddedSubtitlesProvider.search` applies a configurable score penalty (default 5) so a non-SDH track wins a tie while SDH remains a valid source by default — necessary because Marvel/Disney rips ship English only as SDH. `embedded_allow_sdh=False` drops SDH tracks from the candidate pool entirely.
- **Foreign-track cleanup helper.** New `remux.remove_foreign_subtitle_streams` strips subtitle streams whose language is not in the target-language set after a successful target-language extraction. Uses the existing `remove_subtitle_streams` path so backups-to-trash semantics are preserved — nothing is hard-deleted. Opt-in globally (`cleanup_foreign_tracks_default`, default off) with per-series override (`SeriesSettings.cleanup_foreign_tracks`, nullable). `cleanup_foreign_tracks_keep_und` preserves `language=und` tracks when cleanup runs.
- **Status + run-now API.** `GET /api/v1/wanted/automation/status` returns the dashboard payload. `POST /api/v1/wanted/automation/run-now` triggers a synchronous drain (max 25 items per call). Master-toggle-off returns `status="disabled"` rather than a 500.
- **Standalone series display alignment.** `_get_standalone_series_detail` now merges `wanted_items.existing_sub` (`embedded_srt` / `embedded_ass`) as a fallback when the filesystem sidecar is absent, mirroring the Sonarr path. Standalone series with only embedded tracks no longer render red pills for languages that already exist in the container.

### Changed
- **Scanner auto-extract routes through the new queue when automation is enabled.** `_WantedScanSourcesMixin._maybe_auto_extract` now routes through `subtitle_automation_queue` when `subtitle_automation_enabled` is on and the target language can be resolved; falls back to the legacy synchronous inline-extract path (gated by `wanted_auto_extract`) when the master toggle is off, the lookup fails, or enqueue raises. Scanner stays fast — enqueue is O(1) and drain happens asynchronously.
- **7 new config keys** exposed via the ScanningSettings grouped view (so `/api/v1/config` reads/writes work without per-key plumbing): `subtitle_automation_enabled` (false), `subtitle_automation_queue_enabled` (true), `subtitle_automation_drain_interval_minutes` (2), `embedded_allow_sdh` (true), `embedded_sdh_penalty` (5), `cleanup_foreign_tracks_default` (false), `cleanup_foreign_tracks_keep_und` (false). All respect the `SUBLARR_` env-var prefix.

### Migration
- `a1b1c1d1e1f1` — adds nullable `series_settings.cleanup_foreign_tracks` (`NULL` = inherit global default) and creates the new `subtitle_automation_queue` table with UNIQUE(`wanted_item_id`) and composite index `(state, next_retry_at)` for drain lookups. PG-tolerant with `IF NOT EXISTS` on the added column.

### Tests
- 89 new tests across 8 test modules (TDD, one file per phase): schema (10), config (11), queue repository (13), drain runner + scheduler (21), scanner enqueue wiring (6), SDH tolerance (12), foreign-track cleanup (9), status API (5), standalone display (2).

## [0.70.4-beta] - 2026-04-20

### Fixed
- **Plan A3 follow-up — Ollama CJK-hallucination retry reintroduced.** The A1 LLMBackend consolidation dropped Ollama's CJK-specific retry. Qwen2.5 and similar multilingual LLMs occasionally drift into Chinese characters when translating between non-CJK languages. `OllamaBackend._verify_line_count` now overrides the base-class retry to add a post-line-count CJK scan via `has_cjk_hallucination()`. On detection, one retry fires with `is_retry=True` (strict prompt). Retry result accepted if clean; otherwise keep original as best-effort — a partially-tainted translation is more useful than failing the job outright. Token counters sum across both attempts regardless of outcome. 3 new tests.
- **i18n batches 1–9 reconstruction — 29 corrupted function signatures restored + 50+ missing useTranslation hooks wired.** A bug in the batch-i18n tooling overwrote component signatures with `\x01  const { t } = useTranslation(...)` lines, breaking `vite build` on master. Reconstruction restores the overwritten signatures (preserving the legitimate string-wrapping work), places hooks correctly inside function bodies, removes duplicate declarations, and fixes a handful of rules-of-hooks violations (useTranslation called inside map/useEffect/conditional). Missing `useTranslation` imports added to 4 files. Test setup (`src/test/setup.ts`) now imports `@/i18n` so render assertions resolve real locale values. Build, tsc, and ESLint now green; frontend suite 837/839 (2 pre-existing SchedulerPage failures unrelated).

## [0.70.3-beta] - 2026-04-20

### Fixed
- **Plan A3 follow-up — Claude cache-token pricing correctly bills at 0.1× for reads and 1.25× for writes.** Previously `cache_read_input_tokens` was summed into `tokens_in` and billed at the full input rate, overstating costs by up to 10× when Anthropic's prompt-cache discount applied. Now `LLMResponse` carries `cache_read_tokens` + `cache_write_tokens` separately, and `calculate_llm_cost_micro_usd()` bills them at 0.1× (90% read discount) and 1.25× (write premium) relative to the fresh-input rate — exactly matching Anthropic's pricing. Non-caching backends are unaffected (defaults of 0 on both new fields). 4 new cost-tracker tests pin the arithmetic including a realistic 10k-cached-token scenario.

### Non-issues / closed follow-ups
- **Plan A4 Ollama context-windowing** — already correctly skipped by design (V8/V9 fine-tune prompt format is fixed; lookback/lookahead would drift from training distribution). No change needed.
- **Plan A4 OpenAI-Compat context-windowing** — already supports lookback/lookahead (prepends to user prompt). No change needed.

## [0.70.2-beta] - 2026-04-20

### Fixed
- **Plan A1 follow-up — TranslationMemory `backend` column fully wired.** The A1 `translation_events` migration added a `backend` column to the existing `translation_memory` table but the ORM model never exposed it, and the backend filter on `POST /api/v1/translation/memory/purge` had been dropped. Now: `TranslationMemory.backend` is a `Mapped[str | None]` column; `store_translation_cache()` accepts a `backend=` kwarg at every layer (repository, `db.translation` wrapper, `translator/cache.py::_store_translations_in_cache`, `translator/manager.py` passes `result.backend_name`); purge endpoint accepts a `"backend"` filter in the request body. 3 new tests cover field persistence, None default, upsert updating backend.

## [0.70.1-beta] - 2026-04-20

### Fixed
- **Plan B6 follow-up — Post-processing ops are now actually configurable.** B6 shipped the curated-ops pipeline with 8 ops, but per-op config (webhook URL, Discord webhook URL, Plex/Emby/Jellyfin base_url + token/api_key) was not yet wired — every configurable op failed at runtime with "not configured". Each op now declares a `config_schema` (field name, label, type, required, default). Config is stored in `config_entries` keyed as `post_processing.op.<op_id>.<field>`. The pipeline calls `_configure_op_instance()` before `execute()` to populate the op's attributes from the DB. New API endpoints `GET/PUT /api/v1/post-processing/ops/<op_id>/config` with password-field masking on GET. Frontend Settings → Post-Processing tab gains a per-op config form. 35 new backend tests + 37 regression tests green.

## [0.70.0-beta] - 2026-04-19

### Added
- **Plan B Phase 7 — Multi-engine sync orchestrator** — New `backend/services/sync_engines/` package with `BaseSyncEngine` ABC + `SyncOrchestrator` fallback chain + per-engine timeout + sanity threshold (60 s default). Existing ffsubsync + alass logic refactored into named engine classes (`FfsubsyncEngine`, `AlassEngine`); legacy `sync_with_ffsubsync` / `sync_with_alass` functions preserved unchanged for backward compat with CLI + existing routes (dict shape + `shift_ms` key stay stable). New `sync_job_runs` audit table records every orchestrated engine attempt (engine, status, offset_ms, duration_ms, subtitle_path, video_path, reason, created_at) — queryable via `/api/v1/sync/runs`. New Settings → Sync Engines informational tab shows engine availability + sanity threshold. Opens the door for dropping in new engines (nanosync, LLM-assisted) without changing the orchestrator. 16 new backend tests + 68 regression tests green.

### Changed — Plan B scope notes
- **B7 engines scope reduced** — Spec listed 4 engines (ffsubsync, alass, nanosync, LLM-assisted). `nanosync` and LLM-assisted sync require research-grade algorithm development; B7 ships the architecture + the 2 existing engines refactored into the pattern. Future phases can drop in new engines without touching the orchestrator.
- **Legacy sync-function routes not migrated** — The HTTP routes `/tools/auto-sync` + `/video-sync` still call the legacy `sync_with_ffsubsync` / `sync_with_alass` functions directly (bypassing the orchestrator). A follow-up B7.1 can migrate these callers to `get_default_orchestrator().sync(...)` — no urgency since behavior is identical.

### Plan B Progress — COMPLETE 🎉
- Phase B1 — Subliminal vendor foundation: **shipped (0.64.0-beta)**
- Phase B2 — Full Subliminal provider adoption: **shipped (0.65.0-beta)**
- Phase B3 — Granular blacklist: **shipped (0.66.0-beta)** (Subzero merge deferred)
- Phase B4 — Scoring penalty rule pipeline: **shipped (0.67.0-beta)**
- Phase B5 — SRT repair + embedded hardening: **shipped (0.68.0-beta)**
- Phase B6 — Post-processing pipeline: **shipped (0.69.0-beta)**
- Phase B7 — Multi-engine sync orchestrator: **shipped (0.70.0-beta)** — **Plan B complete.**

After this phase, Sublarr has Bazarr-grade delivery quality: 29 subtitle providers, named-class penalty scoring pipeline, SRT repair on every save path, embedded track-selection hardening, post-processing pipeline with 8 ops + opt-in shell escape, multi-engine sync orchestrator with fallback + audit.

## [0.69.0-beta] - 2026-04-19

### Added
- **Plan B Phase 6 — Post-processing pipeline** — New package `backend/post_processing/` firing on three save triggers (`after_download`, `after_translate`, `after_sync`). Eight built-in ops: `strip_html`, `remove_bom`, `convert_encoding`, `webhook` (SSRF-protected via `validate_service_url`), `discord_notify`, `plex_refresh`, `emby_refresh`, `jellyfin_refresh`. Opt-in shell escape hatch behind `SUBLARR_ALLOW_SHELL_SCRIPTS=true` env flag — shlex-quoted substitution, 30-second timeout, PATH-only env, stdout+stderr captured to audit. New `post_processing_runs` audit table (alembic migration) records every pipeline run with per-op outcome + duration. Pipeline runs on a dedicated 2-worker thread pool so request handlers aren't blocked. New Settings → Post-Processing tab. Endpoints at `/api/v1/post-processing/{ops,config,runs}`. 40 new backend tests.

### Plan B Progress
- Phase B6 — Post-processing pipeline: **shipped**

## [0.68.0-beta] - 2026-04-19

### Added
- **Plan B Phase 5 — Subtitle repair + embedded track-selection** — New `backend/subtitle_repair.py` module with pure repair functions that run on every save path (provider download via `save_subtitle()`, embedded extract, post-translate save in SRT/ASS flows). Five defect classes handled: UTF-8 BOM at file start; wrong newline encoding (CRLFCRLF, lone CR); invalid millisecond decimals in SRT timestamps (e.g. `00:00:01,4` → `00:00:01,400`); overlapping cues (clamps earlier cue's end to next start minus 1ms, drops if clamp produces zero-duration); encoding mis-detection (Windows-1252 mislabeled UTF-8 recovered via chardet fallback). Embedded-extraction now ranks candidate tracks by `(language, forced, HI)` flags — forced query boosts forced tracks (+15) and penalizes mismatches (-5); HI-preferred boosts SDH/CC tracks (+10); HI-excluded kills them (-999). Opt-outable via new `enable_subtitle_repair=True` setting. 11 new backend tests + 182 regression tests green.

### Plan B Progress
- Phase B5 — SRT repair + embedded hardening: **shipped**

## [0.67.0-beta] - 2026-04-19

### Added
- **Plan B Phase 4 — Scoring penalty rule pipeline** — Introduced a named-class `PenaltyRule` pipeline into subtitle scoring. 15 rules total: 10 ports of existing Sublarr behaviour (release_group / source / audio_codec / resolution / video_codec match; ASS format bonus; HI + forced preferences prefer / exclude-or-only kills) + 5 new Bazarr-equivalent opt-in rules (loose release-group substring match; source-hierarchy penalty for WEB-DL-for-BluRay-request; year off-by-one tolerance; codec-upgrade mismatch penalty; machine-translation penalty). Weights persist in `scoring_weights` via a new `score_type="penalty_rule"` discriminator with default-preserving merge. New opt-in rules default to weight=0 so existing scoring output is unchanged on deploy — operators toggle rules in Settings → Scoring → Penalty Rules. Exposes `/api/v1/scoring/penalty-rules` (GET + PUT per rule). 26 new backend tests + 85 regression tests green.

### Changed — Plan B scope note
- **B4 rescoped from "~30 rules" to 15 rules** — Sublarr's existing `compute_score()` already implemented most Bazarr-equivalent matching behaviour via the EPISODE_SCORES / MOVIE_SCORES weight maps. The real gap was naming + introspection + a handful of missing edge-case rules (codec-upgrade detection, source hierarchy, loose release-group matching, MT penalty, year off-by-one). The 15 shipped rules cover that gap honestly.

### Plan B Progress
- Phase B4 — Scoring penalty rule pipeline: **shipped**

## [0.66.0-beta] - 2026-04-19

### Added
- **Plan B Phase 3 — Granular blacklist (per-provider + file-hash)** — Extended the subtitle blacklist with a `file_hash` (VARCHAR(64)) dimension so retries can be suppressed for "any subtitle with hash H from provider Y", catching re-uploaded duplicates in addition to the existing per-subtitle-ID path. Alembic migration `9e36be515063` adds the column + partial UNIQUE index `(provider_name, file_hash) WHERE file_hash IS NOT NULL`. Repository gains `is_blacklisted_by_hash()` and an extended `is_blacklisted(provider, subtitle_id=None, file_hash=None)` accepting either discriminator. API POST accepts + returns `file_hash`; Blacklist page in Settings shows a truncated Hash column with full-hash tooltip. EN+DE i18n updated. 8 new tests green, no regression in existing blacklist tests.

### Changed — Plan B scope note
- **B3 Subzero selective merge deferred** — Cherry-picking 3-5 providers from the `subliminal_patch` fork (argenteam, assrt, subdivx, wizdom, etc.) proved deeper than the spec estimated: those providers inherit from Subzero-patched base classes, requiring either vendoring the entire monkey-patch set or porting each provider to vanilla Subliminal's `Provider` interface. With 29 providers already registered after B2 (comfortably past Bazarr's core set), the Subzero cherry-pick is deferred; it can re-open as a post-Plan-B follow-up if operators request the language-niche coverage (Spanish/Hungarian/Hebrew/Greek).

### Plan B Progress
- Phase B3 — Granular blacklist: **shipped** (Subzero merge deferred)

## [0.65.0-beta] - 2026-04-19

### Added
- **Plan B Phase 2 — Full Subliminal provider adoption** — Registered the remaining 6 Subliminal providers via the B1 adapter: `addic7ed_subliminal`, `gestdown_subliminal`, `napiprojekt_subliminal`, `opensubtitlescom_subliminal`, `podnapisi_subliminal`, `tvsubtitles_subliminal`. Two are net-new to Sublarr (napiprojekt, opensubtitlescom REST API), four are alternative Subliminal-flavor implementations of existing native providers (addic7ed, gestdown, podnapisi, tvsubtitles). Provider count: 17 → 23. 13 new parametrized tests green. Scope note: vanilla Subliminal 2.2.0 vendors 7 providers (not the ~20 the Plan B spec estimated — that number was Bazarr post-Subzero). The "≥35 providers after Plan B" target depends on B3's Subzero selective merge.

### Plan B Progress
- Phase B2 — Full Subliminal provider adoption: **shipped**

## [0.64.0-beta] - 2026-04-19

### Added
- **Plan B Phase 1 — Subliminal vendor foundation** — Vendored Subliminal 2.2.0 and babelfish 0.6.1 into `backend/providers/_vendor/`. Added `SubliminalProviderAdapter` shim that wraps any Subliminal provider as a native Sublarr `SubtitleProvider`, converting between Sublarr's `VideoQuery` / `SubtitleResult` dataclasses and Subliminal's `Video` / `Subtitle` types. Registered `opensubtitles_subliminal` as the pilot flavor (XML-RPC, distinct from Sublarr's native `opensubtitles_fetch` REST implementation). New pip deps: `chardet`, `dogpile.cache`, `pysrt`, `stevedore`. 17 new tests green. First step toward Bazarr-grade provider coverage — the remaining ~19 Subliminal providers come online in Phase B2.

### Plan B Progress
- Phase B1 — Subliminal vendor foundation: **shipped**

## [0.63.0-beta] - 2026-04-19

### Added — 4 new translation backends (Lingarr parity reached)
- **Mistral** — LLM via OpenAI-compat endpoint `api.mistral.ai`. Default model `mistral-large-latest` at $2.00/$6.00 per 1M tokens; `mistral-small-latest` as cheaper alternative at $0.20/$0.60.
- **OpenAI ChatGPT (native)** — LLM via OpenAI's official endpoint. Default `gpt-4o-mini` at $0.15/$0.60 per 1M tokens; `gpt-4o` at $2.50/$10.00. Distinct from the existing `openai_compat` backend (which accepts any OpenAI-compatible base URL) — ChatGPT is the opinionated "just use OpenAI" default.
- **Azure Translator** — char-priced REST API at `api.cognitive.microsofttranslator.com`. $10/1M characters. Config fields: `api_key` + `region` (default `westeurope`). Batch-friendly, no LLM prompt overhead.
- **MyMemory** — free-tier char-priced API with optional `email` field to raise daily quota from 1k → 10k words. Per-line GET requests (no batch endpoint on the server side). Cost always $0.
- **Total backends: 12** — 5 LLM (Ollama, OpenAI-compat, Claude, Gemini, DeepSeek, Mistral, ChatGPT = 7 LLM counting both) + 5 char-priced (DeepL, Google, LibreTranslate, Azure, MyMemory). This reaches Lingarr parity on backend breadth.
- All 4 new backends auto-register with `TranslationManager` via try/except ImportError so missing optional deps don't break startup.

### Tests
- +34 new backend tests (9 Mistral + 9 ChatGPT + 8 Azure + 8 MyMemory).
- Full scheduler + translation suite: 294 tests green.

### Plan A — Translation Platform — COMPLETE
This version completes Plan A's 5-phase roadmap:
- A1 Telemetry foundation (0.59.0-beta)
- A2 Queue Dashboard (0.60.0-beta)
- A3 Claude + Gemini + DeepSeek (0.61.0-beta)
- A4 Context-window pre-chunking (0.62.0-beta)
- A5 Azure + Mistral + MyMemory + ChatGPT (**this version**)

## [0.62.0-beta] - 2026-04-19

### Added
- **Context-aware LLM translation** — New `context_windower` module produces `ContextChunk(lookback, batch, lookahead, batch_start_index)` tuples. When translating subtitles in multiple chunks, the LLM now sees up to 10 surrounding lines **before** and 5 lines **after** its current batch (defaults) as context in the system prompt, with an explicit instruction "do NOT translate or repeat". Resolves pronoun ambiguity ("he said"), terminology drift (character names re-transliterated across batches), and narrative coherence across batch boundaries. Token overhead: ~300 extra input tokens per 50-line batch — acceptable for the quality gain, and free when Anthropic's prompt caching is active.
- **Three new config fields** — `translation_context_enabled` (default `true`), `translation_context_lookback_lines` (default `10`, range 0–50), `translation_context_lookahead_lines` (default `5`, range 0–50).
- **LLMBackend + TranslationBackend accept keyword-only `lookback`/`lookahead`** — threaded through `translate_with_fallback` → `translate_batch` → `_assemble_messages`. Non-LLM backends (DeepL, Google, LibreTranslate) accept but ignore the kwargs; only LLMBackend subclasses (Claude, Gemini, DeepSeek, plus Ollama/OpenAI-compat if their overridden `_assemble_messages` is later updated) actually consume the context.

### Tests
- +15 new tests (12 for context_windower, 3 for translator/manager integration).
- Full suite: 174 tests green, no regressions in existing translation / scheduler tests.

## [0.61.0-beta] - 2026-04-19

### Added
- **Anthropic Claude translation backend** — New `ClaudeBackend` integrates Anthropic's Claude models (sonnet-4-6, opus-4-7, haiku-4-5). Uses the official `anthropic` Python SDK. System prompts are wrapped with `cache_control: {type: "ephemeral"}` to enable Anthropic's prompt-caching feature — for Sublarr's use case (identical system prompt across every batch) this produces a ~90% cost reduction on the system portion of the token bill after the first request warms the cache. Subtitle refusals via `stop_reason=refusal` surface as the standard `ContentFilterError`.
- **Google Gemini translation backend** — New `GeminiBackend` integrates Gemini 2.5 Pro / Flash via REST (no SDK dependency). Converts OpenAI-style messages to Gemini's `systemInstruction` + `contents[].parts[]` shape, passes the API key as `?key=...` query param, and maps `finishReason=SAFETY` to the standard `ContentFilterError`.
- **DeepSeek translation backend** — New `DeepSeekBackend` integrates DeepSeek Chat + Coder models via OpenAI-compatible API. Lowest-cost LLM in the stack at $0.14/$0.28 per 1M tokens (in/out) — useful default for high-volume translation where Claude/Gemini cost becomes significant.
- **Registered out of the box** — All three backends are auto-registered with `TranslationManager` at startup (graceful degradation if the `anthropic` SDK is missing). They appear in **Settings → Translation → Backends** with API-key + model fields; `/api/v1/translation/concurrency` now lists 8 backends (5 LLM + 3 char-priced).

### Tests
- +27 new tests (9 per new backend) covering construction, request shape, response parsing, token counting, content-filter/refusal mapping, auth style, cost calculation, and end-to-end translate_batch via mocked clients.
- Full scheduler + translation suite: 241 tests green.

### Dependencies
- `anthropic>=0.39,<1.0` added to `backend/requirements.txt` (required for `ClaudeBackend`).

## [0.60.0-beta] - 2026-04-19

### Added
- **Live Translation Queue dashboard** — New **Settings → Translation → Queue** page shows active translation jobs with per-batch progress bars, ETA, live cost accrual, and a Cancel button. A "Recent" section lists the last 20 finished jobs from this process's memory with status/duration/cost. Polls every 3 seconds.
- **`QueueState` in-memory tracker** — New thread-safe registry (`backend/translation/queue_state.py`) populated by the translation pipeline as jobs start/progress/finish. Active snapshot includes progress (`done`/`total`/`pct`), ETA (computed from observed lines/second), cost-so-far in micro-USD, and a `cancel_requested` flag. Recent buffer caps at 20 jobs via `deque(maxlen=20)`.
- **Best-effort job cancellation** — `POST /api/v1/translation/queue/<job_id>/cancel` sets a flag that `LLMBackend.translate_batch` checks before acquiring the concurrency slot. In-flight batches are not interrupted (the current API call completes), but subsequent batches are skipped — translation ends with `status="cancelled"` and full partial cost is logged. Returns 202 on first call, 409 on double-cancel, 404 on unknown job.
- **`JobCancelledError` in LLMBackend** — new exception class; `translate_batch` now accepts a `job_id: str | None` parameter and raises `JobCancelledError` if the corresponding `QueueState` entry is cancelled. Event is written with `status="cancelled"` before re-raising.
- **Admin audit logging for cancels** — same `translation_admin_action` pattern as A1's purge/concurrency mutations; `action=cancel-job job_id=<id> actor=<api-key-fp>`.

### Tests
- +16 new backend tests (QueueState tracker + /queue + /cancel routes + LLMBackend cancel integration).
- +3 new frontend component tests for QueueDashboard.
- Full scheduler + translation suite: 246 tests green.

## [0.59.0-beta] - 2026-04-19

### Added
- **Translation Cost & Memory page** — New **Settings → Translation → Cost & Memory** surfaces per-backend cost aggregation (today / 7d / 30d), a per-backend breakdown table with event count, average latency and error rate, and Translation Memory statistics (row count, disk size, 7-day cache hit-rate). Operators can purge TM entries older than N days directly from the page with a confirmation and toast feedback. First phase (A1) of the Lingarr-parity translation-platform roadmap.
- **Per-backend concurrency control** — Each translation backend card now exposes a concurrency slider (1–20 slots) that takes effect immediately. Backend-specific rate-limit or throughput characteristics (OpenAI: higher; MyMemory: 1) can now be tuned per backend without redeploying.
- **Integer micro-USD cost tracking** — Every `translate_batch` call now writes a row to the new `translation_events` table (populated by the `LLMBackend` base class and the `write_translation_event` helper). Costs are stored as integer micro-USD (1 USD = 1,000,000 micro-USD) to avoid float drift across aggregation of millions of events. Price sheet is code-owned (`backend/translation/price_sheet.py`) and covers Claude, Gemini, DeepSeek, OpenAI, Mistral, ChatGPT, plus char-priced DeepL / Google / Azure / LibreTranslate / MyMemory.
- **LLMBackend base class** — New shared base for LLM-based translation backends (`backend/translation/llm_base.py`). Concentrates concurrency acquisition, prompt assembly, line-count retry, cost calculation, and event logging in one place. OllamaBackend and OpenAICompatBackend now inherit from it; subsequent phases (A3) will add Claude / Gemini / DeepSeek on top with ~120 LOC each.
- **Prometheus translation metrics** — `/api/v1/metrics` now exposes `translation_cost_micro_usd_total{backend,status}`, `translation_tokens_total{backend,direction}`, `translation_cache_hits_total{backend}`, `translation_latency_seconds{backend}`, `translation_concurrency_in_use{backend}`, and `translation_concurrency_limit{backend}`.
- **Nightly translation_events retention** — New `translation_events_cleanup` JobSpec runs daily at 03:30 UTC and deletes rows older than `translation_events_retention_days` (default 90, range 7–365). Surfaces on the existing Scheduler page alongside the other 7 cron jobs.
- **Read-only translation admin API** — Three new GET endpoints: `/api/v1/translation/cost`, `/cost/by-backend?window=7d`, `/memory/stats` — plus `POST /memory/purge` and `GET/PATCH /concurrency/<backend>` for mutations. Every mutation writes a `translation_admin_action` audit log line with the API-key fingerprint.

### Tests
- +33 new backend tests (price_sheet, cost_tracker, TranslationEvent model + migration, BackendConcurrency, write_translation_event, LLMBackend base class, retention cron, cost + memory routes).
- +3 frontend component tests for CostMemoryPage.
- Fixed pre-existing Phase 5 scheduler migration test isolation issue caused by new ORM tables (test fixture now drops translation tables before the stamp).
- Full scheduler + translation suite: 233 tests green.

## [0.58.1-beta] - 2026-04-19

### Changed
- **Filesystem watchers now use the shared debouncer utility** — Extracted the `threading.Timer`-based debounce machinery from `PluginFileWatcher` (plugin hot-reload) and `MediaFileWatcher` (standalone media directory scanning) into a new `utils/debouncer.py` module. Provides `DebouncedCallback` (single trailing-edge timer) and `KeyedDebouncedCallback` (per-path independent timers), both with correct cancel-before-reassign semantics and idempotent `shutdown()`. This eliminates the last Timer-leak bug class from Sublarr's codebase and closes the related regression pattern documented in the team's memory.

### Tests
- +13 new tests for the debouncer utility (cancellation, shutdown idempotency, concurrent thread safety across 500 triggers, per-key independence).
- 148/148 scheduler + watcher tests green across all suites.

## [0.58.0-beta] - 2026-04-19

### Changed
- **All recurring background jobs migrated to APScheduler** — The four legacy `threading.Timer`-based schedulers (`cleanup_scheduler`, `upgrade_scheduler`, `anidb_sync`, `wanted_scanner_scheduler`) have been replaced by APScheduler `JobSpec`s registered at startup. The **Settings → System → Scheduler** page now shows all six recurring jobs (`anidb_sync`, `cleanup`, `scheduler_history_cleanup`, `upgrade_scan`, `wanted_scanner`, `wanted_search`), each with its live state, trigger, and run history. Scheduled work now survives container restarts with its next-fire-time intact, and operators can run-now / pause / resume / edit-trigger / reset every one of them from the UI.
- **Legacy scheduler entry points are now thin adapters** — `start_cleanup_scheduler(app, socketio)`, `start_upgrade_scheduler(app)`, and `WantedScanner.start_scheduler(app, socketio)` no longer spawn their own `threading.Timer` chains. When called by the settings-save path, each function now re-applies the current config interval to the corresponding APScheduler job via `modify_trigger`, so operator edits in the existing settings UI continue to work unchanged.
- **System Tasks page continues to work** — thin proxy objects for `get_cleanup_scheduler()` / `get_upgrade_scheduler()` preserve the `is_executing` / `last_run_at` / `next_run_at` / `_running` surface that `routes/system/tasks.py` reads, so the legacy tasks view is unaffected.

### Tests
- 131 scheduler-related tests green (98 Phase 1–3 + 17 upgrade + 11 anidb + 5 wanted_scanner_split). No regressions.

## [0.57.0-beta] - 2026-04-19

### Added
- **Full scheduler control from the UI** — The action buttons on **Settings → System → Scheduler** are now live. Operators can **Run now** (queues a one-shot execution), **Pause** / **Resume** the recurring job, **Edit trigger** (interval or cron editor with a live "next 3 fires" preview), and **Reset** the trigger back to the code default. Every successful action shows a toast notification.
- **Trigger edit modal** — New modal with two tabs (Interval / Cron). Interval editor accepts seconds/minutes/hours. Cron editor offers three modes: Daily (hour + minute), Weekly (day-of-week chips + hour + minute), and Advanced (raw 5-field cron expression). The next 3 fire times are computed client-side via `cron-parser` and updated as the editor's inputs change.
- **Write endpoints for the scheduler API** — `POST /api/v1/scheduler/jobs/<id>/run-now` (202 on success, 409 if a oneshot is already pending), `POST .../pause`, `POST .../resume`, `PATCH /jobs/<id>` with Pydantic-validated trigger payloads (400 on invalid / unreachable cron), `POST .../reset-default`. Every mutation logs a `scheduler_admin_action` line to the app log with the caller's API-key fingerprint for audit purposes.

### Tests
- +18 new tests across the backend write routes, serializer converter, and frontend `TriggerEditModal` component.
- Playwright E2E spec added for the golden-path user flow (render → run now → toast → edit trigger → edited pill → reset).
- Full scheduler test suite now at 98 tests (80 Phase 2 + 18 Phase 3), all green.

## [0.56.0-beta] - 2026-04-19

### Added
- **Scheduler admin page (read-only)** — New **Settings → System → Scheduler** page lists every registered scheduler job with its live state: current trigger, next fire time, last run status + duration, and a 7-day summary of ok/error/timeout/missed/skipped runs. Action buttons (Run now, Pause, Edit trigger, Reset) are visible but disabled with a "Available in Phase 3" tooltip — the API contract is stable, Phase 3 will unlock the buttons.
- **Per-job run history drawer** — Click **History** on any job card to open a right-side drawer showing the last 50 runs, filterable by status (All / OK / Error / Timeout / Missed / Skipped). Failing rows expand inline to show the captured `error_type` + full `error_msg`.
- **Read-only scheduler API** — Three new endpoints under `/api/v1/scheduler/jobs`: `GET /` (list with live state), `GET /<id>` (single job detail or 404), `GET /<id>/runs` (paginated history with `limit`, `offset`, `status` query params). 503 `SchedulerDownError` is returned when the scheduler is not running on the replica. 10-second server-side cache on the 7-day stats query.

### Tests
- +12 new tests across backend route/serializer suites and the `SchedulerPage` component.
- Full scheduler test suite now at 80 tests (68 Phase 1 + 12 Phase 2), all green.

## [0.55.0-beta] - 2026-04-19

### Added
- **APScheduler-backed scheduler infrastructure** — Introduces a new `SublarrScheduler` service alongside the legacy `threading.Timer` schedulers. Persists jobs to a new `apscheduler_jobs` table backed by `SQLAlchemyJobStore`, so scheduled work survives container restarts with its next-fire-time intact. First shippable phase of the V1 competitive-parity Phase 5 roadmap; user-visible scheduler UI and migration of the 6 Timer sites land in the next rollout phases.
- **Scheduler job run history** — New `scheduler_job_runs` table captures per-execution metadata (started/finished timestamps, duration, status, triggered_by, error type/message). Populated by the tick wrapper on happy path and by event listeners on missed / overlapping fires.
- **Automatic history retention** — New `scheduler_history_cleanup` cron job runs nightly at 03:15 UTC and deletes history rows older than `scheduler_history_retention_days` (default 30, range 1–365).
- **Bounded scheduler shutdown** — On SIGTERM, the scheduler waits up to 25 seconds for in-flight ticks before the container exits, leaving 5 seconds of buffer before Docker's 30-second grace period. Abandoned rows are reconciled to `error/InterruptedByShutdown` on the next startup.
- **Single-instance guard** — New `SUBLARR_SCHEDULER_ROLE` env var (default `primary`) gates scheduler startup. Setting it to `disabled` on additional replicas prevents duplicate firing when horizontally scaling.
- **Prometheus scheduler metrics** — `/api/v1/metrics` now exposes `scheduler_job_runs_total{job_id,status}`, `scheduler_job_duration_seconds{job_id}`, and `scheduler_interrupted_runs_total` for dashboards and alerting.

### Tests
- +68 new scheduler tests across 10 test files covering the facade lifecycle, tick wrapper timeout and error paths, event listeners, migration upgrade/downgrade roundtrip, retention, stale-run reconciliation, run-now one-shot handling, and a full end-to-end bootstrap smoke test.

### Docs
- Phase 5 scheduler-hardening design spec and phase-1 implementation plan added under `docs/superpowers/`.

## [0.54.1-beta] - 2026-04-18

### Changed
- **Massive code-quality refactor (Bucket B)** — 65 structural splits across routes, providers, services, repositories, translator, and frontend styling. Major reductions: `app.py` 739→470 LOC via 4 sibling modules; `translator/core.py` 789→287 LOC via `ass_flow` + `srt_flow`; `search_coordinator.search` method 530→~95 LOC via five in-class helpers; `ProviderBudgetManager` split across three mixin modules (counters / pacing-modes / learning); `WantedRepository`, `TranslationRepository`, `StandaloneScanner`, `WantedScanner` decomposed via mixins; all provider adapters (animetosho, legendasdivx, opensubtitles, sonarr_client) extracted parsing helpers; `routes/webhooks.py` converted to blueprint package. Pure structural refactor — no user-visible behavior changes.
- **Frontend styling migration (A1 pilot)** — Library, Wanted, Queue, and Activity pages migrated from inline styles to Tailwind utilities. Visual appearance unchanged.

### Tests
- Fixed `monkeypatch` target in `test_provider_registry` after `ConfigResolvingMixin` extraction.

## [0.54.0-beta] - 2026-04-18

### Changed
- **Internal: `backend/providers/__init__.py` split across 4 sibling modules** — 893 → 399 LOC (55% reduction). `ProviderManager` now inherits `SearchCoordinatorMixin` + `ConfigResolvingMixin` + `StatusReportingMixin`. Provider-class registration moved to `providers/registry.py`; Flask-context singleton (`get_provider_manager`, `invalidate_manager`) moved to `providers/manager_singleton.py`. Public import surface byte-identical for all 53+ callers. `<500 LOC` regression guard added.
- **Internal: `backend/routes/cleanup.py` split into Flask blueprint package** — 1105 → 43 LOC in `routes/cleanup/__init__.py` (96% reduction). Domain submodules: `dedup`, `orphan`, `rules`, `stats`, `preview`. All 17 URL endpoints under `/api/v1/cleanup` unchanged. `<100 LOC` regression guard added. Shared scan/orphan state preserved at package scope for backwards compatibility with direct attribute access from tests.

### Docs
- **Inspiration Backlog I7** — mixin-to-composition refactor trigger documented in beta-roadmap spec (§4). Fires when any `ProviderManager` mixin grows past ~400 LOC; `SearchCoordinatorMixin` at 878 LOC already meets the threshold but is deferred to a dedicated cycle.
- **New plan documents** — `providers-init-split` (6 tasks) and `routes-cleanup-split` (7 tasks) under `docs/superpowers/plans/`.

### Tests
- **26 new characterization tests + 2 LOC regression guards** pinning the public APIs and file-size invariants of the refactored modules. Providers: 17 tests + `<500 LOC` guard. Cleanup: 7 tests + `<100 LOC` guard. Existing test suites (`test_providers_init.py`, `test_routes_cleanup.py`) unchanged — a deliberate check that the public surface is byte-identical.

## [0.53.2-beta] - 2026-04-18

### Fixed
- **Race in `reload_settings`** — Between lock release and return, a concurrent `reload_settings()` call could cause the first caller to receive the second caller's settings instance. Moved the return statement inside the lock. Pre-existing; no observed prod incident.

### Changed
- **Internal: `backend/config.py` split into four modules** — The 846 LOC god-file was reduced to 36 LOC as a pure re-export façade. View classes, the `Settings` Pydantic model, and the singleton accessors now live in `config_views.py`, `config_settings.py`, and `config_singleton.py` respectively. The public import surface is byte-identical for all 60+ callers. A `<600 LOC` regression guard test prevents silent regrowth.

### Docs
- **Discord and Reddit community links** — Added to README and About page.
- **Beta-roadmap and competitive-parity specs** — Strategic planning documents defining the post-Phase-4a direction (code confidence, observability, UX hardening). See `docs/superpowers/specs/2026-04-18-*.md`.

### Tests
- **Config refactor safety net** — 24 new characterization tests plus a regression guard enforcing `backend/config.py < 600 LOC`.

## [0.53.1-beta] - 2026-04-18

### Fixed
- **Dashboard "Providers: degraded (N/22 active)" count mismatch** — `_health_check_providers` passed `len(provider_statuses)` as the denominator, which counted every registered class (including plugins the user hasn't configured). The status line now filters by the `enabled` flag first, so a fully-configured install reads "healthy (10/10 active)" instead of "degraded (10/22 active)". Three regression tests added.

### Added
- **Multi-key pool UI is now actually reachable** — Phase 4a shipped the `KeysList`/`KeyEditDialog` components but didn't mount them anywhere. A new `ProviderKeysPool` wrapper is mounted in the provider-edit modal (Settings → Providers → edit tile), fetching + mutating via react-query and invalidating the dashboard budget widget on save.
- **Series override UI is now reachable** — `SeriesOverrideSettings` mounted in the series detail page as a settings card. Edits persist via `PATCH /api/v1/series/<id>/settings`; a green toast confirms saves.

### Changed
- **Ruff cleanup** — Auto-fixed 3 check violations (UP017, I001, SIM117) and reformatted 6 legacy files (Phase 1 migration, locustfile, sidecar/post-processor/wanted-search tests). Backend `ruff check .` and `ruff format --check .` are now both clean across the entire codebase.

## [0.53.0-beta] - 2026-04-18

### Fixed
- **Rate-limit errors no longer swallowed by 5 providers** — `animetosho`, `subdl`, `titrari`, `opensubtitles`, and `legendasdivx` catch their own network errors in a broad `except Exception`. The first three were swallowing `ProviderRateLimitError` before it could reach the SearchCoordinator, which meant Phase 3's 429-learning never fired for them (prod showed 299+ swallowed animetosho 429s in 3 hours with zero rows in `provider_learned_limits`). They now re-raise `ProviderRateLimitError` and `ProviderAuthError` before the broad except. A parametrised regression test locks this in.
- **Activity → History tabs remount on filter switch** — Clicking "Löschungen" or "Scans" under Aktivität → Verlauf kept showing the previous filter's rows because `ActivityLogTab` read its initial filter from a prop via `useState(defaultFilter)` which only fires on mount. Adding `key={filter}` to the component forces a remount so every sub-filter switch re-initialises the query correctly.
- **Duplicate scanner no longer hides groups past the first page** — The cleanup UI called `useDuplicates()` with the default `per_page=50` and had no pagination, so a prod library with 263 duplicate groups showed only the first 50 — the remaining 213 were invisible and unclickable. Bumped the default to the backend cap (200) and surface a "X of Y duplicate groups" hint plus a warning label when the list is still truncated.
- **Duplicate scanner warns on cross-episode misfiles** — Groups are detected purely by SHA-256 content hash, which flagged legitimately suspicious cases (e.g. `S01E10` and `S02E10` sharing identical content — a misfiled subtitle, not a safe dedup). The backend now marks such groups with `cross_episode=true`; the UI renders an orange "Cross-Episode" badge with a tooltip so users verify before batch-deleting.

### Added
- **V1 API-Budget Scheduler — Phase 4a: Multi-key pools + per-series overrides** — Each provider can now have multiple API keys organised in a pool. The new `KeySelector` picks the key with the most remaining day-budget per call (budget-aware, with a 60s cache and 429 cooldown). Two new columns on `series_settings` let users override a series's scheduling priority (premium/standard/backlog) and guarantee a minimum number of search attempts per day (hard floor that survives the backlog-reserve gate).
- **`/api/v1/system/budget` exposes per-key breakdown** — Response now includes a `keys: [...]` array with per-key `used / limit / last_429_at / last_used_at`. The outer `tier` is the highest enabled key (vip+ > vip > free); `limits` is the sum across all enabled keys so a second VIP key doubles the aggregate day-budget as expected.
- **`/api/v1/providers/<name>/keys` CRUD endpoints** — List/add/update/delete pool rows with duplicate-label conflict handling. A `POST .../test-connection` fires a cheap provider-specific probe (OpenSubtitles, subdl) with 20/min rate-limit and redacted errors.
- **`PATCH /api/v1/series/<id>/settings` endpoint** — Sets `priority_override` (nullable, one of premium/standard/backlog) and `min_attempts_per_day` (0..50), creating the row if missing.
- **Standalone frontend components** — New `KeysList` + `KeyEditDialog` (settings), new `SeriesOverrideSettings` (library). `BudgetWidget` rows now expand on click to show per-key breakdown when a provider has 2+ keys. All covered by Vitest; DE + EN i18n complete. Components are not yet mounted in ProvidersTab / SeriesDetail — UX integration follows in a subsequent commit.

### Changed
- **Scheduler credential injection moved into the worker thread** — Previously the SearchCoordinator mutated the singleton provider's `api_key` attribute before `executor.submit`, which could race between concurrent `search()` calls. Credentials are now injected inside `_search_provider_with_retry` under a per-provider `RLock`, and restored in a `finally` block.
- **`idx_wanted_sonarr_series` re-added** — Phase 4a's LEFT JOIN on `series_settings.sonarr_series_id` needs the index that was dropped in `h1i2j3k4l5m6` back in April.

### Tests
- **`test_phase4a_e2e.py`** — End-to-end integration: two VIP keys double the aggregate day-budget, `min_attempts_per_day=3` guarantees three oldest-searched items per tick, `priority_override=premium` promotes a backlog item to the first rank.
- **`test_provider_rate_limit_propagation.py`** — Parametrised regression across all 5 paid-credential providers.

## [0.52.0-beta] - 2026-04-17

### Added
- **V1 API-Budget Scheduler — Phase 1: Foundation** — New `ProviderBudgetManager` tracks per-provider API usage across three windows (second / hour / day) with in-memory + optional Redis backing. Providers declare their rate limits and tier metadata; OpenSubtitles auto-detects free/VIP/VIP+ from the API. Failed items no longer freeze permanently — split into `no_result`, `provider_error`, and `no_result_slow` kinds with exponential backoff. Scheduled search supports fair / newest-first / weighted order presets.
- **V1 API-Budget Scheduler — Phase 2: User-Facing** — First-run setup wizard walks new installs through profile selection (light / balanced / aggressive / custom). Dashboard shows a per-provider budget widget with live usage bars and reset countdowns, updated in real time via SocketIO. Stretch mode paces the daily quota evenly across 24h so the whole budget isn't burned in the first hour.
- **V1 API-Budget Scheduler — Phase 3: Intelligence** — The scheduler now learns real provider limits by observing 429 responses: `record_429` reduces a learned adjustment factor (floor 0.1) that multiplies into the effective limit; `tick_recovery` ramps the factor back toward 1.0 after 7 clean days. New pacing modes: **burst** front-loads the quota for the first N UTC hours then paces the remainder; **adaptive** distributes the budget proportional to your observed demand histogram over the last 30 days. Item selection is priority-weighted (premium → standard → backlog); backlog items defer to the next tick when any provider exceeds 50% day-usage. `/api/v1/system/budget` now exposes the learned `adjustment_factor`, `consecutive_good_days`, and `last_429_at` per provider.
- **Dashboard learning badge + pacing-mode selector** — The budget widget renders a `-N%` badge when a provider is currently being throttled by the learned factor. Automation settings expose the stretch / burst / adaptive selector and a burst-window input (1–23 hours).

### Fixed
- **Provider rate-limit recovery no longer over-credits good days** — `ramp_recovery` now guards against rapid consecutive calls so multiple ticks within the same 24h window don't inflate the good-day streak.
- **Budget refunded on submit failure** — When a provider search submission fails before hitting the network, the pre-consumed budget is refunded instead of leaking.
- **`db.wanted` facade forwards priority_weighting** — The module-level facade now passes the new kwarg through so explicit overrides from outside the repo layer work.

### Changed
- **Default `wanted_search_max_items_per_run` bumped from 50 to 500** — The previous default was too low to make progress on larger backlogs under the new budget gating.
- **Scheduler operational failures log at `warning`** — `record_429`, `tick_recovery`, the SearchCoordinator hook, and the backlog-reserve gate now surface their failures at the default log level instead of hiding them in debug.

### Tests
- **`test_phase3_e2e.py`** — End-to-end: a 429 storm reduces the factor, 7 clean days ramp it back up by one step. Verifies Tasks 3–5 integrate correctly on a real DB.
- **Raw-SQL fixture repair** — `test_routes_wanted.py` and `test_routes_wanted_extract.py` now include `priority` and `error_count` in raw INSERTs so the Phase 1 migration's NOT NULL constraints don't trip the 32 helper-based tests.

## [0.51.17-beta] - 2026-04-15

### Fixed
- **Manual "Alte Backups" cleanup rule no longer crashes with a DB type error** — `POST /api/v1/cleanup/rules/<id>/run` on an `old_backups` rule raised `DatatypeMismatch: column "files_deleted" is of type integer but expression is of type text[]`. `cleanup_old_backups` returns `{"deleted": [list of paths]}`, but `services/cleanup_rule_runner.execute_rule` passed that list straight into `repo.log_cleanup(files_deleted=...)` where the column is an integer count. The scheduler path in `cleanup_scheduler._execute_cleanup` already converted the list to a count; the manual endpoint did not. Convert via `len(...)` so the manual run reaches the same result path. `bytes_freed` is explicitly 0 because `cleanup_old_backups` does not track file sizes.

## [0.51.16-beta] - 2026-04-15

### Fixed
- **Pin setuptools below 81 to preserve `pkg_resources`** — `0.51.15-beta` pinned `setuptools>=70` to bring back `pkg_resources` for `ffsubsync`/`webrtcvad`, but pip resolved to `setuptools 82` which dropped the `pkg_resources` shim entirely (deprecated since 67.5, removed in 81). Tightened the pin to `setuptools>=70,<81` so `pkg_resources` remains importable.

## [0.51.15-beta] - 2026-04-15

### Fixed
- **Auto-sync no longer crashes on videos without embedded subtitle streams** — `ffsubsync` falls back to `webrtcvad` for voice-activity detection when the reference video has no subtitle track to align against, and `webrtcvad` imports the deprecated `pkg_resources` shim. Python 3.12 base images stopped shipping `setuptools` by default, so the import raised `ModuleNotFoundError: No module named 'pkg_resources'` and the sync job failed. The earlier `0.51.12-beta` smoke test on Rent-a-Girlfriend S05E02 happened to use a video with embedded subtitles and skipped this codepath, masking the bug. Pin `setuptools>=70` in `requirements.txt` so `pkg_resources` is always available.

## [0.51.14-beta] - 2026-04-15

### Fixed
- **Auto-sync, NFO export, and pipeline result now point at the actual saved file** — The wanted-search runner spammed `Auto-sync skipped: subtitle path does not exist on disk` for FateZero, FateApocrypha, To Your Eternity, Zombie Land Saga, and To LOVE-Ru after `0.51.12-beta` started exposing pipeline path mismatches. Root cause: `providers.download_manager.save_subtitle` silently rewrites the file extension when the actual subtitle format does not match the input extension (e.g. caller asked for `.de.ass` but content detection found SRT) and returns the corrected path. Six of seven callers ignored the return value and continued using the stale original path for downstream operations. Capture the returned path at all seven callsites in `wanted_search/process.py`, `wanted_search/post_processor.py`, and `translator/providers.py`. `download_manager.save_subtitle` also now logs a `WARNING` whenever it rewrites an extension so the production frequency is observable.

### Tests
- **Regression coverage for the save_subtitle return-path contract** — New `TestSaveSubtitleReturnPathPropagated` simulates a provider that says ASS but delivers content saved as SRT and asserts the rewritten path reaches `_try_auto_sync` and the response dict. Three existing `TestTryAutoSync` cases now use real `tmp_path` files so they are not silently masked by the `0.51.13-beta` `os.path.isfile` guard.

### Docs
- **Long-term API redesign proposal** — `docs/refactor-proposals/save-subtitle-api-v2.md` describes a keyword-only `dest_dir` / `base_name` signature plus a `SavedSubtitle` dataclass return so the discard-the-return-value misuse pattern becomes structurally impossible.

## [0.51.13-beta] - 2026-04-15

### Fixed
- **Auto-sync skipped cleanly when sidecar is missing** — After shipping `ffsubsync` in `0.51.12-beta`, the wanted-search runner spammed `Auto-sync failed: [Errno 2] No such file or directory` right after startup. Root cause: the post-download pipeline sometimes passes a subtitle path whose file is not on disk (e.g. the pipeline claims a `.de.ass` while only `.de.srt` exists). Previously masked by `SyncUnavailableError` when ffsubsync was absent. `_try_auto_sync` now checks both `subtitle_path` and `video_path` with `os.path.isfile` and logs a `WARNING` (`Auto-sync skipped: ... does not exist`) instead of raising from `shutil.copy2`.

## [0.51.12-beta] - 2026-04-15

### Fixed
- **Auto-sync now actually runs** — `ffsubsync` is bundled into the Docker image. Previously every webhook-triggered download logged `Auto-sync skipped: ffsubsync is not installed` and passed through unaligned; post-processing now aligns downloaded `.de.ass` / `.en.ass` files to the video timeline.

## [0.51.11-beta] - 2026-04-14

### Added
- **Post-extract sidecar cleanup by language profile** — After the batch-probe pipeline extracts subtitles + remuxes the container, it now compares every sidecar file on disk against the item's language profile (`target_languages` plus `source_language` when `wanted_auto_translate` is on). Anything outside that set (e.g. `.jpn.ass` when the profile targets `de` + `en`) is moved into the same trash folder used by the remux backup, not hard-deleted. Unknown / `und` language tags are preserved to avoid destroying data that cannot be classified. Language normalisation via new `normalize_language_code` reverse lookup handles `ger`/`deu`/`german`→`de`, `eng`→`en`, `jpn`→`ja`, etc.
- **Retroactive cleanup endpoint** — New `POST /api/v1/cleanup/non-target-subs` walks the configured `media_path`, unions every profile's `target_languages`, and moves legacy non-target sidecars to trash. Defaults to `{"dry_run": true}` which only counts and samples; actual move requires explicit `{"dry_run": false}`. Aborts when no target languages are configured so an empty profile list can never wipe the whole library.

### Fixed
- **`process_wanted_item` no longer overwrites extracted sidecars** — When the target-language `.ass` (or `.srt` with `upgrade_enabled=false`) already exists next to the video the provider search is skipped, the wanted item is marked `extracted`, and the pipeline returns `status=skipped` with a human-readable reason. Previously Step 1 of the search could save a provider version over a freshly extracted sidecar because the `is_upgrade` gate did not apply to non-upgrade items. SRT satisfaction with `upgrade_enabled=true` still falls through so the SRT→ASS upgrade path keeps working.

## [0.51.10-beta] - 2026-04-14

### Fixed
- **Webhook pipeline now has Flask app context** — The `_webhook_auto_pipeline` thread touches the DB (`get_wanted_items_by_path`, `process_wanted_item`) which requires a Flask-SQLAlchemy app context. The raw `threading.Thread` used so far had none, so every DB call raised `Working outside of application context` and the entire auto-download path failed silently — caught by the outer `try/except` that logged only a bland `search/process failed` warning. A new `_spawn_pipeline()` helper captures `current_app` from the request handler and pushes `app_context()` inside the worker thread; the Sonarr, Radarr, and Jellyfin PlaybackStart handlers all route through it now. This is a pre-existing bug that 0.51.9 surfaced by always calling `process_wanted_item` for every language.

## [0.51.9-beta] - 2026-04-14

### Added
- **Webhook pipeline downloads without translate + iterates all languages** — Previously the Sonarr/Radarr webhook auto-pipeline only downloaded subtitles when `webhook_auto_translate=true` (via `process_wanted_item`) and fell back to search-only when translation was off, which meant users with the common "download yes, Ollama-translate no" config got search results but no files. And `get_wanted_item_by_path` returned a single item per path, so multi-target-language setups (e.g. `de` + `en`) only processed the first language. The pipeline now looks up all wanted items for the imported path via new `get_wanted_items_by_path` and runs `process_wanted_item` on each one, independent of the translation setting. `process_wanted_item` already respects `wanted_auto_translate` internally, so disabled translation continues to skip Steps 2/4/5 (source-lang + translate) while Steps 1+3 (direct target-lang ASS/SRT download) still run. A failure on one language no longer short-circuits the others.

## [0.51.8-beta] - 2026-04-14

### Fixed
- **Index-cleanup migration now completes on Postgres** — The `h1i2j3k4l5m6` migration used `DROP INDEX CONCURRENTLY` inside an `autocommit_block`, which collided with Alembic's default transactional DDL assumption and rolled the entire migration back silently. Switched to plain `DROP INDEX IF EXISTS` inside the normal migration transaction — all target indexes are under 1 MB, so the brief `AccessExclusiveLock` is measured in milliseconds and the cleanup now lands cleanly.
- **Alembic auto-upgrade errors are no longer silent** — The non-fatal wrapper in `app.py` caught every exception but logged only `str(e)`, which is empty for some exception types. That hid the silent migration failure for weeks. Added `exc_info=True` so future migration failures land in the log with the full traceback.

## [0.51.7-beta] - 2026-04-14

### Fixed
- **Alembic chain unstuck** — Migration `g1h2i3j4k5l6_add_subtitle_downloads_indexes` has been silently failing on every prod startup with `relation "idx_subtitle_downloads_downloaded_at" already exists`, because SQLAlchemy `create_all()` already creates that index from the model definition. The non-fatal wrapper swallowed the error but pinned `alembic_version` one step behind the real head, so every later migration (including the 0.51.6 index cleanup) was blocked for weeks without anyone noticing. Rewrote both `CREATE INDEX` calls as raw SQL with `IF NOT EXISTS` so the migration tolerates a pre-existing state and the chain can reach HEAD. This release unblocks the dead-index cleanup from 0.51.6.

## [0.51.6-beta] - 2026-04-14

### Fixed
- **WantedScanner timer leak on settings save** — Every config-UI save was leaking a pair of `threading.Timer` instances because `start_scheduler()` overwrote the timer references without cancelling the previous ones. The old chains kept ticking and produced `Wanted scan already running, skipping` log lines when they eventually fired. `start_scheduler` now cancels the previous timer pair first, and the `_schedule_next_*` helpers also cancel before swapping, so recursive rescheduling stays single-chain.

### Changed
- **Removed 6 unused database indexes** — After two weeks of prod runtime `pg_stat_user_indexes` reported zero scans on six indexes. New migration `h1i2j3k4l5m6` drops them with `DROP INDEX CONCURRENTLY` on PostgreSQL (no write blocking). Removed: `subtitle_hashes.idx_subtitle_hashes_file_path` (100% duplicate of the UNIQUE constraint on the same column), `activity_log.idx_activity_log_event_type`, `activity_log.idx_activity_log_created_at`, `wanted_items.idx_wanted_sonarr_series`, `wanted_items.idx_wanted_radarr_movie`, `subtitle_downloads.idx_subtitle_downloads_path`. Frees ~2 MB of storage and saves index-maintenance cost on every insert/update. `idx_wanted_sonarr_episode` and the trigram GIN indexes on `search_*` tables are kept for existing query paths even though they are currently idle.

## [0.51.5-beta] - 2026-04-14

### Fixed
- **Stream removal after extraction now works end-to-end** — The mkvmerge `--subtitle-tracks` exclusion argument was built as `!3,!4`, which mkvmerge v91+ rejects as an invalid BCP 47 language tag. The correct form is `!3,4` (single `!` at the start of the list). Every subtitle extraction on Cardinal was logging `mkvmerge failed (exit 2)` with an empty reason — subtitles were extracted correctly to `.ass` files but the tracks stayed in the container. Error capture now also falls back to stdout when stderr is empty, because mkvmerge writes hard errors to stdout.
- **Circuit breaker hardening** — Auth and rate-limit errors in provider search methods were caught by generic exception handlers and returned as empty results, preventing the circuit breaker from ever opening. All three layers (download, provider search, coordinator retry loop) now correctly propagate these errors.
- **Orphan scanner false positives** — Episode titles containing dots (e.g. `Mr. Saturday`) were truncated by the language-tag regex, producing false orphan reports. The regex is now anchored to known subtitle extensions (srt/ass/ssa) and accepts modifier suffixes.
- **Wanted-search NULL guard** — `process_wanted_item` no longer crashes with a TypeError when `search_count` is NULL. Items inserted before a later default=0 migration triggered this crash, which in turn caused retry storms that logged identical tracebacks thousands of times at the same millisecond.
- **Unknown API paths return JSON 404** — `/api/v1/*` paths that do not match a registered blueprint now return a proper 404 instead of falling through to the SPA with HTTP 200. Client bugs fail loudly instead of silently.
- **Logging setup is idempotent** — Repeat `create_app()` invocations (tests, reloaders) no longer leak RotatingFileHandler and SocketIOLogHandler instances. Previously each leak multiplied every log record N-fold, producing the same entry at the same millisecond in the log file.
- **Sonarr/Radarr error loop on unconfigured setups** — Instance lists with empty `url` or `api_key` are now dropped at the factory. Previously a client was constructed with empty strings and every scan tick ERROR-logged `Sonarr GET /series failed after 3 attempts`.

### Docs
- **Security reporting** — SECURITY.md now points exclusively to GitHub security advisories; removed the redundant email path.

## [0.51.4-beta] - 2026-04-13

### Fixed
- **Provider errors now fully propagate to circuit breaker** — Auth and rate-limit errors in provider search methods were caught by generic exception handlers and returned as empty results, preventing the circuit breaker from ever opening. All three layers (download, provider search, coordinator retry loop) now correctly propagate these errors.
- **Server rate-limit tracking across threads** — When one search thread receives a 429 from a provider, a shared timestamp is set so all other concurrent threads skip that provider immediately instead of each hitting the same rate limit independently.
- **Timeouts propagated as errors** — Provider timeouts were silently returned as empty results. They now raise ProviderTimeoutError so the circuit breaker counts them as failures.

### Changed
- **Database indexes for subtitle_downloads** — Added indexes on `downloaded_at` and `file_path` columns, eliminating sequential scans on the 7.7M-row table. Batch worker count reduced from 4 to 2 to prevent CPU overload on small containers. Circuit breaker cooldown increased from 60s to 300s.

## [0.51.3-beta] - 2026-04-13

### Fixed
- **Subtitle hash UniqueViolation on concurrent writes** — Replaced check-then-insert with atomic UPSERT (INSERT ... ON CONFLICT DO UPDATE) for the subtitle_hashes table, preventing PendingRollbackError cascades during parallel wanted searches. Includes explicit session rollback in all callers.
- **Circuit breaker not wired into download path** — download_subtitle() now checks allow_request() before each download and records success/failure on the circuit breaker. Applies to all 22+ providers. OpenSubtitles HTTP 406 (quota exhausted) is now raised as ProviderRateLimitError with reset time instead of a generic error.
- **Log viewer entries overlapping** — Replaced fixed 30px row height with dynamic measurement via measureElement, preventing multi-line tracebacks from rendering on top of each other.
- **Status bar missing batch and provider status** — Footer now shows batch extraction/search activity and a throttled provider count with names on hover.

### Tests
- Added 20 integration tests for atomic UPSERT behavior, batch extraction flows, and download manager rollback handling.
- Added 2 StatusBar tests for throttled provider indicator.

## [0.51.2-beta] - 2026-04-12

### Fixed
- **Firefox subtitle rendering** — libass-wasm createTrack crashes in Firefox (ass_read_file returns NULL). Added WebVTT fallback: Firefox now uses native `<track>` elements with ASS→VTT conversion. Chrome/Edge/Safari keep full ASS rendering via SubtitleOctopus.
- **OpenAPI security declarations** — All 286 API routes now have explicit security declarations in the OpenAPI spec. Previously 165 routes appeared public in the spec despite being protected by runtime auth hooks.

### Docs
- **SECURITY.md** — New security policy documenting threat model, 3 pentest rounds (25 findings, all CRITICAL/HIGH resolved), accepted risks, and production security checklist.
- **MIGRATION.md** — New upgrade guide covering beta-to-V1 migration path with version-specific breaking changes and troubleshooting.

### Tests
- **737 new backend tests** — 27 new test files covering routes (standalone, notifications, whisper, webhooks, subtitle processor), services (wanted scanner, video player, cleanup, marketplace, standalone manager, NFO parser, file watcher), translator package (core, manager, jobs, helpers, cache), translation backends (DeepL, Google, LibreTranslate, Ollama, OpenAI), and DB repositories (standalone, hooks, jobs, library, whisper). Added Locust load testing configuration.

## [0.51.1-beta] - 2026-04-12

### Fixed
- **Graceful shutdown** — Background threads (wanted scanner, upgrade scheduler) now stop cleanly on SIGTERM instead of blocking container shutdown for up to 60 seconds.

### Tests
- **Full module coverage achieved** — Added 1,290 new tests across 10 files covering all previously untested modules: forced detection, mediainfo utils, download manager, HTTP session, spell checker, OCR service, retranslation, audio visualizer, OpenAPI spec, translation repository, track routes, and standalone scanner. Backend test suite now at 2,793 passing tests with 100% module coverage.

## [0.51.0-beta] - 2026-04-12

### Added
- **Provider transparency** — The dashboard provider widget now shows real-time status badges: throttled providers display a countdown timer, circuit-breaker-open and auto-disabled providers show their state clearly, and problems sort to the top. The activity queue displays a provider status line during searches (e.g. "5 active · 3 throttled") so users understand why searches are slow instead of seeing a frozen progress bar.

### Fixed
- **Cleanup stats crash** — The cleanup statistics endpoint threw a KeyError because `get_duplicate_groups()` returns `file_size` but `get_disk_stats()` accessed `size`. The key name mismatch caused every `/api/v1/cleanup/stats` request to fail with HTTP 500.

## [0.50.1-beta] - 2026-04-12

### Changed
- **V1 code health: split 10 oversized backend files** — All files exceeding the 800-line project limit have been refactored into focused modules: wanted_scanner_core (1233→627), cleanup routes (1113→928), standalone routes (967→786), profiles routes (964→748), bazarr_migrator (948→576), translator core (926→789), providers init (847→797), subtitles routes (824→785), and api_keys routes (803→796). config.py (812) accepted as declarative exception.
- **Removed 86 completed beta planning documents** — All plan/spec/research/summary files from v0.23–v0.50 deleted; replaced by a single Road to V1 release roadmap spec.

### Fixed
- **6 broken tests repaired** — Remux duration mismatch test updated for widened tolerance (v0.47.7), wanted search dedup collision fixed, CleanupSettings tests aligned with v0.47.3 redesign, SubtitlePresencePills test updated for v0.49.0 pill removal.

## [0.50.0-beta] - 2026-04-11

### Added
- **Settings search (Ctrl+K)** — Spotlight-style modal lets users search all settings pages and individual fields by name or description. Selecting a result navigates to the correct page and highlights the matched field with a 5-second pulsing glow.

### Fixed
- **Duplicate groups crash** — Backend returned `hash`/`path`/`size` keys instead of `content_hash`/`file_path`/`file_size`; the Cleanup page now loads without a TypeError.
- **Settings highlight not firing** — Fixed field matching via `htmlFor` normalisation and a custom-event mechanism for same-page navigation. Added missing `htmlFor` attributes to all Toggle-based FormGroups so every searchable field can be highlighted.
- **Highlight animation invisible** — Replaced broken CSS `@keyframes` (silently ignored by the browser) with JS-driven inline-style transitions, giving a reliable 5-second pulse sequence.

## [0.49.0-beta] - 2026-04-11

### Added
- **Wanted list visual redesign** — Multi-language groups now have a purple left accent border and a darker header row to clearly separate groups. Language tag suffixes (e.g. `[EN]`, `[DE]`) are stripped from titles since the language badge on each sub-row already conveys that information. A status legend showing all six possible states is displayed above the table.

### Fixed
- **"No embedded subtitles" pill hidden when empty** — The "nicht eingebettet" pill and its separator are no longer shown when a video file has no embedded subtitle tracks, reducing visual noise in the Existing column.

## [0.48.0-beta] - 2026-04-11

### Added
- **Wanted: grouped episode rows** — Episodes with multiple target languages now appear as a single row with one language sub-row per language, instead of a separate row for each. The title, S/E number, and "Added" date render once per episode group; the language badge, status, subtitle presence, search count, last-search time, and action buttons appear per language sub-row. Supports any number of target languages (DE + EN + JP etc.).

### Fixed
- **Wanted: search results panel restored** — Clicking a row in the Wanted list now correctly opens the inline search-results expansion panel for that item. The panel was previously disconnected and could never be shown.

## [0.47.7-beta] - 2026-04-11

### Fixed
- **Auto-extract reliability** — Four recurring failures in the embedded subtitle extraction pipeline have been resolved: (1) Duration mismatch false-positives on MKVs with phantom trailing segments are fixed by widening the remux tolerance from ±2 s to max(5 s, 1 % of file duration). (2) Non-UTF-8 bytes in file paths or ffmpeg stderr no longer crash extraction — all subprocess calls now use `errors="replace"`. (3) Race condition where two workers processed the same file concurrently now produces a clear log message instead of a cryptic "expected -1, got 0" error. (4) Default ffmpeg timeout for subtitle extraction raised from 120 s to 300 s, preventing spurious timeouts on large files over NFS.

## [0.47.6-beta] - 2026-04-11

### Fixed
- **Dashboard stats PostgreSQL error** — Fixed a type mismatch where the `upgrade_candidate` column (integer) was compared to a boolean `True`, causing PostgreSQL to throw "operator does not exist: integer = boolean" on every dashboard load. Query now uses `== 1` to match the integer column type.

## [0.47.5-beta] - 2026-04-10

### Fixed
- **Auto-extract item_id is None in batch scan** — When the wanted scanner runs in batch mode, `_commit()` is a no-op and SQLAlchemy never assigns the autoincrement PK until an explicit flush. Added `session.flush()` after `session.add()` so `item.id` is populated before being returned, eliminating the "Wanted item None not found" errors and cascading logging crashes during startup scans.

## [0.47.4-beta] - 2026-04-10

### Fixed
- **Wanted search crashes on startup** — ThreadPoolExecutor worker threads now each receive their own Flask application context. Previously every parallel item search raised "Working outside of application context", causing the startup search to fail for all items silently.
- **Language profiles blocked by duplicate Alembic revision** — A duplicate revision ID (b2c3d4e5f6a7) caused all pending migrations to be skipped on production, which prevented creation of language profiles. The hi_preference migration was renumbered, a merge migration added, and the chain restored.

## [0.47.3-beta] - 2026-04-10

### Changed
- **Cleanup page completely overhauled** — Instead of a rule manager with sidebar, modal, and arbitrarily named rules, there are now 5 fixed operations (Language Filter, Format Upgrade, Orphaned Files, Orphaned DB Entries, Old Backups) as collapsible cards with toggle, inline configuration, and schedule. No more "Create new rule" required.

### Fixed
- **Preview now shows concrete file examples** — The dry run returns up to 20 example files with path, size, and deletion reason (e.g. `lang:ja`), instead of just counts.
- **Cleanup UI fixes** — Fixed dropdown clipping in the language filter, disk widget more compact, layout and save feedback reworked.

## [0.47.2-beta] - 2026-04-10

### Fixed
- **FormGroup dividers in light mode** — The dividers between settings fields used a hardcoded dark color (`rgba(42,46,56,0.5)`) instead of `var(--border)` and were incorrectly colored in light mode.
- **Wanted page: double scrollbar** — `height: calc(100vh - 40px)` ignored the main padding (24 + 60 px), which pushed the table 44 px past the visible area. Corrected to `calc(100vh - 108px)`.
- **Settings nav: insufficient top spacing** — The sticky sidebar started with only 4 px spacing from the top edge. Increased to 16 px.
- **PillTabs: invisible in light mode** — The tab container had no border and visually blended with the page background; border `var(--border)` added.
- **CleanupTab: section content without indentation** — The content of collapsible sections had no `pt-3`, causing it to start directly below the toggle button. Top padding added.
- **Logs page: inconsistent page header** — Raw `<h1>` heading replaced by the canonical `PageHeader` component; height calculation adjusted from `7rem` to `8rem`.

## [0.47.1-beta] - 2026-04-10

### Fixed
- **Wanted scheduler logging** — `scan_all()` now correctly logs `EVENT_SCAN` (was silent before); `search_all()` logs `EVENT_SEARCH` instead of `EVENT_SCAN`, preventing search results from appearing as scan entries in the activity log. Search now also runs on startup by default.
- **Dashboard provider health** — Provider success rate was treated as a 0–100 integer but the API returns a 0–1 decimal; dots and percentages now display correctly.
- **Trash page** — Complete redesign: stats bar with total sizes and retention info, expiry badges color-coded by urgency, delete button for MKV backups, all strings via i18n.
- **Settings navigation** — Removed the tile overview page; settings now open directly on General.
- **Cleanup rules** — Fixed 5 API contract mismatches: `getCleanupRules` now handles `{rules:[…]}` wrapper; `deleteDuplicates` sends correct key `groups`; history normalizes `items→entries`; preview sends `{action:"dedup"}` with correct response mapping; scan status normalizes `running:bool→status:string`. The `old_backups` manual run now actually deletes files instead of just listing them.
- **Cleanup modal** — Redesigned rule-creation dialog with icon button cards, backdrop-close, Enter-to-submit, and X close button.

## [0.47.0-beta] - 2026-04-09

### Added
- **Movie Subtitle Management** — Existing subtitle sidecar files are now displayed on the Movie detail page with a full actions menu (HI removal, common fixes, timing offset).
- **Timing Offset Tool** — The subtitle actions menu now includes a "Shift Timing" option that applies a millisecond offset to any sidecar subtitle file directly from the UI.
- **Forced Scoring per Language Profile** — Language profiles can now specify include / prefer / exclude / only for forced subtitles, wiring directly into the scoring pipeline.
- **Cutoff Language in Profile Editor** — Language profiles now expose the cutoff_language field, allowing per-profile cutoff configuration.
- **74 Language Options** — The language selector was expanded from 20 to 74 supported languages.
- **HI Preference in Profiles** — Language profiles now carry a hearing-impaired preference (prefer / avoid / only) that feeds directly into subtitle scoring.

### Fixed
- **Toggle Revert Bug** — Settings toggles (AniDB, Standalone, Remux) were reverting to OFF immediately after click because of a `=== 'true'` string comparison against boolean values returned by the backend. All affected tabs now use `boolVal()`.
- **Optimistic Toggle Updates** — Config toggles now update the cache immediately on click, so the UI feels instant instead of waiting for the GET refetch.
- **HI/Forced Preference Migration** — Source/target language and HI/forced preference settings were moved from the General page to the Subtitles page where they belong.
- **Advanced Settings Label** — The collapsible advanced section now shows "Advanced Settings" instead of "0 advanced settings" when no count is provided.
- **German locale encoding** — 90 broken UTF-8 sequences (Ã¤, Ãœ, ÃŸ, etc.) in de/common.json were corrected to proper umlauts (ä, Ü, ß, …).

### Changed
- **Settings Information Architecture** — Settings fields were consolidated into their correct sub-pages (ffmpeg_timeout moved to Automation → Search & Scan; format tools section removed).
- **Language Profile Editor** — Translation fields removed from the profile editor; language options deduplicated and expanded.

## [0.46.0-beta] - 2026-04-06

### Added
- **Persistent settings navigation** — All settings pages now have a permanent sidebar navigation (SettingsNav + SettingsShell) that remains visible on every sub-page.

### Fixed
- **Language profiles prominently placed** — Language Profiles are now the first section on the Subtitles page and are immediately visible instead of deeply hidden in a collapsed area.
- **Language profile form fully localized** — All UI strings in the Language Profiles form are now properly translated for both supported languages (Save, Cancel, Target Languages, Profile Name, etc.).
- **Batch-Extract no longer removes subtitles without sidecar** — If extraction produces an empty sidecar file, the embedded subtitle stream is not removed from the MKV. Prevents data loss on failed extraction.

## [0.45.0-beta] - 2026-04-06

### Added
- **Settings redesign — advanced fields system** — FormGroup now supports
  an `advanced` prop that renders an amber "Advanced" badge and tooltip
  instead of an inline hint, reducing visual clutter for power-user options.
  SettingsSection displays a collapsible "N advanced settings" toggle
  when advanced fields are present.
- **LanguagePillSelector component** — Multi-language selection in Language
  Profiles now uses interactive pills with a dropdown, replacing free-text
  comma-separated input. Includes full LANGUAGE_OPTIONS list (20 languages).
- **Dedicated settings sub-pages** — Five settings areas extracted into their
  own routes for cleaner navigation: Post-Processing (`/automation/post-processing`),
  Hooks & Webhooks (`/system/hooks`), Metadata/AniDB (`/connections/metadata`),
  Stream Management/Remux (`/subtitles/stream-management`), and Transcription/Whisper
  (`/providers/transcription`). Old `/settings/hooks` and `/settings/webhooks`
  routes redirect automatically.
- **Settings i18n — hint text and advanced keys** — All settings fields now
  have translated hint/description text. Advanced toggle labels and section
  titles are fully localised in EN and DE.

### Fixed
- **Unused import removed** — Stale `Workflow` import cleaned up from
  AutomationSettings after the Post-Processing extraction.

## [0.44.0-beta] - 2026-04-06

### Added
- **Unified History Tab** — History and activity log merged into a single tab. Sub-filters (Downloads / Extractions / Deletions / Scans) switch between views.
- **Readable subtitle pills in the Wanted section** — Pills now show clear text (e.g. "DE missing", "DE ASS ⬇") instead of cryptic symbols, with explanatory tooltips on hover.

### Fixed
- **Duplicate presets button** — The preset button was rendered twice in the Wanted filter area; one was removed.
- **Filter dropdown transparent** — Popover for "Add filter" and "Presets" had no visible background and did not close when clicking outside; both fixed.
- **Filter field names** — Field labels in the filter dropdown (Status, Type, Subtitle Type, Title) are now correctly translated.
- **Activity tab i18n** — Duplicate JSON key `history` in activity.json was overwriting the filter labels; merged. Second filter bar in ActivityLogTab suppressed when used from UnifiedHistoryTab.
- **Wanted page subtitle** — Page description is now correctly localized via i18n.

## [0.43.0-beta] - 2026-04-06

### Added
- **Full UI localization (i18n)** — All visible strings in the interface have been migrated to the react-i18next system. The language can now be switched between German and English via settings. Covers all pages (Library, Wanted, History, Logs, Plugins, Setup, Settings) and components (BatchActionBar, SpellCheckPanel, SubtitleEditor, Charts, Standalone mode status, Cleanup rules, and many more).

## [0.42.0-beta] - 2026-04-06

### Added
- **Update indicator** — Pulsing amber dot on the Settings icon and a chip (↑ vX.Y.Z) next to the version number in the sidebar when a newer release is available on GitHub. The version number in the StatusBar becomes clickable and opens a popover with a link to GitHub Releases.
- **Logs page** — New route `/logs` with its own sidebar icon (ScrollText) for direct access to backend logs.
- **Full i18n localization** — All Settings pages (General, Automation, Scoring, Backup, AniDB, Cache), the Trash page, and other UI pages (Library, Plugins, Setup, Statistics, etc.) are now fully translatable. Fallback language is German.

## [0.41.8-beta] - 2026-04-05

### Fixed
- **Wanted items removed after download** — Wanted items are now deleted from the database immediately after a subtitle is successfully downloaded (previously they accumulated with `status = "found"` and were never removed). 71 stale entries cleaned up on deploy. The scanner will not re-add items that already have a subtitle file on disk.
- **Dashboard metrics populated** — The total subtitles, average score, and low score stats showed `—` because the `/stats` endpoint never returned these values. Now returns `total_subtitles` (count from `subtitle_downloads`), `average_score` (avg score), and `low_score_count` (upgrade candidates).
- **Activity page: Download history restored** — The `Downloads` tab was showing the empty `ActivityLogTab` (new `activity_log` table) instead of `HistoryPage` (subtitle_downloads). Restored correctly; the `ActivityLogTab` is now its own separate `Activity Log` tab.

## [0.41.6-beta] - 2026-04-05

### Fixed
- **Alembic duplicate revision** — `make_glossary_series_id_nullable` and `add_activity_log` both carried revision ID `e4f5a6b7c8d9`. Renamed `make_glossary_series_id_nullable` to `f2a3b4c5d6e7` and updated the four dependent migrations (`add_fansub_preferences`, `add_chapter_cache`, `add_glossary_metadata`, `add_datetime_to_health_results`). Container startup no longer fails with "Revision is present more than once".

## [0.41.0-beta] - 2026-04-04

### Added
- **Cleanup Rules page** — Dedicated first-class Settings page (`/settings/cleanup`) replacing the old CleanupTab. Rule list sidebar + detail view with 4 rule types: Language Filter (delete sidecars in non-allowed languages), Format Upgrade (delete SRT when ASS exists), Orphan Files (delete subtitle sidecars with no matching video), and DB Cleanup (remove DB entries whose subtitle file no longer exists on disk). Each rule has a name, enabled toggle, and schedule (manual / daily / weekly / after scan). Dry-run preview before executing. `.nfo` files are never touched.
- **`schedule` column on `cleanup_rules`** — New `schedule` column (manual/daily/weekly/after_scan) added via Alembic migration `f0e1d2c3b4a5`; existing rules default to `manual`.
- **Rule executors** — `backend/services/cleanup_executors.py` with pure executor functions for all 4 rule types, supporting `dry_run` mode for preview.
- **`POST /api/v1/cleanup/rules/{id}/preview`** — New dry-run endpoint returning files that would be deleted with estimated MB freed.

## [0.40.0-beta] - 2026-04-04

### Added
- **Subtitle Presence Pills** — The `Vorhanden` column on the Wanted page is replaced by a pill-based `Untertitel` column. A left pill shows the target-language subtitle status (`DE ✗` / `DE SRT ↑` / `DE ↓ ASS`); a right group shows all other embedded subtitle streams in the video file (`EN ↓ ASS`, `+N ▾` overflow dropdown sorted by configured source language). The `↑` upgrade arrow only appears when the upgrade candidate flag is set.
- **`embedded_languages` field** — New `embedded_languages` TEXT column on `wanted_items` (Alembic migration `c6d7e8f9a0b1`). The wanted scanner now probes and stores all non-target embedded subtitle streams at both movie and episode scan sites.
- **`get_all_subtitle_streams()`** — New utility in `ass_utils.py` returning all embedded subtitle streams as `[{lang, format}]`, with optional target-language exclusion and deduplication.

### Changed
- **Wanted column renamed** — i18n key `existing_col` changed from `"Vorhanden"` to `"Untertitel"` (DE) and `"Existing"` to `"Subtitles"` (EN).
- **`upsert_wanted_item` partial-update safety** — `embedded_languages` is no longer overwritten to `[]` by call sites that do not supply the field (episodes route, standalone scanner); existing data is preserved on partial updates.

## [0.39.0-beta] - 2026-04-03

### Added
- **Post-Processing UI** — Toggle and command textarea for `post_processing_enabled` / `post_download_command` added to Settings → Automation → Processing Pipeline; 7 substitution variables supported (`{subtitle_path}`, `{language}`, `{provider}`, `{score}`, `{media_type}`, etc.)
- **Rate limiting on critical routes** — `POST /api/v1/config/import` (5/min), `GET /api/v1/config/export` (30/min), `POST /api/v1/auth/setup` (5/min), `POST /api/v1/auth/change-password` (5/min + 20/hr), `POST /api/v1/providers/search` (20/min)
- **Provider cache metrics** — `sublarr_provider_cache_hits_total` and `sublarr_provider_cache_misses_total` Prometheus counters with `layer=fast/db` label; now increment correctly from two-tier cache path
- **DB performance indexes** — Composite index `(status, retry_after)` on `wanted_items` for scan-loop filter; `language` index on `subtitle_downloads` for provider history queries (Alembic migration `b5c6d7e8f9a0`)
- **Configurable Gestdown retry delay** — `gestdown_retry_delay_s` config field (default `1.0`, env `SUBLARR_GESTDOWN_RETRY_DELAY_S`); replaces hardcoded `time.sleep(1)` on HTTP 423; set to `0` to disable for batch scans
- **OpenAPI docstrings** — All 6 endpoints in `routes/auth_ui.py` and `stream_media()` in `routes/media.py` now have full OpenAPI YAML docstrings with status codes and schemas

### Changed
- **`providers/__init__.py` refactored** — 1404 → 843 LOC; search coordination extracted to `providers/search_coordinator.py` (`SearchCoordinatorMixin`)
- **`wanted_search/process.py` refactored** — 1067 → 695 LOC; post-download logic extracted to `wanted_search/post_processor.py`; score selection to `wanted_search/score_selector.py`
- **Frontend splits** — `ConnectionsSettings.tsx` (938 → 43 LOC), `EventsTab.tsx` (903 → 12 LOC), `api/system.ts` (888 → 20 LOC); all split into domain sub-components with barrel re-exports

### Tests
- **+58 new backend tests** — Route tests for `config`, `mediaservers`, `media`, `blacklist`, `series_audio`; unit tests for `archive_utils` (ZIP bomb/slip) and `anidb_sync` (token parser, XML processor, 409 guard)
- **+6 frontend tests** — `Library.test.tsx` (series/movies tab, view toggle) and `SeriesDetail.test.tsx` (title, season, episode render)
- **`test_security.py` split** — 1159-LOC file split into 4 domain files: `test_security_paths.py`, `test_security_download.py`, `test_security_prompt.py`, `test_security_auth.py`

### Docs
- **Wiki: Post-Processing** — New page `user-guide/post-processing.md` covering variables, examples, behavior limits, troubleshooting
- **Wiki: Circuit Breaker** — New page `user-guide/advanced/circuit-breaker.md` covering state machine, persistence, Prometheus metrics, manual reset
- **Wiki: Ollama Chat API (V9+)** — `user-guide/settings/translation.md` extended with Chat vs. Generate comparison, system prompt / `{series_context}` guide, per-model recommendations

## [0.38.1-beta] - 2026-04-03

### Tests
- **HTTP route tests** — 6 new test files covering `routes/subtitles.py`, `routes/library/`, `routes/wanted/`, `routes/providers.py`, `routes/translate/`, and `bazarr_migrator.py` (Phase 3b test coverage)
- **2 bug fixes via TDD** — `WantedRepository` init call fixed in `routes/wanted/search.py`; `sqlite3.Row.get()` replaced with `dict()` in `bazarr_migrator.py`
- **Flaky time test fixed** — `WantedFailureReason.test.tsx` uses `vi.useFakeTimers()` + frozen timestamp to prevent minute-boundary failures

### Changed
- **Phase 5 refactoring complete** — `wanted_scanner.py` → facade + `wanted_scanner_core.py`; `config.py` → `config_language_data.py` + `config_instances.py` + `config_utils.py`; `AdvancedTab.tsx` → 4 sub-tab components; `Wanted.tsx` → toolbar/filter/row components; `LegacySettings.tsx` reduced to 682 LOC

## [0.38.0-beta] - 2026-04-03

### Security
- **P1 — Provider domain allowlist** — `validate_download_url()` added to `security_utils.py`; all 6 provider download methods now validate URLs against a per-provider domain allowlist before fetching; blocks SSRF via compromised provider responses
- **P2 — Filename sanitization** — `werkzeug.secure_filename()` applied to all provider-supplied filenames before they reach `os.path.splitext` or disk writes; neutralizes path traversal attacks
- **P3 — Prompt injection guard** — subtitle lines and glossary entries are sanitized before LLM prompt construction in `translation/llm_utils.py`; embedded newlines escaped, oversized terms rejected
- **P4 — Magic-byte validation** — downloaded subtitle content validated against expected format signatures (SRT/ASS/VTT); binary payloads rejected before storage
- **P5 — Streaming size cap** — all provider downloads capped at 50 MB via streaming download helper; replaces unbounded `.content` reads
- **F-05 — Webhook signature warning** — `auth.py` now logs a warning when a Sonarr/Radarr webhook arrives without `X-Signature` or `X-Bazarr-Signature` header

### Added
- **Language profile filters API** — `must_contain`, `cutoff`, and `audio_exclude` fields now fully exposed via `GET/PUT /api/v1/language-profiles/:id`; repository serializer and update allowlist updated
- **Video codec scoring** — `video_codec` weight (default 2) added to scoring defaults; `apply_video_codec_bonus()` helper matches codec strings from media metadata
- **Ollama Chat API (V9)** — `use_chat_api` flag in translation config enables Ollama `/api/chat` endpoint alongside legacy `/api/generate`; `series_context` injected as system message for improved translation coherence
- **Circuit breaker state persistence** — breaker open/closed state and failure counters survive restarts via new `circuit_breaker_state` DB table + Alembic migration
- **`@handle_api_error` decorator** — `error_utils.py` provides a reusable decorator for route error handling; applied to cleanup route handlers

### Changed
- **`providers/__init__.py` split** — 1642-line file extracted into `providers/format_validator.py` (magic-byte validation) and `providers/download_manager.py` (streaming download + size cap); all imports backwards-compatible
- **`services/cleanup_scanner.py`** — cleanup business logic extracted from `routes/cleanup.py` (1016 → <400 LOC)
- **`services/standalone_manager.py`** — standalone auto-mode logic extracted from `routes/standalone.py`
- **`frontend/src/api/client.ts` split** — 2151-line file split into 9 domain modules (`core`, `library`, `providers`, `settings`, `system`, `translation`, `wanted`, `health`); backwards-compat re-exports maintained
- **`frontend/src/lib/types.ts` split** — 1301-line file split into 7 domain type files under `frontend/src/types/`; backwards-compat re-exports maintained
- **ROADMAP.md** — updated to reflect v0.37.3 current state; v0.29–v0.37 marked done; v0.38–v0.40 roadmap added
- **`datetime.utcnow()` removed** — all 10 deprecated calls replaced with `datetime.now(UTC)` across `whisper/queue.py`, `nfo_export.py`, and `routes/system/logs.py`

### Removed
- **`providers/whisper_subgen.py`** — dead provider file deleted (replaced by Whisper backend system in v0.35)

### Tests
- **+147 backend tests** — new test files for `routes/cleanup`, `routes/api_keys`, `routes/profiles`, `routes/notifications`, and `whisper/queue`
- **+72 security tests** — `TestValidateDownloadUrl`, `TestFilenameSanitization`, `TestPromptInjectionGuard`, `TestMagicByteValidation`, `TestStreamingCap` appended to `test_security.py`
- **Subtitle health timestamps** — `subtitle_health_results.checked_at` migrated from TEXT to `DateTime(timezone=True)`; in-memory scheduler state uses datetime objects throughout

---

## [0.37.3-beta] - 2026-04-01

### Changed
- **Activity navigation restructure** — "Wanted" promoted to top-level sidebar nav item (alongside Dashboard, Library, Settings); Activity reduced from 5 tabs to 4 clean tabs: Queue, Translations, History, Blacklist
- **Queue tab** — now shows only background batch operations (Wanted Batch Search, Batch Probe, Scanner) with an empty state when idle; translation jobs moved to dedicated Translations tab
- **Translations tab** (new) — shows active and queued translation jobs with live polling; replaces the old "In Progress" tab
- **Badge indicator** — moved from Activity nav item to Wanted nav item (shows count of items still needing subtitles); Translations tab shows badge for active + queued job count

### Removed
- **"Needs Attention" tab** — redundant with the Wanted page (was a filtered view of the same data)
- **"In Progress" tab** — consolidated into the new Translations tab

---

## [0.37.2-beta] - 2026-03-31

### Added
- **AniDB title dump resolver (Tier 4)** — offline `anime-titles.xml.gz` lookup (91 k+ entries, cached 36 h) resolves AniDB ID for standalone anime items even when TVDB/AniList IDs are unknown; enables AnimeTosho to find subtitles for series like "Date A Live" where no external ID is stored

### Fixed
- **AnimeTosho provider** — rewritten with correct two-step API flow (`?show=torrent&id=` to get subtitle attachment list); the old implementation read `files` from the search feed which is no longer included in the AnimeTosho API; result: 72 subtitle results for Date A Live S01E01, 10 for 86: Eighty Six S01E04 (was 0 for both)
- **Provider cache key** — now includes `anidb_id` so a freshly resolved AniDB ID triggers a new provider search instead of returning a stale cache entry
- **Provider search** — fixed occasional hang when a provider thread exceeded its timeout; `ThreadPoolExecutor` is now shut down with `cancel_futures=True` so pending threads do not block the Flask response
- **Vite 8 blank page** — `BUNDLED_DEV` environment variable was not being replaced at build time; switched `manualChunks` from object to function form for rolldown/Vite 8 compatibility
- **Alembic migrations on PostgreSQL** — `env.py` now uses `engine.begin()` to wrap all migration DDL in an explicit transaction; `ALTER COLUMN` for `DateTime` columns now emits `USING` cast clause on PostgreSQL

---

## [0.37.0-beta] - 2026-03-31

### BREAKING CHANGE — Database Migration Required

**All timestamp columns have been migrated from plain TEXT to `DateTime(timezone=True)`.**
The Alembic migration `b0c1d2e3f4a5` reformats stored timestamps from ISO 8601 (`2024-01-15T10:30:00+00:00`) to SQLAlchemy's SQLite format (`2024-01-15 10:30:00`). This runs automatically on startup (`flask db upgrade`). **No manual action required for Docker deployments** — the migration is applied automatically.

Use `scripts/check_datetime_migration.py --db /config/sublarr.db --mode before/after` to verify migration integrity.

### Added
- **ConfirmModal component** — replaces all `window.confirm()` calls with an accessible, styled modal dialog
- **StatisticsRepository** — extracted all statistics queries from route handlers into a dedicated repository
- **`services/retranslation.py`** — business logic for item re-translation extracted from route handlers
- **`scripts/check_datetime_migration.py`** — standalone pre/post migration DB consistency checker (70 columns, 29 tables, row-count snapshot comparison)
- **`useDebounce` hook** — extracted reusable debounce hook into `frontend/src/hooks/useDebounce.ts`
- **`configUtils.ts`** — shared frontend config helpers extracted from settings pages
- **`settingsShared.ts`** — consolidated duplicate `inputStyle` and shared settings UI constants

### Changed
- **TranslationTab refactor** — split 1989-line `TranslationTab.tsx` into 8 focused sub-files under `pages/Settings/translation/` (`TranslationBackendsTab`, `BackendCard`, `PromptPresetsTab`, `GlobalGlossaryPanel`, `TranslationQualitySection`, `TranslationMemorySection`, `OllamaPullSection`, `TemplatePickerModal`)
- **SeriesDetail performance** — episode wanted-items now filtered server-side by `series_id`; eliminates the previous 9999-item full-list fetch
- **`wanted_scanner.py`** moved to `services/wanted_scanner.py` for consistent service-layer placement
- **Session timeout** — now enforced at 8 h by default (was Flask's 31-day default); configurable via `session_timeout_minutes`

### Fixed
- **Security — command injection** — replaced `subprocess(shell=True)` with `shlex.split()` in all subprocess calls
- **Security — IP allowlist** — `allowed_ip_ranges` setting now enforced in `before_request` hook for all non-exempt routes
- **Security — SSRF** — `validate_service_url()` now applied to plugin install URLs and plugin registry fetch
- **Security — webhook auth** — requests are now rejected immediately when no API key is configured
- **Security — path traversal** — `is_safe_path()` added to OCR batch-extract endpoint; corrected reversed argument order in `cleanup_sidecars`
- **Security — health endpoint** — returns HTTP 503 when required services are down (was always 200)
- **`subtitle_processor` route** — removed erroneous `.isoformat()` call when writing to `updated_at` DateTime column
- **Silent error suppression** — replaced bare `except Exception: pass` blocks with `logger.warning()`/`logger.debug()` throughout backend
- **Alembic revision conflict** — resolved duplicate revision ID `a1b2c3d4e5f6`

---

## [0.36.4-beta] - 2026-03-30

### Fixed
- **Health status — Ollama no longer critical** — removed Ollama connectivity from the overall health flag; Ollama is an optional translation backend and its unavailability only affects translation, not core subtitle management; the status bar now correctly shows Online when Sublarr itself is reachable

---

## [0.36.3-beta] - 2026-03-29

### Fixed
- **Preview Player — Firefox subtitle crash (definitive fix)** — replaced `createTrack("/sub.ass")` with `createTrackMem(content, length)` in the libass-wasm worker's `onRuntimeInitialized`; bypasses `ass_read_file()` (which returns NULL in Firefox even with valid WASM FS content) by passing the placeholder ASS directly in memory via `ass_new_track` + `ass_process_data`; real subtitle continues to load post-init via `setTrackByUrl()`

## [0.36.2-beta] - 2026-03-29

### Fixed
- **Preview Player — Firefox subtitle crash** — fixed `ass_read_file` returning NULL in the libass-wasm worker (Firefox); the worker's `onRuntimeInitialized` always calls `createTrack("/sub.ass")` — now initialised with a valid placeholder ASS so the init-time call succeeds; real subtitle is loaded post-init via `setTrackByUrl()` through the worker's message buffer; also fixes CSP `wasm-unsafe-eval` and fallback font (`default.woff2` via `fonts-liberation` in Docker)

## [0.36.1-beta] - 2026-03-29

### Fixed
- **Preview Player — subtitle rendering** — subtitles now render correctly in the preview player; fixed canvas overlay positioning (libass canvasParent inserted inside relative wrapper), worker auth (subContent instead of unauthenticated subUrl), and CJS constructor interop for libass-wasm
- **Preview Player — subtitle toggle latency** — eliminated 10–20 s reappearance delay when toggling subtitles off/on; worker is now kept alive across track changes and reuses `setTrack()`/`freeTrack()` instead of a full WASM worker restart

## [0.36.0-beta] - 2026-03-29

### Added
- **Scoring — video_codec weight** — x264/x265/AV1 codec match adds +2 points to episode and movie scores (Bazarr parity)
- **Language Profiles — mustContain / mustNotContain** — AND-logic filter: only accept subtitles matching ALL mustContain terms; any mustNotContain term rejects (Bazarr parity); new DB columns on `language_profiles`
- **Language Profiles — cutoff** — stop searching for a language once a subtitle is already present on disk
- **Language Profiles — audioExclude** — skip downloading a subtitle if the audio track is already in the target language
- **Provider Infrastructure — CircuitBreaker persistence** — CB OPEN state written to `ProviderStats.disabled_until`; survives application restarts; `is_open` property added
- **Provider Infrastructure — rate-limit throttle** — configurable extended throttle on `ProviderRateLimitError` via `provider_rate_limit_throttle_minutes`
- **Download Quality — upgrade chain tracking** — `upgraded_from_id` foreign key on `subtitle_downloads` records which subtitle was replaced; enables full upgrade audit trail
- **Download Quality — post-download command** — `post_download_command` config executes an arbitrary shell command after each successful download; supports `{subtitle_path}`, `{language}`, `{provider}`, `{score}` variable substitution
- **Sync — manual alass endpoint** — `POST /api/v1/sync/alass` triggers alass subtitle synchronisation on demand

### Added
- **Standalone Mode — Auto-activation** — `is_standalone_mode()` helper auto-activates standalone mode when no *arr is configured; `StandaloneStatus` extended with `arr_configured` and `auto_activated` fields
- **Connections — Standalone scan button** — manual scan button added to the Standalone section in Connection Settings

### Changed
- **Settings — Connections** — removed central API Keys section; API keys are now managed inline within each connection's own settings panel
- **Translation — Beta marking** — Translation card on Settings overview now shows "BETA" pill; Translation Settings page shows a warning banner

### Fixed
- **Language Profiles — mustContain AND logic** — corrected to require ALL terms instead of ANY term (Bazarr parity fix)
- **Post-download hook** — guard added via `getattr(self, 'settings', None)` to prevent crash when settings are not available
- **OpenSubtitles — Anime season-1 collapse** — fallback search now maps S02+ episodes to Season 1 with the original episode number (not absolute episode); `moviehash` stripped from fallback params to allow title-based lookup
- **UI — WebSocket events** — corrected event names (`upgrade_complete`, `wanted_scan_complete`); added `wanted_item_searched` handler
- **UI — Wanted page** — per-row independent loading state (shared `isPending` was spinning all rows simultaneously)
- **UI — Episode Search Panel** — null-safety guards on `target_results` and `source_results`

---

## [0.35.0-beta] - 2026-03-22

### Added
- **Movie Detail — Subtitle Management** — wanted items section below file info shows missing subtitles per language; inline Search / Skip / Re-enable buttons; wired to `/wanted?movie_id=` filter
- **Backend — `/wanted` movie filter** — new `?movie_id=` query param filters wanted items by `standalone_movie_id`; enables movie detail subtitle management without loading the full wanted list

### Changed
- **Series Detail — Episode Grid** — restored full feature set: per-row checkboxes, SubBadge per subtitle language (teal = ASS optimal, purple = SRT upgradeable, orange = missing), audio-track badges, sidecar subtitle actions (delete, download, NFO export, subtitle menu, health badge, preview, edit), batch toolbar (Search / Extract / Translate / Cleanup), Skip / Accept inline actions wired to `useUpdateWantedStatus`
- **Dashboard — AutomationBanner** — subtitle line now shows live "Last completed: X ago" derived from `scannerStatus.last_scan_at`; replaces hardcoded placeholder text
- **Library** — fixed `anime_only=False` filter that was hiding non-anime content; all library entries now visible regardless of type

### Fixed
- **Settings — API Keys** — removed duplicate TMDB and TVDB entries; fixed `updateApiKey` request body format that was causing 400 errors on save
- **Security — CSP / Permissions-Policy** — `Content-Security-Policy` and `Permissions-Policy` response headers added to all responses (F-23)
- **Security — Webhook SSRF** — `validate_service_url()` applied to webhook create and update endpoints; blocks dangerous URL schemes (F-21)
- **Security — Auth warning** — startup `SECURITY WARNING` log emitted when both API key and UI auth are disabled, alerting operators to the open-API exposure (F-17/F-18 root cause)

---

## [0.33.0-beta] - 2026-03-20

### Added
- **Providers — Subf2m** — new subtitle provider supporting 60+ languages via Subf2m.co
- **Providers — Subsource** — new subtitle provider (multi-language, movie & TV)
- **Providers — YIFY Subtitles** — movie-only provider using IMDB-based JSON API
- **Providers — Zimuku** — Chinese subtitle provider (simplified & traditional)
- **Providers — BetaSeries** — French subtitle provider for TV series
- **Providers — Titlovi** — Balkan subtitle provider (Croatian, Serbian, Bosnian, Slovenian, Macedonian)
- **Providers — EmbeddedSubtitles** — integrates embedded subtitle tracks from media files directly into the search and scoring pipeline
- **Subtitle Processing Pipeline** — post-download processing hook; 18 fix functions (HI removal, common formatting corrections, OCR artifact cleanup); configurable per-series via series detail panel
- **Settings — Processing Pipeline** — new settings section for configuring post-processing behavior (fix modules, interjection list)
- **Series Detail — Batch Process** — button to run post-processing on all existing subtitles for a series; progress log modal

### Changed
- **Settings — Fansub / Release Groups** — global release-group preference fields moved from Wanted tab to Scoring tab where they belong conceptually
- **Series Detail — Fansub Preferences** — replaced the always-visible card with a compact toolbar button; active overrides highlighted in accent color; per-series settings in a modal dialog

### Fixed
- **Security — SSRF** — URL validation in `PUT /api/v1/config` now covers dot-notation extension keys (e.g. `whisper.subgen.url`) that previously bypassed the `_URL_FIELDS` check
- **Security — SocketIO log sanitization** — `SocketIOLogHandler` now strips DB-internal error details (table names, column names, query fragments) before emitting to WebSocket clients
- **Backend — startup crash** — `validate_service_url` was imported in `routes/config.py` but never implemented; added full SSRF-safe implementation

---

## [0.32.0-beta] - 2026-03-19

### Changed
- **Settings — Navigation** — Restructured from 7 groups / 23 tabs to 5 logical groups (Connections, Languages & Subtitles, Providers, Automation, System); no tabs removed
- **Providers — Priority** — Replaced move-up/down buttons in edit modal with drag & drop handles on provider tiles

### Added
- **Score Breakdown** — Hover tooltip on score badges in search results shows per-component point breakdown (series title, season, episode, format bonus, provider modifier, etc.)
- **Wanted — Failure Details** — Failed items now show inline error reason, attempt count, and next retry countdown
- **Wanted — Batch Progress** — Progress bar with found/failed counters during "Search All" operation
- **Dashboard — Automation Widget** — New widget showing automation status (enabled/disabled), today's found/failed subtitle stats, last/next run times, and Run Now button
- **Onboarding — Language Step** — New wizard step to configure target and source language during first-time setup
- **Onboarding — Automation Step** — New wizard step to configure automatic search interval and subtitle upgrade behavior

---

## [0.31.0-beta] — 2026-03-19

### Changed
- **Backend — Test Foundation** — added 29 new tests covering `WantedSearchService`, `ProviderManager`, and quality-validation logic; total suite now 736 tests at 47.76% coverage
- **Backend — Type Safety + Lint** — resolved all `ruff` errors and `mypy` type warnings across the entire backend; no new ignores added
- **Backend — File Splits** — 8 oversized files (800–2921 lines) decomposed into focused packages: `routes/hooks/`, `routes/library/`, `routes/wanted/`, `routes/translate/`, `routes/system/`, `routes/tools/`; service packages `translator/` and `wanted_search/`; shared batch state extracted to `routes/batch_state.py`
- **Backend — Architecture** — `providers/registry.py` with `PROVIDER_METADATA` dict replaces three class-level dicts; nested `Settings` views (`GeneralSettings`, `TranslationSettings`, `ProviderSettings`, `MediaServerSettings`, `ScanningSettings`) with read-only delegation; singleton lifecycle via `get_scanner()`/`get_provider_manager()` checking `app.extensions`
- **Frontend — SyncControls split** — `SyncControls.tsx` decomposed into `OffsetTab`, `SpeedTab`, `FramerateTab`, `ChapterTab`, `StandardActions`, `SyncTabBar`; orchestrator retains all state and handlers
- **Frontend — useApi split** — `useApi.ts` decomposed into six domain files: `useLibraryApi`, `useWantedApi`, `useTranslationApi`, `useProvidersApi`, `useIntegrationApi`, `useSystemApi`; barrel re-exports all public hooks
- **Frontend — Error Boundaries** — `ErrorBoundary` component wraps Library, Wanted, and Settings routes; runtime errors are caught per-route instead of crashing the full app

### Fixed
- **Backend — monkeypatch targets** — updated `test_wanted_search_reliability.py` patch paths to point to the submodule where each function is called after the Phase 3 package split
- **Frontend — verbatimModuleSyntax** — added `import type` to all interface-only imports in `VideoPlayer.tsx`, `PlayerModal.tsx`, `SubtitleTrackSelector.tsx` to satisfy `verbatimModuleSyntax: true` in tsconfig
- **Frontend — TypeScript strict errors** — fixed all errors from `tsc --project tsconfig.app.json`: toast call signature (`toast.success/error` → `toast(msg, type)`), `'warning'` toast type (→ `'error'`), missing `RefreshCw` import, `handleDeleteSidecar` return type, duplicate `style` JSX attribute, Recharts `Formatter` type mismatch, duplicate `subscene` provider key, implicit `any` in Logs filter callback, `useSeriesDetail` nullable parameter, missing libass-wasm type declaration

---

## [0.30.0-beta] — 2026-03-16

### Added
- **Standalone — NFO metadata integration** — standalone scanner reads `.nfo` sidecar files to resolve series/movie title, year, TVDB/TMDB ID, and episode metadata without requiring an API lookup; falls back to filename parsing when no NFO is present
- **Standalone — Skip extra files** — trailers, featurettes, samples and other non-episode extras are now excluded from subtitle discovery during standalone filesystem scan; follows Jellyfin/Kodi naming convention (`-trailer`, `-featurette`, `-behindthescenes`, `-deleted`, `-interview`, `-scene`, `-short`, `-sample`, `-theme`); configurable via `standalone_skip_extras` toggle in Settings → Library Sources (advanced)

### Fixed
- **Standalone — symlinks and SQLAlchemy text() compatibility** — `os.walk(followlinks=True)` now follows symlinked directories; raw SQL wrapped in `sqlalchemy.text()` to fix deprecation warnings
- **Standalone — app context** — scanner operations that write to DB now correctly run inside Flask app context to avoid `RuntimeError: No application context`
- **Standalone — library view** — standalone series/movies now appear in Library with correct poster URLs and breadcrumb navigation
- **Standalone — series detail fallback** — SeriesDetail page gracefully handles episodes without a Sonarr instance; subtitle sidecar endpoint falls back to standalone path resolution
- **Standalone — poster endpoint** — path security enforced via `is_safe_path()`; URL generation updated to use `/api/v1/` prefix consistently
- **Standalone — NFO/poster lookup in Season subfolder** — scanner now finds `poster.jpg` and `.nfo` files inside `Season XX/` subdirectories, not only in the series root
- **Settings — nav redirect** — Setup page correctly redirects to `/settings` after initial configuration; `NavLink` `isActive` prop removed (invalid in React Router v6)
- **Wanted — scroll list layout** — replaced hardcoded `calc(100vh - 300px)` with `flex-1 / min-h-0` chain; list now fills the full remaining viewport at any window size

### Changed
- **Dependencies** — jsdom 28 → 29; 13 npm minor/patch updates

---

## [0.29.0-beta] — 2026-03-14

### Added
- **Web Player — Streaming endpoint** — `GET /api/v1/media/stream?path=` serves video files with HTTP 206 range-request support; `is_safe_path()` enforced; `Content-Type` resolved by extension; `SUBLARR_STREAMING_ENABLED` setting (default true) allows disabling the endpoint
- **Web Player — PlayerModal** — portal-based HTML5 `<video>` player with play/pause/seek/volume/fullscreen; opens via "Preview" button on episode cards in SeriesDetail
- **Web Player — ASS/SRT subtitle overlay** — SubtitleOctopus (libass WASM) renders styled ASS subtitles natively in-browser; `subtitles-octopus-worker.js` and `.wasm` served from `/public/`
- **Web Player — Subtitle track selector** — dropdown to switch between all available sidecar subtitle files for the episode; "Off" option disables overlay
- **Web Player — Seek-to-cue** — clicking a cue row in SubtitleEditorModal jumps the player to that timestamp via `onSeekRequest` bridge
- **Web Player — Settings toggle** — `streaming_enabled` toggle in Settings → Automation (advanced section)

---

## [0.28.0-beta] — 2026-03-14

### Added
- **AI Glossary Builder — DB schema** — adds `term_type` (character/place/other), `confidence` (float 0–1), `approved` (boolean) columns to `glossary_entries`; Alembic migration `f1a2b3c4d5e6`
- **AI Glossary Builder — Extractor service** — `glossary_extractor.py` performs frequency analysis over subtitle sidecar files to surface recurring proper-noun candidates without requiring an LLM
- **AI Glossary Builder — Suggest endpoint** — `POST /api/v1/series/<id>/glossary/suggest` triggers auto-detection and returns ranked candidates for human review
- **AI Glossary Builder — TSV export** — `GET /api/v1/glossary/export` downloads all approved glossary terms as a tab-separated file for external use
- **AI Glossary Builder — CRUD extended** — existing `POST/PUT /api/v1/glossary` endpoints accept the new `term_type`, `confidence`, and `approved` fields
- **AI Glossary Builder — Config** — `SUBLARR_GLOSSARY_ENABLED` (default true) and `glossary_max_terms` per-series cap (default 100) in Settings → Translation (advanced section)
- **AI Glossary Builder — LLM injection** — approved terms injected as `<glossary>` system prompt prefix during translation; capped at 50 terms; V8-compatible `term → translation` comma format retained; single-line fast-path added (`Translate to German: {line}`) when subtitle contains exactly one cue
- **AI Glossary Builder — GlossaryPanel UI** — Suggest button (Wand2 icon) triggers candidate detection; candidate list with approve/pre-fill/reject actions; `TermTypeBadge` (character/place/other); Export TSV button; all wired via new `suggestGlossaryTerms` and `exportGlossaryTsv` hooks

---

## [0.27.0-beta] — 2026-03-14

### Added
- **NFO Export — Auto sidecar** — `auto_nfo_export` config flag (off by default) writes an XML `.nfo` file alongside every downloaded or translated subtitle; contains provider, source/target language, score, translation backend, BLEU score, timestamp, and Sublarr version
- **NFO Export — API routes** — `POST /api/v1/subtitles/export-nfo?path=<path>` for single-subtitle export; `POST /api/v1/series/<id>/subtitles/export-nfo` for bulk export of all subtitles in a series; per-file `is_safe_path()` validation enforced on all paths
- **NFO Export — Settings toggle** — `auto_nfo_export` toggle in Settings → Automation (advanced section); expert feature, hidden behind "Show advanced"
- **NFO Export — SeriesDetail button** — `FileCode` button on each subtitle sidecar badge in SeriesDetail triggers single-file NFO export with toast feedback

---

## [0.26.0-beta] — 2026-03-14

### Added
- **Single-Account Login — First-run setup wizard** — on first visit, `/setup` presents two choices: set a password or leave the UI open; no forced registration
- **Single-Account Login — Flask session auth** — `before_request` hook enforces session-or-`X-Api-Key` on all `/api/` routes when enabled; session secret auto-generated and persisted in `config_entries`; bcrypt password hashing
- **Single-Account Login — Auth API** — `GET /api/v1/auth/status`, `POST /auth/setup` (first-run), `POST /auth/login`, `POST /auth/logout`, `POST /auth/change-password`, `POST /auth/toggle`; API key auth (`X-Api-Key`) remains independent
- **Single-Account Login — React routing** — `AuthGuard` component redirects to `/setup` or `/login` as needed; auth pages render full-screen without Sidebar
- **Settings → Security tab** — toggle UI auth on/off; change-password form (shown only when auth enabled)
- **Sidebar — Logout button** — shown when `auth.enabled && auth.authenticated`; navigates to `/login` on success

---

## [0.25.3-beta] — 2026-03-14

### Added
- **List Virtualization — Library table view** — replaced client-side pagination (25/page) with `@tanstack/react-virtual` virtual scroll using the padding-row technique; `<table>/<tr>` DOM structure preserved; sticky header; scroll resets on filter/sort; grid view retains pagination; `VirtualLibraryTable` + `LibraryShared` components extracted to `frontend/src/components/library/`
- **List Virtualization — Wanted list** — Wanted now fetches all matching items in a single request (up to 9 999) and renders with virtual scroll; `useWantedVirtualizer` hook in `frontend/src/components/wanted/VirtualWantedTable.tsx`; removes multi-page navigation

---

## [0.25.2-beta] — 2026-03-13

### Added
- **Subtitle Diff Viewer — Per-cue accept/reject** — `POST /tools/diff` computes a cue-level diff using pysubs2 + difflib.SequenceMatcher; returns structured diff entries (unchanged/modified/added/removed) with timing in seconds. `POST /tools/diff/apply` recomputes the diff server-side, merges accepted/rejected changes into the modified SSAFile (preserving header and styles), creates a `.bak` backup, and writes atomically via `os.replace`. Frontend `SubtitleDiff.tsx` rewritten from CodeMirror merge view to a filterable per-cue table; users can accept or reject each change individually or via Accept All / Reject All; applying navigates back to preview and invalidates the subtitle-content cache.

---

## [0.25.1-beta] — 2026-03-13

### Added
- **CLI — `sublarr search`** — search subtitle providers for all wanted items in a series via `--series-id <id>`; calls `GET /wanted` + `POST /wanted/batch-search`
- **CLI — `sublarr translate`** — translate a subtitle file via `POST /translate/sync`; supports `--force` flag; prints output path (sync) or job ID (queued)
- **CLI — `sublarr sync`** — sync subtitle timing to a video file via `POST /tools/auto-sync`; `--engine ffsubsync|alass`
- **CLI — `sublarr status`** — show active translation jobs and background task state; `--running` to filter in-progress jobs only
- **CLI — Entry point** — `backend/sublarr_cli.py`; configure via `SUBLARR_URL` and `SUBLARR_API_KEY` env vars or `--url`/`--api-key` flags

---

## [0.25.0-beta] — 2026-03-13

### Added
- **Jellyfin — Play-start webhook** — Sublarr now triggers the subtitle search+translate pipeline automatically when Jellyfin starts playing an episode; receives `PlaybackStart` events from the Jellyfin Webhook Plugin; resolves item path via configured Jellyfin/Emby media server instances
- **Settings → Automation — Jellyfin play-translate** — new toggle enables automatic translation on Jellyfin playback start (`SUBLARR_JELLYFIN_PLAY_TRANSLATE_ENABLED`, default off)

---

## [0.24.4-beta] — 2026-03-13

### Added
- **Chapter Detection — ffprobe-based chapter list** — Sublarr reads chapter metadata from video files; results cached per-file (mtime-invalidated) to avoid repeated `ffprobe` calls; path validated via `is_safe_path()`
- **Advanced Sync — Chapter Range** — offset operations can now be scoped to a chapter window; only subtitle events within the selected chapter are shifted; preview mode samples only in-range events
- **SyncControls — Chapter Tab** — new "Chapter" tab visible when chapters are detected; chapter dropdown (title + timestamps), ±offset presets, preview, and two-step confirm-apply flow

---

## [0.24.3-beta] — 2026-03-13

### Added
- **Fansub Preferences — per-series preferred and excluded groups** — configure preferred and excluded fansub groups per series; preferred groups receive a configurable score bonus, excluded groups are effectively filtered out; accessible from Series Detail
- **SeriesFansubPrefsPanel** — new panel in SeriesDetail with comma-separated preferred/excluded group inputs, bonus score field, and Save/Reset buttons

---

## [0.24.2-beta] — 2026-03-13

### Added
- **SeriesSettings — per-series Whisper audio track** — pin a preferred audio track index for Whisper transcription per series; clearing the setting (set to null) resumes automatic track selection
- **SeriesAudioTrackPicker** — new component in SeriesDetail; lazy-loads available audio tracks via ffprobe; dropdown sets the per-series Whisper transcription preference

---

## [0.24.1-beta] — 2026-03-12

### Added
- **OP/ED Detector** — detects Opening and Ending cue regions in subtitle files using ASS style name matching and position/duration heuristics; read-only detection returns `{type, start_ms, end_ms, event_count, method}` without modifying the file; configurable detection window via `SUBLARR_OP_WINDOW_SEC` (default 300 s)

### Changed
- **SubtitleEditorModal — Quality Tools** — added Detect OP/ED button after Remove Credits button

---

## [0.24.0-beta] — 2026-03-12

### Added
- **Credit Remover — `credit_remover.py`** — detects and removes credits-only subtitle lines from ASS/SSA/SRT files using 4 independent heuristics: role markers (`(Translator)`, `(QC)`, etc.), credit prefix patterns (`Credits:`, `Staff:`, etc.), duration heuristic (events near end of file), and isolated capitalized names (`John Smith`); `dry_run` mode for preview without modification
- **`POST /api/v1/tools/remove-credits`** — new endpoint to strip detected credits; `dry_run=true` returns preview of lines that would be removed (capped at 50); `dry_run=false` creates `.bak` backup then writes cleaned file; returns `original_lines`, `cleaned_lines`, `removed`, `backed_up`
- **Config — `credit_threshold_sec`** — new setting (`SUBLARR_CREDIT_THRESHOLD_SEC`, default 90s) controls how many seconds from the end of a file are considered the credits region

### Changed
- **SubtitleEditorModal — Quality Tools** — added Remove Credits button alongside existing Remove HI button

---

## [0.23.0-beta] — 2026-03-12

### Added
- **Batch Translate — `POST /wanted/batch-translate`** — re-translate multiple subtitle files in one request; accepts `item_ids` array; returns per-item success/failure map
- **Batch Search Extended** — `POST /wanted/batch-search` now accepts `series_ids` array for multi-series search in a single call
- **Library — Series Checkboxes** — multi-select series in Library view with floating batch toolbar (Search All Missing)
- **SeriesDetail — Episode Checkboxes** — multi-select episodes with floating batch toolbar (Search / Extract)
- **Filter Presets** — save, load, and delete named filter configurations on Library, Wanted, and History pages; persisted in `filter_presets` DB table via `GET|POST|DELETE /api/v1/filter-presets`
- **Global Search (Ctrl+K)** — fuzzy search across series, episodes, and subtitles; keyboard-accessible command palette
- **Auto-Extract on Scan** — `scan_auto_extract` + `scan_auto_translate` settings; scanner automatically extracts embedded subs on first detection

---

## [0.22.0-beta] — 2026-03-11

### Added
- **Marketplace — GitHub Plugin Discovery** — new Settings → Providers → Marketplace tab; discovers community plugins via `topic:sublarr-provider` GitHub topic search; caches results in `marketplace_cache` DB table with 1-hour TTL
- **Marketplace — Official/Community Badges** — plugins from `official-registry.json` receive a verified "Official" badge; community plugins show a neutral "Community" label; `is_official` flag persisted in DB
- **Marketplace — SHA256 Integrity Verification** — `install_plugin_from_zip()` verifies SHA256 hash before extraction; SHA256 is required (empty string rejected with HTTP 400); prevents install of corrupted or tampered plugins
- **Marketplace — Capability Warnings** — `CapabilityWarningModal` warns users before installing non-official plugins that declare `filesystem` or `subprocess` capabilities; confirmation required before proceeding
- **Marketplace — Installed Plugins DB** — `installed_plugins` table tracks name, version, capabilities, SHA256, plugin dir, and install timestamp; persists across restarts
- **Marketplace — Hot-Reload** — `POST /marketplace/install` hot-reloads the plugin manager after successful installation via `manager.reload()` + `invalidate_manager()`
- **Marketplace — Refresh** — `POST /marketplace/refresh` force-fetches latest plugin list from GitHub, bypassing the 1-hour cache TTL
- **Marketplace — Update Detection** — UI compares installed version against registry version; highlights available updates with a yellow badge
- **Config — `github_token`** — new optional `SUBLARR_GITHUB_TOKEN` setting; used for authenticated GitHub API requests to avoid rate limiting
- **DB Migration `a2b3c4d5e6f7`** — adds `marketplace_cache` and `installed_plugins` tables via Alembic

### Security
- **SSRF Prevention** — `zip_url` validated to be HTTPS-only before download (`urlparse` scheme check)
- **Path Traversal** — `is_safe_path()` applied to all install/uninstall plugin directory operations
- **XSS Prevention** — `github_url` validated with `startsWith('https://')` before rendering as `<a href>`

---

## [0.21.1-beta] — 2026-03-11

### Added
- **Accessibility — Toast `aria-live`** — `ToastContainer` now has `role="status"`, `aria-live="polite"`, and `aria-atomic="true"`; screen readers announce toast messages without interrupting focus
- **Accessibility — Skip-to-Main Link** — visually-hidden skip link added as first focusable element in the render tree; activating it moves focus to `#main-content`; visible on keyboard focus
- **Accessibility — Modal `role="dialog"`** — all 7 modals (`SubtitleEditorModal`, `WidgetSettingsModal`, `GlobalSearchModal`, `SubtitleCleanupModal`, `SyncModal`, `AddProviderModal`, `ProviderEditModal`) now have `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to the modal title, and `autoFocus` on the close button
- **Accessibility — Semantic Tables** — all `<th>` elements in Library, History, Blacklist, and Wanted tables have `scope="col"`; Library sort headers update `aria-sort` dynamically (`ascending` / `descending` / `none`)
- **Accessibility — Form Labels** — `AddProviderModal` and `ProviderEditModal` inputs have `aria-label` or `<label htmlFor>` associations; `SettingRow` renders a semantic `<label>` when `htmlFor` is provided
- **Accessibility — Client-Side Validation** — `AddProviderModal` and `ProviderEditModal` validate required fields on blur and on submit attempt; inline `<p role="alert">` error messages with `aria-invalid` / `aria-describedby` on inputs
- **StatusBadge — Lucide Icons** — each status now renders a lucide icon alongside the color dot for colorblind accessibility (`CheckCircle2`, `XCircle`, `Clock`, `Loader2`, `AlertCircle`, `Search`, `MinusCircle`); `Loader2` animates with `animate-spin`; color dot removed
- **Page-Specific Skeletons** — `LibrarySkeleton`, `TableSkeleton`, `ListSkeleton`, `FormSkeleton` added to `PageSkeleton.tsx`; Library, History, Queue, Blacklist, Wanted, and Settings Suspense boundaries use their matching skeleton instead of the generic one
- **`prefers-reduced-motion`** — CSS media query added to `index.css`; overrides all animation/transition durations to `0.01ms` for users who opt out of motion

### Changed
- **Library Grid — Tablet Breakpoint** — added `md:grid-cols-5` between `sm:grid-cols-4` and `lg:grid-cols-6`; smooths the column jump at 768px viewport
- **Stagger Animation — 300ms Cap** — Library grid cards and Wanted list rows apply `animationDelay: Math.min(i * 30, 300)ms`; late items on large lists no longer appear broken
- **CSS Hover — Remove JS State** — `RecentActivityWidget` and `ProviderTile` replaced `useState`/`onMouseEnter`/`onMouseLeave` background-color handlers with a `.hover-surface:hover` CSS utility class; eliminates unnecessary re-renders

---

## [0.20.0-beta] — 2026-03-10

### Added
- **PostgreSQL — First-Class Support** — full migration guide, PG-compatible Alembic migrations, dialect-aware health endpoints (`GET /database/health`), VACUUM guard (returns 501 on PostgreSQL); `docker-compose.postgres.yml` for batteries-included PG stack; `docs/POSTGRESQL.md` covers fresh install, SQLite→PG migration via pgloader, pool tuning, backup/restore
- **Incremental Metadata Cache** — ffprobe results cached persistently in DB with mtime-based invalidation; `GET /api/v1/cache/ffprobe/stats` and `POST /api/v1/cache/ffprobe/cleanup` endpoints; batch wanted-scanner probes now use cache (`use_cache=True`); eliminates redundant ffprobe calls on unchanged files
- **Background Wanted Scanner — Batch Commits** — scanner now batches all DB writes per series/movie into a single commit (instead of one commit per episode); thread-local `_batch_mode` flag ensures batch mode in the scanner thread never blocks concurrent API request commits; `SUBLARR_SCAN_YIELD_MS` setting (default: 0) adds optional CPU yield between series to reduce contention
- **Parallel Translation Workers — Configurable Count** — `SUBLARR_TRANSLATION_MAX_WORKERS` setting (default: 4) controls the thread pool size of the in-memory job queue; `/translate` async endpoint now routes through the shared job queue (same as `/translate/sync`) so concurrency is always bounded and observable via `GET /api/v1/jobs`
- **Redis Job Queue** — `backend/worker.py` RQ worker entry point with `AppContextWorker` subclass — each job runs inside a Flask app context; `docker-compose.redis.yml` stack with Redis 7 + Sublarr + `rq-worker`; scale workers with `--scale rq-worker=N`; graceful fallback to `MemoryJobQueue` when Redis is unreachable

---

## [0.19.2-beta] — 2026-03-10

### Fixed
- **Remux Engine — mkvmerge wrong track ID** — `_remux_mkvmerge` was referencing an undefined `stream_index` variable (NameError) and the call site was passing `subtitle_track_index` (0-based subtitle-only index, e.g. `0`) instead of the global ffprobe stream index (e.g. `2`); mkvmerge's `--subtitle-tracks !N` flag uses global Track IDs matching ffprobe's `stream_index` — passing `!0` targeted the video track and left the subtitle untouched; now `_remux_mkvmerge` receives and uses the correct global `stream_index`; validated with mkvmerge v92.0 inside Docker

---

## [0.19.1-beta] — 2026-03-10

### Fixed
- **Dockerfile — mkvtoolnix missing** — added `mkvtoolnix` to the Docker image apt-get install step; without it `mkvmerge` was unavailable inside the container and all MKV stream removal jobs failed with "mkvmerge not found"

---

## [0.19.0-beta] — 2026-03-10

### Added
- **Stream Removal — Safe Remux Engine** — remove embedded subtitle streams from video containers without re-encoding; mkvmerge used for MKV/MK3D, ffmpeg for all other containers (MP4, AVI, etc.); backend auto-detected by file extension; ffprobe verification after remux validates duration (±2s), video/audio stream counts, subtitle count (exactly -1), and file size (≥50% of original)
- **Trash-Folder Backups — Configurable Retention** — original video moved to centralized `<media_root>/<remux_trash_dir>/trash/<YYYY-MM-DD>/<file>.<ts>.bak` before each remux (TinyMediaManager-style); absolute trash path supported; falls back to sibling `.bak` on permission error; CoW reflink attempted first on Btrfs/XFS for near-instant copies; `remux_trash_dir` (default `.sublarr`) and `remux_backup_retention_days` (default 7) configurable in Settings → Automation
- **Async Remux Jobs** — `POST /api/v1/library/episodes/<ep_id>/tracks/<index>/remove-from-container` starts a background job; `GET /api/v1/remux/jobs` and `GET /api/v1/remux/jobs/<job_id>` expose status; real-time updates via Socket.IO `remux_job_update` events; optional Sonarr/Radarr folder-monitoring pause during remux
- **Backup Management API** — `GET /api/v1/remux/backups` lists all `.bak` files in trash directories; `POST /api/v1/remux/backups/cleanup` deletes backups older than retention period (supports `dry_run` mode)
- **Undo / Restore** — `POST /api/v1/remux/backups/restore` atomically restores backup to original video path via `os.replace()`; both paths validated with `is_safe_path()` to prevent path traversal; "Undo" button appears in TrackPanel after successful stream removal and restores in one click

---

## [0.18.0-beta] — 2026-03-10

### Added
- **HI Support — Hearing Impaired Preference** — new `hi_preference` setting (`include` / `prefer` / `exclude` / `only`); provider results scored accordingly: `prefer` adds +30, `exclude` / `only` apply ±999 penalty; `hi_removal_enabled` toggle for future HI-tag stripping
- **Forced Subtitle Support — Forced Preference** — new `forced_preference` setting (`include` / `prefer` / `exclude` / `only`) with same ±30/±999 scoring logic; bonuses stack when both HI and forced preferences match
- **TRaSH Scoring Presets — Importable Community Profiles** — `backend/scoring_presets/` package with three bundled presets (`anime`, `tv`, `movies`); `GET /api/v1/scoring/presets`, `GET /api/v1/scoring/presets/<name>`, `POST /api/v1/scoring/presets/import` endpoints; Settings → Events & Hooks → Scoring tab shows preset selector and custom JSON import; import validates schema and calls `invalidate_scoring_cache()`
- **Anti-Captcha Integration — Provider 403 Bypass** — new `CaptchaSolver` class supporting Anti-Captcha.com and CapMonster via identical `createTask` / `getTaskResult` REST API; `anti_captcha_provider` + `anti_captcha_api_key` settings; Kitsunekko calls `_try_solve_captcha_and_retry()` on HTTP 403 — submits reCAPTCHA v2 token and retries; falls back gracefully if no solver configured; Anti-Captcha section added to Providers tab in Settings

---

## [0.17.0-beta] — 2026-03-10

### Added
- **Duplicate Detection — SHA-256 download dedup** — skips provider downloads when SHA-256 hash matches an existing subtitle in the same directory; stale hash entries are auto-cleaned on startup; toggleable via `SUBLARR_DEDUP_ON_DOWNLOAD`; hash registered on every successful file write
- **Smart Episode Matching — multi-episode + OVA/Special** — multi-episode filenames (`S01E01E02`) parsed to full episode list; OVA/Special/SP detection via guessit + filename regex; `release_group`, `source`, `resolution`, `absolute_episode` propagated to `VideoQuery` for all providers
- **Video Hash Pre-Compute** — `file_hash` computed once in `build_query_from_wanted()` and reused across all providers; eliminates redundant file reads when multiple providers are queried in parallel
- **Release Group Filtering** — include/exclude subtitle results by release group, codec, or source tag; score bonus for preferred groups; release metadata auto-extracted from filename via guessit; configurable at Settings → Wanted
- **Provider Result Re-ranking** — auto-adjusts per-provider score modifiers from download history; formula: success rate + avg score vs. global average + consecutive failure penalty; throttled hourly; preview endpoint and manual trigger available
- **Subtitle Upgrade Scheduler** — periodic re-check for higher-quality subtitles; eligibility: score < 500 OR non-ASS format; configurable `upgrade_scan_interval_hours` at Settings → Automation; manual trigger via `/tasks/upgrade-scan/trigger`
- **Translation Quality Dashboard** — daily quality trend chart (avg score + issue count) and per-series quality table (sortable, color-coded bars) added to Statistics page
- **Custom Post-Processing Scripts — `subtitle_downloaded` event** — `subtitle_downloaded` event now emitted from `save_subtitle()`; shell hooks at Settings → Events & Hooks receive `SUBLARR_SUBTITLE_PATH`, `SUBLARR_PROVIDER_NAME`, `SUBLARR_SCORE`, `SUBLARR_LANGUAGE`, and `SUBLARR_SERIES_TITLE` environment variables

---

## [0.15.2-beta] — 2026-03-03

### Added
- **Activity — Parsed media titles** — file column now shows parsed series/episode name and episode number instead of raw filename; full path still accessible in the expanded row; `parseMediaTitle()` utility added to `lib/utils.ts`
- **History — Blacklist confirmation dialog** — ban icon on history entries now opens a confirmation modal showing provider and title instead of blacklisting immediately; optional "Also delete subtitle file" checkbox deletes the sidecar file and invalidates the history cache in one atomic flow
- **SeriesDetail — Delete confirmation dialog** — deleting a subtitle sidecar now opens a confirmation modal with an "Also add to blacklist?" checkbox; when checked, the provider record is looked up from `subtitle_downloads` and added to the blacklist before the file is moved to trash
- **Activity — Expanded row layout** — expanded detail row redesigned with cleaner label/value grid, stats section, and better visual hierarchy

### Fixed
- **Wanted — `wanted_auto_translate=False` not respected** — `process_wanted_item()` always started a translation job regardless of the `wanted_auto_translate` setting; now the flag is checked and translation is skipped when disabled
- **Backend — `DELETE /library/subtitles`** — accepts optional `blacklist: bool` body parameter; when `true`, looks up the provider record in `subtitle_downloads` (LIKE-match on video base path + language) and calls `add_blacklist_entry()` before trashing the sidecar

---

## [0.15.1-beta] — 2026-03-01

### Fixed
- **App — SPA 404 on page reload** — `static_url_path=""` caused Flask's built-in static file route to intercept `/wanted`, `/library` etc. and return 404 before the `serve_spa()` catch-all; fixed by setting `static_folder=None` so only the custom handler runs
- **App — PostgreSQL startup warnings** — `rowid` in `wanted_items` dedup query replaced with `id` (primary key); `MIN(title)` aggregate added to search index rebuild query to satisfy PostgreSQL GROUP BY rules; `_patch_pre_alembic_columns()` detects and adds the `source` column to `subtitle_downloads` for databases created before Alembic was introduced
- **Scoring — `_DEFAULT_EPISODE_WEIGHTS` import** — re-exported from `db.scoring` so `routes/hooks.py` can import them without reaching into the repository layer

---

## [0.15.0-beta] — 2026-03-01

### Added
- **Sidebar — Update available badge** — a pulsing badge appears in the sidebar when a newer GitHub release is available; the version is fetched from the GitHub Releases API once on load and cached; clicking opens the release page directly

### Fixed
- **Wanted — Search and download** — provider search and download were broken due to missing Flask app context in background threads and stale cache; fixed by passing the app instance explicitly and resetting the provider cache on each call

---

## [0.14.2-beta] — 2026-03-01

### Added
- **Wanted — Extracted status** — extracting an embedded subtitle no longer removes the item from Wanted; instead it stays visible with a new teal `Extracted` badge so the user can see what was extracted and trigger translation or cleanup as a follow-up step
- **Wanted — Sidecar Cleanup** — new `POST /api/v1/wanted/cleanup` endpoint and matching UI button (with confirmation dialog) that deletes non-target-language `.ass`/`.srt` sidecar files next to media files of extracted items; supports `dry_run` mode and optional `item_ids` filter; path-traversal protected via `is_safe_path()`
- **Wanted — Extracted filter tab** — new filter tab in the status row allows filtering the Wanted list to show only items with status `extracted`

### Changed
- **Wanted — Extract behavior** — `PUT /wanted/<id>/status` now accepts `extracted` as a valid status value in addition to `wanted`, `ignored`, `failed`

---

## [0.14.1-beta] — 2026-03-01

### Added
- **Library — Grid/Thumbnail view** — toggle button (table ↔ grid) next to series/movies tabs; grid renders poster images from Sonarr/Radarr with missing-count badge; preference persisted to `localStorage`; fallback film-slate SVG when no poster available
- **Library — Status and profile filters** — dropdown to filter items by status (all / has missing / complete) and by profile name; filtering applied client-side via `useMemo` with no additional API calls
- **Wanted — Error and retry display** — failed wanted items now show the failure reason as a truncated `⚠ message` tooltip in the status column; upcoming retry time shown as `Retry: Xm/Xh` below the badge when `retry_after` is set
- **Settings — Search field** — text input at the top of the settings sidebar filters tabs by name in real-time; Migration tab is excluded from search results regardless of the Advanced toggle
- **SeriesDetail — EpisodeActionMenu** — replaces 8 unlabelled icon-only action buttons with two primary labelled buttons (Search, Edit) and a `⋯ More` dropdown grouped by category (Preview/Compare, Timing, Analyse, History); extracted into standalone `EpisodeActionMenu` component

### Fixed
- **Sidebar — Version display** — version fallback changed from the hardcoded `v0.1.0` to `v…` while the health endpoint is loading; version now always reflects `backend/VERSION` correctly
- **i18n — SeriesDetail action buttons** — all 12 episode action button tooltips (Preview, Edit, Compare, Sync Timing, Auto-Sync, Video Sync, Health Check, Embedded Tracks, Search, Interactive Search, History, Back) were hardcoded English; replaced with `t('library:episode_actions.*')` keys available in both DE and EN
- **i18n — Wanted page** — "Scan Embedded" button label, "Scanning…" state text, and "Upgrades Only (N)" filter badge were hardcoded; replaced with `t('library:wanted.*')` keys
- **i18n — FilterBar / FilterPresetMenu** — "Add filter", "Clear all", "Presets", "No saved presets", "Preset name…", "Save current filters" were hardcoded English; now use `t('common:filters.*')` keys
- **Settings — Migration tab visibility** — Migration tab was always visible in the System group; now only rendered when the Advanced toggle is active and the settings search field is empty

### Changed
- **Statistics — empty state message** — placeholder text updated to mention subtitle searches in addition to translations so users understand both workflows populate the chart
- **Statistics — download tracking** — `record_subtitle_download()` in `db/providers.py` now also writes to the `daily_stats` table via `record_stat()`; provider downloads were previously invisible on the Statistics page (only translation jobs were tracked)

---

## [0.14.0-beta] — 2026-03-01

### Added
- **Provider UI — Disable vs. Remove** — Power button grays out a provider tile in-grid (50% opacity, "Disabled" badge) while Trash button removes it to the `+` pool entirely; new `providers_hidden` config key separates "off but visible" from "removed from grid"
- **Provider — Subscene** — 55-language community subtitle database, no account required; HTML scraping with BeautifulSoup4, rate limit 10/60 s
- **Provider — Addic7ed** — 36 languages, TV-series specialist with episode-exact matching; optional login credentials increase daily download limit; BeautifulSoup4, rate limit 10/60 s
- **Provider — TVSubtitles** — 35 languages, TV-series only, no auth; BeautifulSoup4, rate limit 15/60 s
- **Provider — Turkcealtyazi** — Turkish subtitle community site, login required; BeautifulSoup4, rate limit 10/60 s
- **Language expansion** — `_LANGUAGE_TAGS` expanded from 25 to ~70 ISO 639-1 codes; `SUPPORTED_LANGUAGES` constant with 63 ordered entries served via `GET /api/v1/languages` (cached 1 h)
- **LanguageSelect component** — searchable dropdown for source/target language settings that updates both the language code and `_name` fields simultaneously

### Changed
- **Settings — source/target language** — fields now use the new `LanguageSelect` dropdown instead of plain text inputs
- **Provider reactive health checks** — status is fetched on-demand only (no background polling); `ProviderManager.update_providers()` does selective enable/disable without full reinit; `providers_hidden` key excluded from provider reinit trigger
- **Provider UI grid** — complete tile-grid redesign: ProviderTile shows status badge, success rate, language count, and credential type; AddProviderModal replaces flat list with searchable cards; ProviderEditModal uses structured config_fields; header shows `N active / M configured` counts; `+` tile only visible when hidden providers exist
- **CI** — `actions/checkout`, `actions/setup-node`, `actions/setup-python` bumped to v6

---

## [0.13.2-beta] — 2026-02-28

### Security
- **Path traversal hardening** — `is_safe_path()` from `security_utils` now enforced on all 8 remaining routes that accepted user-supplied file paths: `tools.py`, `video.py`, `whisper.py`, `spell.py`, `integrations.py`, `webhooks.py`, `translate.py` (4 endpoints + batch directory), `subtitles.py`; inline ad-hoc `os.path.abspath().startswith()` checks replaced throughout (CRITICAL)
- **WebSocket authentication** — Socket.IO `connect` handler now rejects connections with an invalid or missing API key when `SUBLARR_API_KEY` is set; frontend `WebSocketContext` passes the key via socket `auth` dict (HIGH)
- **Secret masking in API responses** — `get_safe_config()` extended to deep-mask JSON blob fields (`sonarr_instances_json`, `radarr_instances_json`, `media_servers_json`) — credential sub-keys (`api_key`, `password`, `token`, `secret`, `pin`) replaced with `"***"`; `notification_urls_json` always masked; `routes/config.py` blocklist extended with 8 additional sensitive keys (HIGH)
- **Request size limit** — `MAX_CONTENT_LENGTH = 16 MB` added to Flask app factory to prevent DoS via oversized request bodies (HIGH)
- **Hook script path restriction** — `create_hook` and `update_hook` now validate `script_path` against `/config/hooks/` using `is_safe_path()`; arbitrary filesystem execution blocked (HIGH)
- **SQL injection in Bazarr migrator** — table names read from the Bazarr SQLite file validated with `^[a-zA-Z_][a-zA-Z0-9_]*$` regex before interpolation into queries; invalid names skipped with a warning (HIGH)
- **XZ decompression bomb protection** — `AnimeTosho._decompress_xz()` now enforces a 10 MB limit on decompressed output; payloads exceeding the limit raise `ValueError` (MEDIUM)
- **Container hardening** — port binding changed from `0.0.0.0` to `127.0.0.1`; `read_only: true` + `tmpfs: [/tmp]` added to `docker-compose.yml` (MEDIUM)

### Changed
- **Dev/prod requirements split** — test and lint tools (`pytest`, `ruff`, `mypy`, `bandit`, `locust`, etc.) moved from `requirements.txt` to new `requirements-dev.txt`; production image no longer installs dev dependencies
- **CI** — backend job now installs `requirements-dev.txt` alongside `requirements.txt` so lint and test tools are available

---

## [0.13.1-beta] — 2026-02-28

### Added
- **Sidecar discovery APIs** — `GET /api/v1/library/series/<id>/subtitles` scans all episode files in parallel (ThreadPoolExecutor) and returns sidecar metadata keyed by Sonarr episode ID; `GET /api/v1/library/episodes/<id>/subtitles` for single-episode scan; response includes path, language, format, size, and mtime for each sidecar file
- **Sidecar delete API** — `DELETE /api/v1/library/subtitles` moves one or more sidecar files to a `.sublarr_trash/` folder (manifest.json per entry) instead of permanently deleting; only files inside `SUBLARR_MEDIA_PATH` are accepted — path-traversal attempts return 403
- **Trash management APIs** — `GET /api/v1/library/trash` lists recoverable files; `POST /api/v1/library/trash/<id>/restore` moves the file back; `DELETE /api/v1/library/trash/<id>` permanently removes it; auto-purge of entries older than `subtitle_trash_retention_days` (default: 7 days) runs on every delete call
- **Batch delete API** — `POST /api/v1/library/series/<id>/subtitles/batch-delete` removes sidecars across all episodes of a series filtered by language and/or format; all deletions go through the trash system
- **Inline sidecar badges** — SeriesDetail episode rows now show a badge for every sidecar file found on disk (language + format label); non-target-language sidecars are displayed in a dimmed style with a × delete button; clicking × soft-deletes the file and immediately refreshes the row
- **Subtitle Cleanup Modal** — series-level "Clean up" button opens a modal grouped by language showing file count and total size per language; "Keep target languages only" quick action pre-selects all non-target languages for deletion; preview shows file count and MB to be moved to trash before confirming
- **Live extraction progress** — `batch-extract-tracks` emits a `batch_extract_progress` WebSocket event after each episode; SeriesDetail shows a progress banner (file name + `X / N episodes`) with a progress bar and animated spinner while extraction is running; Extract button is disabled during the operation
- **Activity page visibility** — `batch-extract-tracks` now creates a DB job record (`running` → `completed`/`failed`) so every extraction run appears on the Activity page with succeeded, failed, and skipped episode counts; the job is visible within one poll cycle (~3 s) of starting
- **Always-visible series toolbar** — new action row pinned to the SeriesDetail hero header containing three buttons: "Extract Tracks" (triggers `batch-extract-tracks` for the whole series, shows live X/N counter), "Clean up" (opens Subtitle Cleanup Modal), and "Search N missing" (moved here from the language row); all three actions are available without selecting individual episodes
- **Auto-cleanup settings** — three new config fields: `auto_cleanup_after_extract` (boolean toggle), `auto_cleanup_keep_languages` (comma-separated ISO 639-1 codes, e.g. `de,en`), `auto_cleanup_keep_formats` (`ass` / `srt` / `any`); when enabled, sidecars not matching the keep rules are moved to trash automatically at the end of each `batch-extract-tracks` run
- **Settings UI** — three new fields added to the Automation tab; `subtitle_trash_retention_days` field also added to control automatic trash purge interval
- **Wanted Batch Search card** — `useWantedBatchStatus()` was previously wired but never rendered; now shown as an amber card with a progress bar and found/failed/skipped item counts while a batch search is running
- **Batch Probe card** — live progress card appears while `batch-probe` is running; shows total tracks scanned, found, extracted, and failed counts plus the currently processed file path; teal accent with animated `Layers` icon
- **Wanted Scanner card** — new `GET /api/v1/wanted/scanner/status` endpoint exposes the full live state of the background wanted scanner (`is_scanning`, `is_searching`, phase label, current/total progress, added/updated counters); rendered as a green card with an optional phase badge and progress bar; adaptive polling — 3 s while active, 30 s idle
- The Queue page now shows all four background operations simultaneously: Batch Translation, Wanted Batch Search, Batch Probe, and Wanted Scanner — each with a distinct colour accent and its own progress indicator

### Changed
- **Subtitle badge semantics** — three visual states: teal = ASS/embedded-ASS (optimal), violet = SRT/upgradeable, orange = missing; non-target-language sidecar files shown in a separate dimmed group with × delete button
- **Language code normalisation** — `normLang()` maps ISO 639-2 three-letter codes (`ger`, `eng`, `jpn`, `fre`, …) to ISO 639-1 two-letter codes (`de`, `en`, `ja`, `fr`, …) so MKV track tags and sidecar filenames no longer generate duplicate badges for the same language
- **SeriesDetail subtitle column** — changed from a fixed `w-40` (160 px) width to `flex-1 min-w-[200px]` so badge rows expand to fill available space and avoid excessive wrapping on wide screens
- **Sidecar query live refresh** — `['series-subtitles']` TanStack Query polls every 4 s while extraction is running; on completion both `['series-subtitles']` and `['series']` are invalidated so episode rows update without a manual reload
- **Queue page polling** — job list refetch interval reduced from 15 s to 3 s so short-lived translation jobs are reliably visible while the Queue page is open

### Fixed
- **Batch-extract series_id 400** — `batch_extract` read `page.get("items", [])` but `get_wanted_items()` returns `{"data": [...]}`, causing every series-level extraction triggered from SeriesDetail to return 400 "item_ids or series_id required"; fixed to `page.get("data", [])`
- **Batch-probe deadlock** — a database error inside `get_wanted_items()` during a probe run left `probe.running = True` permanently until process restart; the call is now wrapped in try/except so the flag is always cleared on failure
- **wanted_item_searched event dropped** — the `wanted_item_searched` signal was emitted in `routes/wanted.py` but never registered in `events/catalog.py`, causing the event to be silently discarded by the unknown-name guard in `emit_event()`; catalog entry and signal registration added
- **Duplicate language badges** — `ger` MKV track tag and target language `de` previously rendered as two separate badges; `normLang()` now normalises both sides before comparison so they collapse to a single badge


---

## [0.12.3-beta] — 2026-02-28

### Security
- **ZIP Slip** — `marketplace.py` plugin installation now uses `safe_zip_extract()` that validates every entry before extraction (CRITICAL)
- **Git clone SSRF/RCE** — `validate_git_url()` enforces HTTPS + domain allowlist (github.com, gitlab.com, codeberg.org) for plugin installs (CRITICAL)
- **Path traversal** — `is_safe_path()` guard added to video segment, audio waveform/extract and OCR endpoints (HIGH)
- **Symlink deletion bypass** — `dedup_engine.py` now skips symlinks and validates paths against `media_path` before deletion (HIGH)
- **Hook env injection** — `sanitize_env_value()` strips newlines and null-bytes from event data before passing to shell scripts (HIGH)
- **CORS wildcard Socket.IO** — replaced `"*"` with configurable `SUBLARR_CORS_ORIGINS` (default: localhost dev origins) (MEDIUM)
- New `backend/security_utils.py` — canonical security utilities used by all of the above

### Changed
- **CI** — paths-filter skips backend/frontend jobs when only the other side changed; concurrency cancels duplicate runs
- **Claude Code Review** — project context in review prompt; concurrency cancels stale reviews on new commits

---

## [0.12.0-beta] — 2026-02-23

### Added
- **Settings UX Redesign** — card-based sub-grouping in all tabs; each logical block has a header with icon, title, description and optional connection badge
- **SettingsCard component** — reusable card wrapper with divided body rows and ConnectionBadge slot
- **ConnectionBadge component** — 4-state indicator (connected/error/unconfigured/checking) for Sonarr, Radarr and media server tabs
- **Advanced Settings toggle** — global "Advanced" checkbox in the Settings header persisted to localStorage; hides annotated advanced fields by default with orange left-border marker
- **SettingRow descriptions** — all 38 config fields now show always-visible description text beneath each label; 10 fields marked as advanced
- **InfoTooltip improvements** — ESC-key dismiss, keyboard focus/blur handlers, full ARIA accessibility (`aria-describedby`, `role="tooltip"`, `useId`), `motion-safe:` animation prefix
- **Dirty-state Save button** — Save button disabled and grayed when no changes exist; enabled with amber indicator when fields differ from loaded config
- **Navigation warning** — `useBlocker` (React Router v6) + `window.beforeunload` prevent accidental navigation away with unsaved changes
- **ProvidersTab descriptions** — credential and endpoint fields annotated with contextual help text
- **MediaServersTab & WhisperTab descriptions** — all SettingRow fields annotated
- **TranslationTab descriptions** — backend credential fields annotated; PromptPresetsTab shows available template variables
- **MigrationTab improvements** — hardcoded Tailwind color classes replaced with CSS custom properties; context header added

---

## [0.11.1-beta] — 2026-02-22

### Added
- **Scan Auto-Extract** — `wanted_auto_extract` + `wanted_auto_translate` settings; scanner
  extracts embedded subs immediately on first detection when enabled
- **Batch Extract Endpoint** — `POST /api/v1/wanted/batch-extract` extracts embedded subs
  for multiple wanted items in one request
- **Multi-Series Batch Search** — `POST /api/v1/wanted/batch-search` now accepts `series_ids`
  array to trigger search across multiple series at once
- **SeriesDetail Batch Toolbar** — episode checkboxes with Search / Extract bulk actions
- **Library Batch Toolbar** — series checkboxes with Search All Missing bulk action

---

## [0.11.0-beta] — 2026-02-22

### Added
- **Track Manifest** (Phase 29) — list all embedded subtitle/audio streams in MKV files, extract them as standalone files, or use one as the translation source; TrackPanel component in Library/Series Detail
- **Video Sync Backend** (Phase 30) — `POST /api/v1/tools/video-sync` starts async ffsubsync/alass job; `GET` polls progress; fallback timeout 300s
- **Video Sync Frontend** (Phase 31) — SyncModal with engine selector (ffsubsync / alass), live progress bar; auto-sync after download configurable per-download
- **Waveform Editor** (Phase 32) — Waveform tab in the subtitle editor: wavesurfer.js visualization with per-cue region markers; backend extracts audio via ffmpeg with in-memory waveform cache
- **Format Conversion** (Phase 33) — convert ASS ↔ SRT ↔ SSA ↔ VTT via pysubs2; convert dropdown in TrackPanel for any non-image subtitle track
- **Batch OCR Pipeline** (Phase 34) — async `POST /api/v1/ocr/batch-extract` + `GET /api/v1/ocr/batch-extract/<job_id>` for extracting text from PGS/VobSub image-based subtitle tracks via Tesseract; parallel 4-worker frame processing
- **Quality Fixes Toolbar** (Phase 35) — one-click editor buttons: Overlap Fix, Timing Normalize, Merge Lines, Split Lines, Spell Check; all endpoints create `.bak` backup before modifying

### Fixed
- ESLint `react-hooks/set-state-in-effect` in `SubtitleEditorModal` — replaced synchronous `setState` calls in `useEffect` with React's "adjust during render" pattern

---

## [0.10.0-beta] — 2026-02-22

### Added
- **Context Window Batching** (Phase 19) — subtitle cues grouped into context-window-aware chunks for coherent LLM translation
- **Translation Memory Cache** (Phase 20) — SHA-256 exact-match + difflib similarity cache avoids retranslating identical/near-identical lines; `.quality.json` sidecar file tracks per-line scores
- **Per-Line Quality Scoring** (Phase 21) — LLM scores each translated line 0–10; low-scoring lines retried automatically; quality badge in Library/Series Detail
- **Bulk Auto-Sync** (Phase 22) — auto-sync buttons in Library, Series Detail, and subtitle editor; `POST /api/v1/tools/bulk-auto-sync` batch endpoint
- **Machine Translation Detection** (Phase 23) — detects OpenSubtitles `mt`/`ai` flags; orange MT badge on search results and in Library
- **Uploader Trust Scoring** (Phase 24) — 0–20 score bonus based on provider uploader rank; emerald Trust badge for top-ranked uploaders
- **AniDB Absolute Episode Order** (Phase 25) — `anidb_sync.py` fetches anime-lists XML weekly; providers query `absolute_episode` for correct numbering; routes/anidb_mapping.py + db/repositories/anidb.py
- **Whisper Fallback Threshold** (Phase 26) — configurable minimum Whisper confidence score; subs below threshold fall back to LLM retry
- **Tag-Based Profile Assignment** (Phase 27) — Sonarr/Radarr series/movie tags automatically assign language profiles via `TagProfileMapping` table; processed in webhook handler
- **LLM Backend Presets** (Phase 28) — 5 built-in prompt templates (Anime, Documentary, Casual, Literal, Dubbed); Settings UI "Add from Template" button; user-editable custom presets

### Fixed
- `_translate_with_manager`: `batch_size` chunking now applied correctly (regression in v0.9.6)
- Prompt presets: `{source_language}` / `{target_language}` placeholders substituted at runtime, not stored pre-substituted

---

## [0.9.6-beta] — 2026-02-21

### Fixed
- Zombie jobs: jobs stuck in "running" state after backend restart are cleaned up on startup
- Wanted page: pagination counter now reflects active filter, not full DB total
- Duplicate `wanted_items`: `UniqueConstraint(file_path, target_language, subtitle_type)` prevents race-condition duplicates
- `get_series_missing_counts()`: excludes `existing_sub = 'srt'` and `'embedded_srt'` (upgrade candidates) from "missing" count

---

## [0.9.5-beta] — 2026-02-21

### Added
- Global Glossary — per-language term overrides applied during all translations; configurable in Settings → Translation
- Per-Series Glossary — series-specific term overrides; accessible from Series Detail
- Provider test: works without explicit `Content-Type: application/json` header (`force=True` JSON parsing)

---

## [0.9.0-beta] — 2026-02-16

### Added
- Plugin architecture with hot-reload for custom subtitle providers
- Plugin discovery from `/config/plugins/` with manifest validation
- Plugin-specific configuration stored in `config_entries` database table
- Watchdog-based hot-reload with 2-second debounce (opt-in via `plugin_hot_reload`)
- Plugin developer template and documentation

- **Gestdown** — Addic7ed proxy with REST API, covers both Addic7ed and Gestdown content
- **Podnapisi** — Large multilingual database with XML API and lxml parsing
- **Kitsunekko** — Japanese anime subtitles via HTML scraping (BeautifulSoup optional)
- **Napisy24** — Polish subtitles with MD5 file hash matching (first 10MB)
- **Whisper-Subgen** — External ASR integration, returns low-score placeholder in search
- **Titrari** — Romanian subtitles via polite scraping (no auth required)
- **LegendasDivx** — Portuguese subtitles with session authentication and daily limit tracking

- Per-provider response time tracking with weighted running average
- Auto-disable after consecutive failure threshold (default: 10 failures)
- Configurable cooldown period (`provider_auto_disable_cooldown_minutes`, default: 30 min)
- Provider health dashboard with success rate, response time, and download counts

- **DeepL** backend with glossary caching by (source, target) language pair
- **LibreTranslate** backend for self-hosted translation (line-by-line for 1:1 mapping)
- **OpenAI-compatible** backend supporting any OpenAI API endpoint with CJK hallucination detection
- **Google Cloud Translation** backend with fresh client per call for credential rotation
- Per-profile backend selection in language profiles
- Automatic fallback chains with configurable backend priority
- Circuit breakers per translation backend (reuses provider circuit breaker pattern)
- Translation quality metrics tracked per backend

- **Plex** support with lazy `plexapi` connection (optional dependency)
- **Kodi** support with JSON-RPC `VideoLibrary.Scan` (directory-scoped)
- Unified media server settings page with multi-server configuration
- `MediaServerManager.refresh_all()` notifies all configured servers after subtitle changes
- Legacy Jellyfin configuration auto-migrated to new multi-server format

- **faster-whisper** backend with lazy model loading and device/compute_type caching
- **Subgen** backend for external Whisper API integration
- Case D translation pipeline: automatic Whisper fallback when all providers fail
- Whisper job queue with configurable max concurrency and progress via WebSocket
- Audio extraction via ffmpeg pipe (no temp files)
- Language detection validation against expected source language

- Folder-watch operation without Sonarr/Radarr dependency
- **TMDB** metadata lookup (requires API key)
- **AniList** metadata lookup (no API key required, 0.7s rate limiting)
- **TVDB** metadata lookup with 24h JWT token caching
- Anime detection via multi-signal heuristic (bracket groups, fansub groups, CRC32, absolute numbering)
- `guessit`-based filename parsing with anime-aware mode
- `MediaFileWatcher` with per-path debounce and file stability checks
- `StandaloneScanner` groups files by series for efficient metadata lookup
- Standalone items integrate with existing Wanted pipeline

- Multi-signal forced subtitle detection (ffprobe flags, filename patterns, title analysis, ASS style analysis)
- Per-series forced subtitle preference (disabled/separate/auto) in language profiles
- OpenSubtitles `foreign_parts_only` filter for native forced search
- Post-search forced classification for providers without native support
- Forced subtitle type badges and filter buttons in Wanted UI

- Internal event bus using `blinker` with signal isolation namespace
- 22+ business events published (subtitle_downloaded, translation_complete, provider_failed, etc.)
- Shell script hooks with environment variable payload and configurable timeouts
- Outgoing webhooks with HTTP POST, JSON payload, and retry logic on failure
- Event catalog with versioned payload schemas (CATALOG_VERSION=1)
- SocketIO bridge for real-time event forwarding to frontend

- Configurable scoring weights (hash, series, year, season, episode, release_group, ASS bonus)
- Per-provider score modifiers (-100 to +100 range)
- Scoring cache with 60s TTL and config-change invalidation

- English and German translations for entire UI
- `react-i18next` with static JSON imports (no HTTP backend)
- Language preference stored in localStorage (`sublarr-language`)
- `LanguageSwitcher` component in header

- Dark/light theme toggle with system preference detection
- Theme stored in localStorage (`sublarr-theme`) with 3 states: dark, light, system
- Inline script in `index.html` prevents flash of wrong theme before React hydration
- CSS variable-based theming

- Full backup (config + database as ZIP) with in-memory buffer
- Scheduled automatic backups with configurable interval
- Restore from ZIP upload via Settings UI
- Backup rotation with configurable retention count

- Recharts-based charts with responsive containers
- Time-range filters (7d, 30d, 90d, all)
- Daily stats, provider usage, translation backend performance, format distribution
- Subtitle download and upgrade history visualization

- Timing adjustment (centisecond precision, H:MM:SS.cc format)
- Encoding fix (detect and convert to UTF-8)
- Hearing impaired tag removal
- Style stripping (ASS to plain text)
- All tools create `.bak` backup before modification
- Path traversal prevention via `os.path.abspath` validation

- OpenAPI 3.0.3 specification at `/api/v1/openapi.json` with 65+ documented paths
- Swagger UI at `/api/docs` for interactive API exploration
- `apispec` + `apispec-webframeworks` for YAML docstring-based spec generation
- X-Api-Key security scheme for authenticated endpoints

- Incremental wanted scan with timestamp tracking (only rescans modified items)
- Full scan forced every 6th cycle as safety fallback
- Parallel ffprobe via `ThreadPoolExecutor` (max 4 workers per series)
- Parallel wanted search processing (removed 0.5s inter-item delay)
- Route-level code splitting with `React.lazy` for all 13 page components
- `PageSkeleton` loading component for Suspense fallback

- Extended `/health/detailed` with 11 subsystem categories
- Translation backend health checks per instance
- Media server health checks per instance
- Whisper backend health reporting
- Sonarr/Radarr connectivity checks across all configured instances
- Scheduler status reporting

### Changed
- **Architecture** — Application Factory pattern (`create_app()`) with 15 Flask Blueprints (from monolithic `server.py`)
- **Database** — Split `database.py` into `db/` package with 9 domain modules (from monolithic 2153-line file)
- **Frontend** — React 19 + TypeScript + Tailwind v4 (upgraded from React 18 + Tailwind CSS)
- **Translation** — Ollama configuration moved from dedicated tab to unified Translation Backends tab
- **Settings** — Split 4703-line `Settings.tsx` monolith into 7 focused tab modules under `Settings/` directory
- **Version numbering** — Changed from v1.0.0-beta to v0.9.0-beta (standard pre-release convention -- v1.0.0 reserved for stable release)
- **Gunicorn** — Single worker mode required for Flask-SocketIO WebSocket state consistency

### Fixed
- Case-sensitive email uniqueness in provider configurations
- Hardcoded version strings ("0.1.0") replaced with centralized `version.py`
- SPA fallback route now returns correct version string
- Toast message and ThemeToggle label i18n gaps closed
- Pre-existing integration test expectations updated for health endpoint response format


---

## [1.0.0-beta] — 2026-02-14

### Added
- **Provider System** — Direct subtitle sourcing from AnimeTosho, Jimaku, OpenSubtitles, and SubDL
- **Wanted System** — Automatic detection of missing subtitles via Sonarr/Radarr integration
- **Search & Download Workflow** — End-to-end subtitle acquisition without Bazarr
- **Upgrade System** — Automatic SRT-to-ASS upgrades with configurable score delta
- **Language Profiles** — Per-series/movie target language configuration with multi-language support
- **LLM Translation** — Integrated subtitle translation via Ollama (ASS and SRT formats)
- **Glossary System** — Per-series translation glossaries for consistent terminology
- **Prompt Presets** — Customizable translation prompt templates with default preset
- **Blacklist & History** — Track downloads and block unwanted subtitle releases
- **HI Removal** — Hearing impaired marker removal from subtitles before translation
- **Embedded Subtitle Detection** — Extract and translate subtitles embedded in MKV files
- **AniDB Integration** — TVDB-to-AniDB ID mapping for better anime episode matching
- **Webhook Automation** — Sonarr/Radarr webhooks trigger scan-search-translate pipeline
- **Multi-Instance Support** — Configure multiple Sonarr/Radarr instances
- **Notification System** — Apprise-based notifications (Pushover, Discord, Telegram, etc.)
- **Onboarding Wizard** — Guided first-time setup
- **Provider Caching** — TTL-based search result caching per provider
- **Re-Translation** — Detect and re-translate files when model/prompt/language changes
- **Config Export/Import** — Backup and restore application configuration
- **Docker Multi-Arch** — Builds for linux/amd64 and linux/arm64
- **Unraid Template** — Community Applications template for Unraid


