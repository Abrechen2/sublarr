/**
 * WaveformEditor — editable waveform surface for the SubtitleEditorModal.
 *
 * Plan B8 Task 3 entry point. Replaces the read-only WaveformTab.
 * Plan B8 Task 4 wires snap targets (keyframes via /api/v1/audio/keyframes)
 * and the Aegisub L/R click-map into the hook.
 * Plan B8 Task 5 adds Aegisub-style keyboard shortcuts and a `?` help
 * overlay; the editor owns the dispatcher and forwards higher-level
 * actions (split / merge / select prev|next cue) to the parent modal.
 *
 * Subsequent tasks (6–10) layer auto-scroll, zoom, spectrogram,
 * audio scrubbing and scene-markers on top.
 */

import { useRef, useState, useEffect, useMemo, useCallback } from 'react'
import {
  Loader2,
  Play,
  Pause,
  Lock,
  Unlock,
  Keyboard,
  Activity,
  Headphones,
  Film,
  Gauge,
  List as ListIcon,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useSubtitleParse, useKeyframes, useAudioTracks, useScenes } from '@/hooks/useApi'
import { extractWaveform } from '@/api/client'

import { useWaveformRegions, type CuePatch, type WaveformCue } from './useWaveformRegions'
import { WaveformHotkeys } from './WaveformHotkeys'
import { WaveformShortcutHelp } from './WaveformShortcutHelp'
import { WaveformAudioTrackPicker } from './WaveformAudioTrackPicker'
import { AssKaraokeOverlay } from './AssKaraokeOverlay'
import { WaveformActiveCueBar } from './WaveformActiveCueBar'
import { WaveformCueList, type SelectionOrigin } from './WaveformCueList'
import { formatCueTextForRegion } from './cueTextDisplay'
import type { WaveformAction } from './keymap'

interface WaveformEditorProps {
  subtitlePath: string
  videoPath: string
  /**
   * Drag-end callback. Receives the cue id (== index as string) and the new
   * start/end seconds. The parent merges into its canonical cue list.
   *
   * Optional: when omitted, the editor falls back to read-only mode so
   * existing call-sites keep working without breakage.
   */
  onCueChange?: (id: string, patch: CuePatch) => void
  /**
   * Currently selected cue index in the parent list (B8 Task 4). When
   * provided + edit-mode is on, L/R clicks on the waveform body set the
   * snapped start / end of this cue. `null` disables click-set.
   */
  selectedCueIdx?: number | null
  /**
   * Move the cue selection in the parent (B8 Task 5 — arrow Up/Down).
   * Called with `'prev' | 'next'`. The parent computes the new index
   * relative to the current list and emits it back via `selectedCueIdx`.
   */
  onSelectAdjacentCue?: (direction: 'prev' | 'next') => void
  /**
   * Set the absolute selection from inside the editor (Stacked-Lanes
   * cue-list click). When omitted, list rows still highlight visually
   * but clicks become no-ops.
   */
  onSelectCue?: (idx: number) => void
  /**
   * Split the selected cue at `splitTimeSec` (B8 Task 5 — `F` key).
   * Implementation lives in the modal; the editor only forwards the time.
   */
  onSplitCue?: (idx: number, splitTimeSec: number) => void
  /**
   * Merge the selected cue with the next one (B8 Task 5 — `G` key).
   */
  onMergeWithNext?: (idx: number) => void
}

/** Minimum cue duration enforced by the snap helper, in ms. */
const DEFAULT_MIN_GAP_MS = 80

/** Keyboard nudge: small step (arrow) and large step (shift+arrow) in seconds. */
const SMALL_NUDGE_S = 0.1
const LARGE_NUDGE_S = 1.0

/** Zoom slider bounds in pixels-per-second (Plan B8 Task 6). */
const ZOOM_MIN_PX_PER_SEC = 1
const ZOOM_MAX_PX_PER_SEC = 50
const ZOOM_DEFAULT_PX_PER_SEC = 10
/** Multiplicative step for `+/-` keyboard nudges. */
const ZOOM_STEP_FACTOR = 1.5

