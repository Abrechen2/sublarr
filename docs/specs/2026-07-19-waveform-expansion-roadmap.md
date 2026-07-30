# Waveform Editor — Expansion Roadmap

- **Status:** Draft / concept (no implementation yet)
- **Date:** 2026-07-19
- **Baseline:** v1.9.4
- **Method:** Joint brainstorm — Claude (claude-opus-4-8) + Codex (gpt-5.4, high
  reasoning, read-only over the real `frontend/src/components/editor/waveform/`
  module).
- **Scope of this doc:** capture *what* to build and in *what order*. It does
  not contain final API shapes or task breakdowns — those come per phase.

---

## 1. Context

The Waveform Editor is a modal tab where users fine-tune subtitle **timing**
and **text** against an episode's audio — an in-browser, Aegisub-inspired
audio/subtitle editor built on `wavesurfer.js`. It is a core part of Sublarr's
value: after download + EN→DE translation, this is where a human makes the
result actually good.

Many users run Sublarr on **low-power hosts** (Synology DS920+, Raspberry Pi),
so client-side DSP cost and bundle size are real constraints. The backend can
run `ffmpeg`/`ffprobe` (keyframes, per-track audio extraction) and
`PySceneDetect` (scene cuts), and already runs `ffsubsync`/`alass` for
post-download auto-sync.

### Already shipped (v1.9.4)

Waveform with sticky timeline ruler; horizontal zoom (1–50 px/s, exponential
`+/-`), amplitude zoom (1×–5×), playback rate (0.5×–2.0×, pitch-preserved),
auto-center. Draggable cue-timing regions, edit-locked by default, 80 ms
min-gap snap. Click-set start/end (Aegisub L/R), keyframe snap + toggleable
markers, always-on gap/overlap quality markers, scene-cut markers, spectrogram
toggle, scrub-on-drag, audio-track picker. Active-cue bar, collapsible cue-list
lane (click-select, inline text edit when unlocked, playhead-follow),
display-only ASS karaoke overlay. Split (F) / merge (G) / prev-next (arrows) /
nudge seek / set start (S) / end (D) / play / undo / redo / save, `?` help.
Prefs in localStorage, i18n DE/EN, ~32 vitest contracts.

### Assessment (both models agreed)

The editor is **strong at single-cue manual timing with visual guardrails**,
but **weak at**: assisted repetition, bulk/ripple timing, "detect → fix" flows,
speech-vs-music awareness, and translation-aware readability signals.

---

## 2. Hard constraints (do not violate)

1. **Seven gold-standard surfaces are user-locked** (active-cue bar, in-region
   text labels, toggleable keyframe markers, amplitude zoom, playback-rate
   slider, always-on gap/overlap markers, sticky timeline ruler). New work is
   **additive**; keep the layout recognizable as an Aegisub-style editor. See
   memory `project_waveform_gold_standard` and `docs/PROTECTED.md`.
2. **ASS `\k` karaoke retiming stays out of scope** (stays in Aegisub). Display
   ticks only.
3. **Respect low-power hosts.** Prefer backend-computed, cached artifacts over
   heavy client-side DSP or large new bundles. New heavy features are opt-in.
4. **Never silently mutate timings.** Any automated fix/transform is
   preview/diff-first and undoable.

---

## 3. Idea catalog

Effort S/M/L · Value low/med/high · consensus = both models independently.

### 3.1 Editing power
| Idea | Why (anime-specific) | Effort | Value | Notes / risk |
|---|---|---|---|---|
| **Loop audition** with configurable pre-/post-roll (consensus) | Catch breaths, mouth-close, hard cuts around very short lines | S/M | high | No locked-surface conflict; negligible perf |
| **Ripple / block timing** on a contiguous selection: shift by ms/frames, stretch/compress between two anchors (consensus) | Whole OP/ED or scene often carries a constant offset; fixing one dense line breaks the next | M/L | high | Must be **modeful & opt-in**; main risk is undo/history correctness |
| **Ripple trim modes** for boundary edits: trim-only / steal-from-next / push-next / preserve-gap (Codex) | Dense dialogue creates chain reactions | M | high | Behavioral complexity → visibly modeful |

