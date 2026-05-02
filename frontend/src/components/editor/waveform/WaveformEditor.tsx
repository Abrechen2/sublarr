/**
 * WaveformEditor — editable waveform surface for the SubtitleEditorModal.
 *
 * Plan B8 Task 3 entry point. Replaces the read-only WaveformTab.
 * Plan B8 Task 4 wires snap targets (keyframes via /api/v1/audio/keyframes)
 * and the Aegisub L/R click-map into the hook.
 *
 * Subsequent tasks (5–10) layer keyboard shortcuts, auto-scroll, zoom,
 * spectrogram and scene-markers on top.
 */

import { useRef, useState, useEffect, useMemo, useCallback } from 'react'
import { Loader2, Play, Pause, Lock, Unlock } from 'lucide-react'

import { useSubtitleParse, useKeyframes } from '@/hooks/useApi'
import { extractWaveform } from '@/api/client'

import { useWaveformRegions, type CuePatch, type WaveformCue } from './useWaveformRegions'

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
}

/** Minimum cue duration enforced by the snap helper, in ms. */
const DEFAULT_MIN_GAP_MS = 80

export function WaveformEditor({
  subtitlePath,
  videoPath,
  onCueChange,
  selectedCueIdx = null,
}: WaveformEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [extractError, setExtractError] = useState<string | null>(null)
  const [extractLoading, setExtractLoading] = useState(true)
  const [editingEnabled, setEditingEnabled] = useState<boolean>(Boolean(onCueChange))

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

  const { isReady, isPlaying, playPause } = useWaveformRegions({
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
    </div>
  )
}