/** localStorage keys for persisted toolbar prefs. */
const SPECTROGRAM_LS_KEY = 'sublarr.waveform.spectrogram'
const SCRUB_LS_KEY = 'sublarr.waveform.scrub'
const KEYFRAMES_LS_KEY = 'sublarr.waveform.keyframes'
const AMP_ZOOM_LS_KEY = 'sublarr.waveform.ampZoom'
const PLAYBACK_RATE_LS_KEY = 'sublarr.waveform.playbackRate'
const CUE_LIST_COLLAPSED_LS_KEY = 'sublarr.waveform.cueListCollapsed'

/** Vertical amplitude (bar-height) zoom — 1× default, up to 5× for quiet audio. */
const AMP_MIN = 1
const AMP_MAX = 5
const AMP_DEFAULT = 1

/** Playback rate slider — 0.5× to 2.0×, default 1.0×. */
const RATE_MIN = 0.5
const RATE_MAX = 2.0
const RATE_DEFAULT = 1.0

function readNumberPref(key: string, fallback: number, min: number, max: number): number {
  if (typeof window === 'undefined') return fallback
  try {
    const v = window.localStorage.getItem(key)
    if (v === null) return fallback
    const n = Number(v)
    if (!Number.isFinite(n)) return fallback
    return Math.max(min, Math.min(max, n))
  } catch {
    return fallback
  }
}

function writeNumberPref(key: string, value: number): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, String(value))
  } catch {
    // Quota / privacy mode — silently fall back to in-memory only.
  }
}

function readBoolPref(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback
  try {
    const v = window.localStorage.getItem(key)
    if (v === null) return fallback
    return v === '1'
  } catch {
    return fallback
  }
}

function writeBoolPref(key: string, value: boolean): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value ? '1' : '0')
  } catch {
    // Quota / privacy mode — silently fall back to in-memory only.
  }
}