### 3.2 Audio / visual analysis aids
| Idea | Why | Effort | Value | Notes / risk |
|---|---|---|---|---|
| **VAD speech-activity lane** (backend-computed, cached), optionally a snap target (consensus — Codex's #1) | Anime mixes bury dialogue under BGM/SFX; raw peaks mislead | M | high | Foundation for later auto-trim/fix. **Lib choice matters:** `webrtcvad` (tiny C, RPi-safe) over `silero` (Torch, too heavy). Reuse existing marker/snap plumbing in `useWaveformRegions.ts` |
| **⭐ CPS / reading-speed diagnostics** in active-cue bar + cue list (both; Claude ranks higher) | Sublarr's core is EN→DE; German expands ~30% → lines become too fast even when sync is "correct" | S/M | high | Pure win, tiny perf, unique to Sublarr's translation DNA |
| **"Suspicious timing" markers**: cues crossing scene cuts, far from any keyframe, or starting/ending far from speech (Codex) | Anime errors cluster at cuts and quick turns | S/M | med/high | Keep subtle/filterable to avoid overlay clutter |

### 3.3 Automation / AI-assist
| Idea | Why | Effort | Value | Notes / risk |
|---|---|---|---|---|
| **One-click "fix safe defects"** for what `gapOverlap.ts` already detects (overlaps, tight gaps, too-short) (consensus) | The code already *finds* problems; users need "fix the clearly-safe ones", not just warnings | M | high | Low risk if scoped + preview/diff first |
| **Preview-able auto-trim to speech** for a cue or block (Codex) | Most retiming is shaving dead air / extending to last phoneme — repetitive, not creative | L | high | Depends on VAD quality; **diff/preview, never silent**. Defer until VAD lane exists |
| **Timing transfer** from a reference track / ASR-aligned source timings (Codex) | Workflows often start from a good-timed EN sub whose DE text changed | M/L | high | Backend complexity; keep as a targeted wizard. Defer until VAD lane exists |

### 3.4 Sublarr-specific integrations (Claude — not in Codex's list)
| Idea | Why | Effort | Value | Notes / risk |
|---|---|---|---|---|
| **⭐ Auto-sync override surface** — apply a global offset / "sync against audio" via the existing `ffsubsync`/`alass` engine, **including the shifts the sanity threshold rejects** | Observed real pain: prod logs show `ffsubsync: insane shift 50500ms (>45000ms threshold) — leaving sidecar untouched`. The user is then left with no assist. The waveform editor is exactly where a human can apply the large offset auto-sync refused | M | high | Reuses backend engine; needs a manual-confirm path around the sanity guard |
| **EN/DE side-by-side cue context** — show source + target text together in the cue lane/context strip | Sublarr often has the original EN sub; seeing both helps line-break & readability decisions | M | med/high | Additive strip; must not crowd the locked active-cue bar |

### 3.5 UX / ergonomics / discoverability
| Idea | Why | Effort | Value | Notes / risk |
|---|---|---|---|---|
| **Jump navigation** to prev/next keyframe, scene cut, defect marker, speech segment (Codex) | Turns passive overlays into navigable editing anchors | S/M | high | None |
| **Command palette** for waveform actions + hidden power features (Codex) | Hotkeys exist but advanced ops are undiscoverable | M | med/high | No layout disruption |
| **Prev/current/next cue context strip** (Codex) | Line-break & overlap choices depend on dialogue flow across cues | M | med/high | Additive secondary strip only |

### 3.6 Performance & robustness
| Idea | Why | Effort | Value | Notes / risk |
|---|---|---|---|---|
| **Server-side multi-resolution waveform-peaks cache** (Codex) | Long episodes on low-power NAS/RPi is exactly where client decode/render hurts | L | high | Extends the existing cached audio-extraction path; big payoff, backend/cache complexity |
| **Density culling** for overlays/markers at low zoom + cue-list virtualization pressure checks (Codex) | Keyframes, scenes, karaoke ticks, defect bars become DOM noise before they're useful | M | med/high | Detail must return when zoomed in |

### 3.7 Accessibility
| Idea | Why | Effort | Value | Notes / risk |
|---|---|---|---|---|
| **Keyboard-only boundary editing** with Alt/Shift precision steps (+ optional ripple modifiers) (Codex) | Helps accessibility *and* expert retiming speed | M | high | Avoid shortcut collisions |
| **Non-color quality encodings** + reduced-motion mode (disable smooth auto-scroll/scrub bursts) (Codex) | Current markers lean heavily on color; editors spend hours here | S/M | med/high | None |

---

## 4. Prioritized roadmap

Sequenced so cheap wins land first and the heavy AI features build on a proper
foundation rather than client-side DSP.

### Phase 1 — Quick wins (no new backend; existing plumbing)
- **CPS / reading-speed diagnostics** (⭐ fastest ROI, unique to Sublarr).
- **Jump-to-next**: keyframe / scene cut / defect marker.
- **One-click "fix safe defects"** (overlaps, tight gaps, too-short) with
  preview/diff — builds directly on `gapOverlap.ts`.
- **Loop audition** with pre-/post-roll.

### Phase 2 — Foundation
- **VAD speech-activity lane** (backend `webrtcvad`, cached per
  path/mtime/track, served like keyframes/scenes), optional snap target.
- **Server-side waveform-peaks cache** (parallel workstream; biggest low-power
  payoff).

### Phase 3 — Sublarr integrations
- **Auto-sync override** via existing `ffsubsync`/`alass`, incl. the
  sanity-rejected large shifts.
- **EN/DE side-by-side cue context.**

### Phase 4 — Automation on the foundation
- **Auto-trim to speech** (cue/block, preview-first).
- **Timing transfer** from reference/ASR-aligned source.
- **Ripple/block timing** modes (can also slot earlier if demand is high).

### Cross-cutting (fold into whichever phase touches the area)
- Command palette, prev/next cue context strip, density culling,
  keyboard-only boundary editing, non-color encodings + reduced-motion.

---

## 5. Highest-leverage picks

- **Codex's #1:** the **VAD lane** — it improves *every* manual edit and is the
  foundation for auto-trim/auto-fix without forcing client-side AI.
- **Claude's #1:** **CPS diagnostics** — same-week ROI, tiny surface, and it
  ties the editor to Sublarr's translation core (German expansion is a *timing*
  problem, not just a text one).
