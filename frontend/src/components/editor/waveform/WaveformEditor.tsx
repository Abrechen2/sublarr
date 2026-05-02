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
import { Loader2, Play, Pause, Lock, Unlock, Keyboard } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useSubtitleParse, useKeyframes } from '@/hooks/useApi'
import { extractWaveform } from '@/api/client'

import { useWaveformRegions, type CuePatch, type WaveformCue } from './useWaveformRegions'
import { WaveformHotkeys } from './WaveformHotkeys'
import { WaveformShortcutHelp } from './WaveformShortcutHelp'
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

export function WaveformEditor({
  subtitlePath,
  videoPath,
  onCueChange,
  selectedCueIdx = null,
  onSelectAdjacentCue,
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

  const { data: parseData } = useSubtitleParse(subtitlePath)
  const { data: keyframesData } = useKeyframes(videoPath || null)

  // Convert parsed cues -> stable WaveformCue array for the hook
  const cues = useMemo<WaveformCue[]>(
    () =>
      (parseData?.cues ?? []).map((cue, idx) => ({
        id: String(idx),
        start: cue.start,
        end: cue.end,
      })),
    [parseData],
  )

  // Keyframes come from the backend in seconds; the hook works in ms.
  const keyframesMs = useMemo<number[]>(
    () => (keyframesData?.keyframes ?? []).map((s) => s * 1000),
    [keyframesData],
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
  })

  // Trigger backend audio extraction once per video
  useEffect(() => {
    if (!videoPath) return
    let cancelled = false
    setExtractLoading(true)
    setExtractError(null)
    extractWaveform(videoPath)
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
  }, [videoPath])

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
        case 'zoomOut':
          // Wired in B8 Task 6 (zoom). No-op for now.
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
    ],
  )

  if (extractError) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-error">{extractError}</p>
      </div>
    )
  }

  const showSpinner = extractLoading || (audioUrl !== null && !isReady)

  return (
    <div className="flex flex-col gap-3 p-4">
      {showSpinner && (
        <div className="flex items-center gap-2 text-sm text-muted">
          <Loader2 size={14} className="animate-spin" />
          {extractLoading ? 'Audio wird extrahiert…' : 'Wellenform wird gezeichnet…'}
        </div>
      )}

      <div
        ref={containerRef}
        className="rounded overflow-hidden bg-primary border border-border"
      />

      {!showSpinner && (
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
        </div>
      )}

      <WaveformHotkeys enabled={isReady && !helpOpen} onAction={handleAction} />
      <WaveformShortcutHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  )
}