export function WaveformEditor({
  subtitlePath,
  videoPath,
  onCueChange,
  selectedCueIdx = null,
  onSelectAdjacentCue,
  onSelectCue,
  onSplitCue,
  onMergeWithNext,
}: WaveformEditorProps) {
  const { t } = useTranslation('editor')

  const containerRef = useRef<HTMLDivElement>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [extractError, setExtractError] = useState<string | null>(null)
  const [extractLoading, setExtractLoading] = useState(true)
  const [editingEnabled, setEditingEnabled] = useState<boolean>(Boolean(onCueChange))
  const [helpOpen, setHelpOpen] = useState(false)
  const [zoomPxPerSec, setZoomPxPerSec] = useState<number>(ZOOM_DEFAULT_PX_PER_SEC)
  const [autoCenter, setAutoCenter] = useState<boolean>(true)
  const [spectrogramEnabled, setSpectrogramEnabled] = useState<boolean>(() =>
    readBoolPref(SPECTROGRAM_LS_KEY, false),
  )
  const [scrubOnDrag, setScrubOnDrag] = useState<boolean>(() =>
    readBoolPref(SCRUB_LS_KEY, false),
  )
  const [showKeyframeMarkers, setShowKeyframeMarkers] = useState<boolean>(() =>
    readBoolPref(KEYFRAMES_LS_KEY, false),
  )
  const [ampZoom, setAmpZoom] = useState<number>(() =>
    readNumberPref(AMP_ZOOM_LS_KEY, AMP_DEFAULT, AMP_MIN, AMP_MAX),
  )
  const [playbackRate, setPlaybackRate] = useState<number>(() =>
    readNumberPref(PLAYBACK_RATE_LS_KEY, RATE_DEFAULT, RATE_MIN, RATE_MAX),
  )
  // 0-based audio-position to extract; the backend route picks `0:a:<idx>`.
  const [selectedAudioIdx, setSelectedAudioIdx] = useState<number>(0)
  // Stacked-Lanes layout: persisted collapse for the cue list under the wave.
  const [cueListCollapsed, setCueListCollapsed] = useState<boolean>(() =>
    readBoolPref(CUE_LIST_COLLAPSED_LS_KEY, false),
  )
  // Origin flag for bidirectional selection sync (Gemini + Codex consensus).
  // Reset to null after a tick so the NEXT selection change auto-scrolls.
  const [selectionOrigin, setSelectionOrigin] = useState<SelectionOrigin>(null)

  const toggleCueListCollapsed = useCallback(() => {
    setCueListCollapsed((cur) => {
      const next = !cur
      writeBoolPref(CUE_LIST_COLLAPSED_LS_KEY, next)
      return next
    })
  }, [])

  const handleListSelect = useCallback(
    (idx: number) => {
      setSelectionOrigin('list')
      onSelectCue?.(idx)
    },
    [onSelectCue],
  )

  // Reset origin so the next external selection change (keyboard / wave) is
  // treated as origin=null and the list auto-scrolls again.
  useEffect(() => {
    if (selectionOrigin === null) return
    const t = setTimeout(() => setSelectionOrigin(null), 200)
    return () => clearTimeout(t)
  }, [selectionOrigin])

  const toggleSpectrogram = useCallback(() => {
    setSpectrogramEnabled((cur) => {
      const next = !cur
      writeBoolPref(SPECTROGRAM_LS_KEY, next)
      return next
    })
  }, [])

  const toggleScrub = useCallback(() => {
    setScrubOnDrag((cur) => {
      const next = !cur
      writeBoolPref(SCRUB_LS_KEY, next)
      return next
    })
  }, [])

  const toggleKeyframeMarkers = useCallback(() => {
    setShowKeyframeMarkers((cur) => {
      const next = !cur
      writeBoolPref(KEYFRAMES_LS_KEY, next)
      return next
    })
  }, [])

  const updateAmpZoom = useCallback((value: number) => {
    setAmpZoom(value)
    writeNumberPref(AMP_ZOOM_LS_KEY, value)
  }, [])

  const updatePlaybackRate = useCallback((value: number) => {
    setPlaybackRate(value)
    writeNumberPref(PLAYBACK_RATE_LS_KEY, value)
  }, [])

  const { data: parseData } = useSubtitleParse(subtitlePath)
  const { data: keyframesData } = useKeyframes(videoPath || null)
  const { data: audioTracksData } = useAudioTracks(videoPath || null)
  const { data: scenesData } = useScenes(videoPath || null)
  const audioTracks = audioTracksData?.tracks ?? []

  // Convert parsed cues -> stable WaveformCue array for the hook.
  // `label` powers the in-region text overlay (Plan B8 follow-up).
  const cues = useMemo<WaveformCue[]>(
    () =>
      (parseData?.cues ?? []).map((cue, idx) => ({
        id: String(idx),
        start: cue.start,
        end: cue.end,
        label: formatCueTextForRegion(cue.text),
      })),
    [parseData],
  )

  // Keyframes come from the backend in seconds; the hook works in ms.
  const keyframesMs = useMemo<number[]>(
    () => (keyframesData?.keyframes ?? []).map((s) => s * 1000),
    [keyframesData],
  )

  // Scene-detection markers (Plan B8 Task 10). Backend may report
  // `available: false` when PySceneDetect isn't installed — we just
  // see an empty list there, so no further guard is needed.
  const sceneMarkersMs = useMemo<number[]>(
    () => (scenesData?.scenes ?? []).map((s) => s * 1000),
    [scenesData],
  )

  const selectedCueId = selectedCueIdx === null ? null : String(selectedCueIdx)

  // Default no-op — when caller doesn't pass onCueChange, drag is disabled
  // anyway, but the hook still wants a function.
  const noopCueChange = useCallback(() => {}, [])

  const {
    ws,
    isReady,
    isPlaying,
    playPause,
    setStartAtPlayhead,
    setEndAtPlayhead,
    seekBy,
  } = useWaveformRegions({
    container: containerRef,
    audioUrl,
    cues,
    onCueChange: onCueChange ?? noopCueChange,
    enableDrag: editingEnabled && Boolean(onCueChange),
    selectedCueId,
    keyframesMs,
    minGapMs: DEFAULT_MIN_GAP_MS,
    zoomPxPerSec,
    autoCenter,
    spectrogramEnabled,
    scrubOnDrag,
    sceneMarkersMs,
    showKeyframeMarkers,
    ampZoom,
    playbackRate,
  })

  // Multiplicative zoom step, clamped to the slider bounds. Used by the
  // `+/-` keyboard shortcuts so the zoom-in/out feel matches Aegisub's
  // exponential scale rather than a linear nudge.
  const stepZoom = useCallback((dir: 'in' | 'out') => {
    setZoomPxPerSec((cur) => {
      const next = dir === 'in' ? cur * ZOOM_STEP_FACTOR : cur / ZOOM_STEP_FACTOR
      return Math.max(ZOOM_MIN_PX_PER_SEC, Math.min(ZOOM_MAX_PX_PER_SEC, next))
    })
  }, [])

  // Trigger backend audio extraction whenever the video or selected audio
  // track changes. The backend caches per (path, mtime, track_index) so
  // round-trips are cheap once each track has been extracted at least once.
  useEffect(() => {
    if (!videoPath) return
    let cancelled = false
    setExtractLoading(true)
    setExtractError(null)
    // Only pass track_index when more than one track is known — the
    // single-track case lets ffmpeg pick its default audio stream and
    // keeps cache keys aligned with pre-Task-6 entries.
    const trackArg = audioTracks.length > 1 ? selectedAudioIdx : undefined
    extractWaveform(videoPath, trackArg)
      .then(({ audio_url }) => {
        if (cancelled) return
        setAudioUrl(audio_url)
        setExtractLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const msg = err instanceof Error ? err.message : 'Audio konnte nicht extrahiert werden.'
        setExtractError(msg)
        setExtractLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [videoPath, selectedAudioIdx, audioTracks.length])

  // Keyboard dispatcher (Plan B8 Task 5) — central place to wire each
  // hotkey id onto a concrete behavior. Stay defensive: each branch
  // checks the prerequisites it needs (selected cue, callback, etc) and
  // silently no-ops otherwise so the user isn't surprised by partial UX.
  const handleAction = useCallback(
    (action: WaveformAction) => {
      switch (action) {
        case 'playPause':
          playPause()
          return
        case 'setStart':
          setStartAtPlayhead()
          return
        case 'setEnd':
          setEndAtPlayhead()
          return
        case 'splitAtCursor':
          if (selectedCueIdx !== null && onSplitCue && ws) {
            onSplitCue(selectedCueIdx, ws.getCurrentTime())
          }
          return
        case 'mergeWithNext':
          if (selectedCueIdx !== null && onMergeWithNext) {
            onMergeWithNext(selectedCueIdx)
          }
          return
        case 'seekBack100ms':
          seekBy(-SMALL_NUDGE_S)
          return
        case 'seekFwd100ms':
          seekBy(SMALL_NUDGE_S)
          return
        case 'seekBack1s':
          seekBy(-LARGE_NUDGE_S)
          return
        case 'seekFwd1s':
          seekBy(LARGE_NUDGE_S)
          return
        case 'prevCue':
          onSelectAdjacentCue?.('prev')
          return
        case 'nextCue':
          onSelectAdjacentCue?.('next')
          return
        case 'zoomIn':
          stepZoom('in')
          return
        case 'zoomOut':
          stepZoom('out')
          return
        case 'showHelp':
          setHelpOpen(true)
          return
      }
    },
    [
      ws,
      playPause,
      setStartAtPlayhead,
      setEndAtPlayhead,
      seekBy,
      selectedCueIdx,
      onSplitCue,
      onMergeWithNext,
      onSelectAdjacentCue,
      stepZoom,
    ],
  )

  // Project parsed cues to the read-only shape the cue list expects.
  // Memoised here (BEFORE any conditional return) so the hook order stays
  // stable across renders.
  const cueListRows = useMemo(
    () =>
      (parseData?.cues ?? []).map((c) => ({
        start: c.start,
        end: c.end,
        text: c.text,
      })),
    [parseData],
  )

  if (extractError) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-error">{extractError}</p>
      </div>
    )
  }

  const showSpinner = extractLoading || (audioUrl !== null && !isReady)

  // Stacked-Lanes layout (gold-standard follow-up): toolbar lives above the
  // active-cue card so the bottom half of the modal is the actual editing
  // zone (Welle + Cue-Liste). Toolbar JSX is extracted into a local var so
  // the spinner-gate is the only branch and there are no DOM order surprises
  // between renders.
  const toolbar = (
    <div className="flex items-center gap-3 flex-wrap">
      <button
        type="button"
        onClick={playPause}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors bg-accent-bg text-accent border border-accent-dim"
      >
        {isPlaying ? <Pause size={12} /> : <Play size={12} />}
        {isPlaying ? 'Pause' : 'Play'}
      </button>

      {onCueChange && (
        <button
          type="button"
          onClick={() => setEditingEnabled((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors bg-surface text-primary border border-border"
          title={
            editingEnabled
              ? 'Editing — drag region edges to retime cues'
              : 'Read-only — toggle to enable drag-edit'
          }
        >
          {editingEnabled ? <Unlock size={12} /> : <Lock size={12} />}
          {editingEnabled ? 'Edit' : 'Locked'}
        </button>
      )}

      <button
        type="button"
        onClick={() => setHelpOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors bg-surface text-primary border border-border"
        title={t('waveform.shortcut.title')}
      >
        <Keyboard size={12} />
        {t('waveform.shortcut_help_button')}
      </button>

      <button
        type="button"
        onClick={toggleSpectrogram}
        aria-pressed={spectrogramEnabled}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors border ${
          spectrogramEnabled
            ? 'bg-accent-bg text-accent border-accent-dim'
            : 'bg-surface text-primary border-border'
        }`}
        title="Spectrogram"
      >
        <Activity size={12} />
        Spectrogram
      </button>

      <button
        type="button"
        onClick={toggleScrub}
        aria-pressed={scrubOnDrag}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors border ${
          scrubOnDrag
            ? 'bg-accent-bg text-accent border-accent-dim'
            : 'bg-surface text-primary border-border'
        }`}
        title="Audio scrubbing while dragging"
      >
        <Headphones size={12} />
        Scrub
      </button>

      <button
        type="button"
        onClick={toggleKeyframeMarkers}
        aria-pressed={showKeyframeMarkers}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors border ${
          showKeyframeMarkers
            ? 'bg-accent-bg text-accent border-accent-dim'
            : 'bg-surface text-primary border-border'
        }`}
        title="Keyframe-Marker einblenden"
      >
        <Film size={12} />
        Keyframes
      </button>

      <button
        type="button"
        onClick={toggleCueListCollapsed}
        aria-pressed={!cueListCollapsed}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors border ${
          !cueListCollapsed
            ? 'bg-accent-bg text-accent border-accent-dim'
            : 'bg-surface text-primary border-border'
        }`}
        title={cueListCollapsed ? 'Cue-Liste einblenden' : 'Cue-Liste einklappen — mehr Welle'}
      >
        <ListIcon size={12} />
        Liste
      </button>

      <label className="flex items-center gap-1.5 text-xs text-muted">
        <span aria-hidden="true">−</span>
        <input
          type="range"
          min={ZOOM_MIN_PX_PER_SEC}
          max={ZOOM_MAX_PX_PER_SEC}
          step={1}
          value={zoomPxPerSec}
          onChange={(e) => setZoomPxPerSec(Number(e.target.value))}
          aria-label="Zoom"
          className="w-24 accent-accent"
        />
        <span aria-hidden="true">+</span>
        <span className="tabular-nums w-9 text-right">{zoomPxPerSec}</span>
      </label>

      <label
        className="flex items-center gap-1.5 text-xs text-muted"
        title="Vertikale Amplituden-Lupe (1×–5×) — für leise Dialoge"
      >
        <Activity size={12} aria-hidden="true" />
        <input
          type="range"
          min={AMP_MIN}
          max={AMP_MAX}
          step={0.1}
          value={ampZoom}
          onChange={(e) => updateAmpZoom(Number(e.target.value))}
          aria-label="Amplitude zoom"
          className="w-20 accent-accent"
        />
        <span className="tabular-nums w-10 text-right">{ampZoom.toFixed(1)}×</span>
      </label>

      <label
        className="flex items-center gap-1.5 text-xs text-muted"
        title="Wiedergabe-Geschwindigkeit (Tonhöhe bleibt erhalten)"
      >
        <Gauge size={12} aria-hidden="true" />
        <input
          type="range"
          min={RATE_MIN}
          max={RATE_MAX}
          step={0.05}
          value={playbackRate}
          onChange={(e) => updatePlaybackRate(Number(e.target.value))}
          aria-label="Playback rate"
          className="w-20 accent-accent"
        />
        <span className="tabular-nums w-12 text-right">{playbackRate.toFixed(2)}×</span>
      </label>

      <label className="flex items-center gap-1.5 text-xs text-muted">
        <input
          type="checkbox"
          checked={autoCenter}
          onChange={(e) => setAutoCenter(e.target.checked)}
          className="accent-accent"
        />
        Auto-center
      </label>

      <WaveformAudioTrackPicker
        tracks={audioTracks}
        selectedAudioIdx={selectedAudioIdx}
        onChange={setSelectedAudioIdx}
      />

      {parseData && (
        <span className="text-xs text-muted">
          {parseData.cue_count} Cues · {parseData.format.toUpperCase()}
        </span>
      )}

      {editingEnabled && selectedCueIdx !== null && keyframesData && (
        <span className="text-xs text-muted">
          Snap: {keyframesData.keyframes.length} keyframes
        </span>
      )}

      {scenesData && scenesData.available && sceneMarkersMs.length > 0 && (
        <span className="text-xs text-muted">
          {sceneMarkersMs.length} scene cuts
        </span>
      )}
    </div>
  )

  return (
    <div className="flex flex-col gap-3 p-4">
      {showSpinner && (
        <div className="flex items-center gap-2 text-sm text-muted">
          <Loader2 size={14} className="animate-spin" />
          {extractLoading ? 'Audio wird extrahiert…' : 'Wellenform wird gezeichnet…'}
        </div>
      )}

      {!showSpinner && toolbar}

      <WaveformActiveCueBar
        cueIndex={selectedCueIdx}
        cueCount={parseData?.cue_count ?? 0}
        startSec={
          selectedCueIdx !== null && parseData?.cues[selectedCueIdx]
            ? parseData.cues[selectedCueIdx].start
            : 0
        }
        endSec={
          selectedCueIdx !== null && parseData?.cues[selectedCueIdx]
            ? parseData.cues[selectedCueIdx].end
            : 0
        }
        text={
          selectedCueIdx !== null && parseData?.cues[selectedCueIdx]
            ? parseData.cues[selectedCueIdx].text
            : ''
        }
      />

      <div className="relative rounded overflow-hidden bg-primary border border-border">
        <div ref={containerRef} />
        {parseData?.format === 'ass' &&
          selectedCueIdx !== null &&
          parseData.cues[selectedCueIdx]?.syllables &&
          parseData.cues[selectedCueIdx].syllables!.length > 0 &&
          parseData.total_duration > 0 && (
            <AssKaraokeOverlay
              syllables={parseData.cues[selectedCueIdx].syllables!}
              cueStartSec={parseData.cues[selectedCueIdx].start}
              durationSec={parseData.total_duration}
            />
          )}
      </div>

      {parseData && (
        <WaveformCueList
          cues={cueListRows}
          selectedCueIdx={selectedCueIdx}
          selectionOrigin={selectionOrigin}
          onSelectCue={handleListSelect}
          collapsed={cueListCollapsed}
          visibleRows={5}
        />
      )}

      <WaveformHotkeys enabled={isReady && !helpOpen} onAction={handleAction} />
      <WaveformShortcutHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  )
}