- **Resolution:** they are not in tension — CPS ships in Phase 1 while the VAD
  lane is built as the Phase 2 foundation. Both are on the critical path.

---

## 6. Open questions / dependencies

- **VAD library:** `webrtcvad` (tiny, CPU-only, RPi/NAS-safe) vs. a neural VAD
  (`silero`, better accuracy but Torch weight). Lean `webrtcvad` for the
  low-power baseline; revisit only if accuracy is insufficient.
- **Peaks cache format & storage:** where cached peaks live (alongside the
  extracted audio?), invalidation key, multi-resolution levels.
- **Auto-sync override:** how to expose a manual path around the
  `sync_sanity_threshold_ms` guard without weakening the automated pipeline's
  safety.
- **Undo model** for block/ripple ops — the existing undo stack must represent
  multi-cue transforms atomically.

## 7a. Progress log

**2026-07-19 — Phase 1 batch shipped (on master, not yet deployed):**
- ✅ CPS / reading-speed diagnostics — `readingSpeed.ts` + active-cue-bar badge
  + cue-list chip (`e810e2a9`).
- ✅ Jump navigation — `K/Shift+K` keyframe, `N/Shift+N` next/prev timing defect,
  new `waveformNavigation.ts` + `seekTo` on the hook (`45afc06f`).
- ✅ File-level issue-summary chip in the toolbar (counts overlaps / tight gaps /
  too-fast / too-short; click → jump to first) — `issueSummary.ts` (`f52d2c6f`).

