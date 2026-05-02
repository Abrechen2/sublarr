/**
 * useWaveformRegions — owns the WaveSurfer + Regions-plugin lifecycle.
 *
 * Plan B8 Task 3 — promotes the read-only WaveformTab into an editing
 * surface. The hook exposes drag/resize-able regions and commits cue
 * changes to the parent only on drag-END (not per-frame), with a
 * `dragging` ref that freezes incoming prop-driven region rewrites
 * mid-drag so React state updates don't snap regions back.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import WaveSurfer from 'wavesurfer.js'
import RegionsPlugin from 'wavesurfer.js/plugins/regions'

export interface WaveformCue {
  /** Stable identifier — typically the cue index in the parent list. */
  id: string
  /** Start time in seconds. */
  start: number
  /** End time in seconds. */
  end: number
}

export type CuePatch = Pick<WaveformCue, 'start' | 'end'>

export interface UseWaveformRegionsArgs {
  container: React.RefObject<HTMLDivElement | null>
  audioUrl: string | null
  cues: WaveformCue[]
  onCueChange: (id: string, patch: CuePatch) => void
  /** When false, regions render but cannot be moved (read-only mode). */
  enableDrag?: boolean
  /** Color for region fill (default teal-low-opacity). */
  regionColor?: string
  /** Wave color (default zinc-600). */
  waveColor?: string
  /** Progress color (default teal-500). */
  progressColor?: string
  /** Height in pixels (default 96). */
  height?: number
}

export interface UseWaveformRegionsResult {
  ws: WaveSurfer | null
  regions: RegionsPlugin | null
  isReady: boolean
  isPlaying: boolean
  play: () => void
  pause: () => void
  playPause: () => void
}

const DEFAULT_REGION_COLOR = 'rgba(20, 184, 166, 0.18)' // teal-500 @ 18 %
const DEFAULT_WAVE_COLOR = '#52525b' // zinc-600
const DEFAULT_PROGRESS_COLOR = '#14b8a6' // teal-500

export function useWaveformRegions({
  container,
  audioUrl,
  cues,
  onCueChange,
  enableDrag = true,
  regionColor = DEFAULT_REGION_COLOR,
  waveColor = DEFAULT_WAVE_COLOR,
  progressColor = DEFAULT_PROGRESS_COLOR,
  height = 96,
}: UseWaveformRegionsArgs): UseWaveformRegionsResult {
  const wsRef = useRef<WaveSurfer | null>(null)
  const regionsRef = useRef<RegionsPlugin | null>(null)
  const draggingRef = useRef<boolean>(false)
  const onCueChangeRef = useRef(onCueChange)
  // Keep latest callback without re-running the WaveSurfer effect on every render
  onCueChangeRef.current = onCueChange

  const [isReady, setIsReady] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)

  // Lifecycle: create WaveSurfer when the audio source is ready.
  useEffect(() => {
    if (!container.current || !audioUrl) return

    const regionsPlugin = RegionsPlugin.create()
    regionsRef.current = regionsPlugin

    const ws = WaveSurfer.create({
      container: container.current,
      waveColor,
      progressColor,
      height,
      plugins: [regionsPlugin],
    })
    wsRef.current = ws

    const onPlay = () => setIsPlaying(true)
    const onPause = () => setIsPlaying(false)
    const onFinish = () => setIsPlaying(false)
    const onReady = () => setIsReady(true)

    ws.on('play', onPlay)
    ws.on('pause', onPause)
    ws.on('finish', onFinish)
    ws.on('ready', onReady)

    // region-update fires per-frame during drag; flip the freeze flag
    // so the prop-sync effect doesn't overwrite the in-progress drag
    const onRegionUpdate = (region: { id: string }) => {
      void region
      draggingRef.current = true
    }
    // region-update-end fires on mouseup; commit the change and unfreeze
    const onRegionUpdateEnd = (region: { id: string; start: number; end: number }) => {
      draggingRef.current = false
      onCueChangeRef.current(region.id, { start: region.start, end: region.end })
    }

    regionsPlugin.on('region-update', onRegionUpdate)
    regionsPlugin.on('region-updated', onRegionUpdateEnd)

    void ws.load(audioUrl)

    return () => {
      ws.un('play', onPlay)
      ws.un('pause', onPause)
      ws.un('finish', onFinish)
      ws.un('ready', onReady)
      regionsPlugin.un('region-update', onRegionUpdate)
      regionsPlugin.un('region-updated', onRegionUpdateEnd)
      ws.destroy()
      wsRef.current = null
      regionsRef.current = null
      setIsReady(false)
      setIsPlaying(false)
    }
  }, [container, audioUrl, waveColor, progressColor, height])

  // Sync cues -> regions whenever the cue list changes, BUT only when
  // we're not in the middle of a drag. Mid-drag rewrites would snap the
  // dragged region back to its pre-drag position.
  useEffect(() => {
    const regions = regionsRef.current
    if (!regions || !isReady) return
    if (draggingRef.current) return

    regions.clearRegions()
    cues.forEach((cue) => {
      regions.addRegion({
        id: cue.id,
        start: cue.start,
        end: cue.end,
        color: regionColor,
        drag: enableDrag,
        resize: enableDrag,
      })
    })
  }, [cues, isReady, enableDrag, regionColor])

  const play = useCallback(() => {
    void wsRef.current?.play()
  }, [])
  const pause = useCallback(() => {
    wsRef.current?.pause()
  }, [])
  const playPause = useCallback(() => {
    void wsRef.current?.playPause()
  }, [])

  return {
    ws: wsRef.current,
    regions: regionsRef.current,
    isReady,
    isPlaying,
    play,
    pause,
    playPause,
  }
}