Scene-cut jump also shipped (`C`/`Shift+C`, `a05a67a9`). Still open from Phase 1:
one-click "fix safe defects" (needs a batch-apply + undo path through
`SubtitleEditorModal`), loop audition (touches the hook's playback effect).

**2026-07-19 — Phase 2 (VAD foundation) shipped + verified on real anime:**
- ✅ Backend `services/speech_detector.py` (WebRTC VAD, pure aggregator) +
  `GET /audio/speech` (`295740ab`). No new dep — webrtcvad ships via ffsubsync.
- ✅ FE data layer `fetchSpeech`/`useSpeech` (`a54d55d6`) + opt-in green speech
  lane with the `Sprache` toggle (`8ee40674`, default OFF).
- ✅ Verified on Beta (standalone, real Oshi no Ko episode): 172 segments in
  1.1s, lane renders correctly, zero app errors. Also shipped: prominent
  loading state (`863e9783`).
- ✅ VAD snapping shipped (`9212c5f5`): fourth snap pool — cue boundary drags
  and L/R click-sets snap to speech-segment edges while the lane is on.
  Priority keyframe > speech > scene > neighbor, 120 ms default tolerance.
- Still open in Phase 2: server-side multi-resolution waveform-peaks cache
  (see the 2026-07-30 note below — measure before building).

**2026-07-30 — Third-pass review (Claude, code-verified):** additions and
re-weightings in section 8. Trust package (user-modified guard + draft
recovery) inserted ahead of the remaining Phase 1 items.

## 7. Explicitly NOT in scope

- ASS `\k` karaoke retiming (stays in Aegisub).
- Removing or hiding any of the seven locked surfaces.
- Heavy always-on client-side DSP.

---

## 8. Third-pass additions (2026-07-30, code-verified)

Gaps neither model caught in the 07-19 brainstorm, plus two re-weightings.
Verified against the code as of `9212c5f5`.

### 8.1 Trust package (new — do FIRST, before remaining Phase 1)

| Idea | Why | Effort | Value |
|---|---|---|---|
| **User-modified guard** — editor save marks the subtitle as hand-edited; the upgrade system skips (or warns on) replacing such files | The save endpoint already has optimistic concurrency (mtime check in `routes/tools/content.py`), but the *reverse* direction is open: a user hand-times for an hour, saves, and the upgrade scheduler later silently replaces the file with a "better" provider download. Same trust cluster as issue #159. | S/M | high |
| **Draft recovery** — persist dirty cue state / undo stack to browser storage keyed `(file, mtime)`, offer restore on reopen | `beforeunload` guard exists, but a browser crash or tab kill discards hours of work. This doc itself says "editors spend hours here". | S/M | high |

Rationale for ordering: every other editor feature *creates* manual work;
these two protect it. Ship them before generating more of it.

### 8.2 New feature ideas

| Idea | Why | Effort | Value |
|---|---|---|---|
| **Split-at-speech-gap assist** | CPS *diagnoses* "too fast" but the usual fix is splitting/rebreaking — no assist exists. VAD lane now provides the natural split point: one keystroke, split at the nearest speech gap inside the cue. Builds on existing split (F). | S/M | high |
| **Batch offset across episodes** | Anime batches from one release group share a constant offset. After a manual fix: "you shifted everything by +2.0 s — apply to the other 11 episodes?" (backend shift, preview list). Leverages one manual fix across the library; the 07-19 doc thinks strictly single-file. | M | high |
| **Post-MT review queue** | Subtitle-health already deep-links "open editor" per finding; the translation side has no equivalent. A queue of flagged cues (CPS violation, high expansion ratio, glossary miss) worked through in the editor is the concrete path for translation to graduate from "experimental". | M/L | high |

### 8.3 Re-weightings of the 07-19 plan

- **Peaks cache: measure before building.** The decode runs in the *user's
  browser*, not on the NAS — the NAS only does the (already cached) Opus
  extraction. And the spectrogram toggle needs raw audio client-side anyway,
  which erases the peaks benefit for spectrogram users. Measure editor open
  time on a realistic client first; expected to fall below auto-sync override
  in priority. ("Biggest low-power payoff" from 07-19 is likely overstated.)
- **VAD quality gate before Phase 4.** `webrtcvad` is energy-based and weak
  exactly where this doc says anime is hard (dialogue under BGM/SFX); it has
  been verified on one episode. Before auto-trim: build a small eval — a
  handful of hand-timed episodes as ground truth, measure boundary error.
  Middle path missed on 07-19: **Silero-VAD has an ONNX variant** (no Torch,
  CPU-friendly, a few MB) — fits the low-power constraint as an opt-in
  accuracy upgrade.

### 8.4 Revised order

1. Trust package (8.1) — small, protects the work everything else creates.
2. Remaining Phase 1 (loop audition, fix-safe-defects).
3. Auto-sync override (Phase 3) — best value/effort of the large features.
4. Split-at-speech-gap (8.2) — small, VAD is in place.
5. VAD eval, then Phase 4; peaks cache only after measurement.
