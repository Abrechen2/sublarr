/**
 * useWaveformRegions — owns the WaveSurfer + Regions-plugin lifecycle.
 *
 * Plan B8 Task 3 — promotes the read-only WaveformTab into an editing
 * surface. Drag-end commits cue changes to the parent (not per-frame),
 * with a `dragging` ref that freezes incoming prop-driven region rewrites
 * mid-drag so React state updates don't snap regions back.
 *
 * Plan B8 Task 4 — adds Aegisub-style snap and L/R click-map:
 *   - On `region-updated` (drag-end): the moved boundary is snapped to
 *     the closest in-range keyframe or neighbor cue. Whole-region drags
 *     preserve duration (snap start, slide end).
 *   - L-click on the waveform body sets the snapped start of the
 *     currently selected cue; R-click sets the end. Clamped against
 *     `minGapMs` so the cue cannot invert or collapse.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import WaveSurfer from 'wavesurfer.js'
import RegionsPlugin from 'wavesurfer.js/plugins/regions'
import SpectrogramPlugin from 'wavesurfer.js/plugins/spectrogram'

import { snap, type SnapOptions } from './snap'

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
  /**
   * Currently selected cue. When set + `enableDrag` is true, L-click on the
   * waveform body sets that cue's snapped start, R-click sets its snapped
   * end. When null/undefined, clicks fall through to WaveSurfer defaults.
   */
  selectedCueId?: string | null
  /** Keyframe positions in milliseconds. Default: empty. */
  keyframesMs?: number[]
  /** Minimum gap to a neighbor cue after snap, in ms. Default: 0 (off). */
  minGapMs?: number
  /** Snap range around a keyframe, in ms. Default: 150. */
  keyframeToleranceMs?: number
  /** Snap range around a neighbor, in ms. Default: 80. */
  neighborToleranceMs?: number
  /** Color for region fill (default teal-low-opacity). */
  regionColor?: string
  /** Wave color (default zinc-600). */
  waveColor?: string
  /** Progress color (default teal-500). */
  progressColor?: string
  /** Height in pixels (default 96). */
  height?: number
  /**
   * Pixels-per-second zoom level (Plan B8 Task 6). When set, the value is
   * applied via `ws.zoom()` once WaveSurfer is ready and again on every
   * subsequent change, driving the toolbar slider + `+/-` shortcuts.
   */
  zoomPxPerSec?: number
  /**
   * Forwarded to WaveSurfer's `autoCenter` option (Plan B8 Task 6). When
   * true, the waveform pans to keep the playhead centered while playing.
   */
  autoCenter?: boolean
  /**
   * Show a spectrogram overlay (Plan B8 Task 7). The plugin registers
   * lazily when the flag flips true and unregisters when it flips back.
   * Default fft size is 512 (cheap enough for live editing).
   */
  spectrogramEnabled?: boolean
  /** FFT size for the spectrogram. Must be a power of 2. Default 512. */
  spectrogramFftSamples?: number
  /**
   * When true, dragging a region edge plays a short audio window at the
   * moving boundary so the user can hear what they're aligning to (Plan
   * B8 Task 8). Throttled internally to ~30 Hz.
   */
  scrubOnDrag?: boolean
  /** Length of the scrub-playback window in seconds. Default 0.2. */
  scrubWindowSec?: number
  /**
   * PySceneDetect scene-cut markers in milliseconds (Plan B8 Task 10).
   * Rendered as thin vertical lines on the waveform wrapper AND used as a
   * snap target (B8 follow-up). When empty or undefined, no markers are
   * drawn and snap-to-scene is disabled.
   */
  sceneMarkersMs?: number[]
  /** Snap range around a scene cut, in ms. Default 200. */
  sceneToleranceMs?: number
}

export interface UseWaveformRegionsResult {
  ws: WaveSurfer | null
  regions: RegionsPlugin | null
  isReady: boolean
  isPlaying: boolean
  play: () => void
  pause: () => void
  playPause: () => void
  /**
   * Snap-and-set the selected cue's start to the current playhead. Used by
   * the keyboard `S` hotkey (Aegisub convention).
   */
  setStartAtPlayhead: () => void
  /** Snap-and-set the selected cue's end to the current playhead (`D` key). */
  setEndAtPlayhead: () => void
  /** Seek the playhead by `deltaSec` seconds; negative means back. */
  seekBy: (deltaSec: number) => void
}

const DEFAULT_REGION_COLOR = 'rgba(20, 184, 166, 0.18)' // teal-500 @ 18 %
const DEFAULT_WAVE_COLOR = '#52525b' // zinc-600
const DEFAULT_PROGRESS_COLOR = '#14b8a6' // teal-500

/** Tolerance for "did this boundary actually move?" — 1 ms in seconds. */
const EDGE_EPSILON_S = 1e-3

/** All neighbor-boundary positions in ms, excluding the cue we're editing. */
function deriveNeighborsMs(cues: WaveformCue[], excludingId: string | null | undefined): number[] {
  const out: number[] = []
  for (const cue of cues) {
    if (cue.id === excludingId) continue
    out.push(cue.start * 1000, cue.end * 1000)
  }
  return out
}

export function useWaveformRegions({
  container,
  audioUrl,
  cues,
  onCueChange,
  enableDrag = true,
  selectedCueId = null,
  keyframesMs,
  minGapMs,
  keyframeToleranceMs,
  neighborToleranceMs,
  regionColor = DEFAULT_REGION_COLOR,
  waveColor = DEFAULT_WAVE_COLOR,
  progressColor = DEFAULT_PROGRESS_COLOR,
  height = 96,
  zoomPxPerSec,
  autoCenter,
  spectrogramEnabled = false,
  spectrogramFftSamples = 512,
  scrubOnDrag = false,
  scrubWindowSec = 0.2,
  sceneMarkersMs,
  sceneToleranceMs,
}: UseWaveformRegionsArgs): UseWaveformRegionsResult {
  const wsRef = useRef<WaveSurfer | null>(null)
  const regionsRef = useRef<RegionsPlugin | null>(null)
  const draggingRef = useRef<boolean>(false)

  // Keep latest values without re-running the WaveSurfer effect on every
  // render. The drag-end commit + click-map handlers read from these refs
  // so listeners stay attached for the WaveSurfer lifetime.
  const onCueChangeRef = useRef(onCueChange)
  onCueChangeRef.current = onCueChange
  const cuesRef = useRef(cues)
  cuesRef.current = cues
  const keyframesMsRef = useRef(keyframesMs)
  keyframesMsRef.current = keyframesMs
  const minGapMsRef = useRef(minGapMs)
  minGapMsRef.current = minGapMs
  const keyframeTolRef = useRef(keyframeToleranceMs)
  keyframeTolRef.current = keyframeToleranceMs
  const neighborTolRef = useRef(neighborToleranceMs)
  neighborTolRef.current = neighborToleranceMs
  // Scene markers are also a snap target (scene-snap follow-up). Same ref
  // pattern as the other tolerance/data refs so the long-lived listeners
  // pick up the latest value without re-attaching.
  const scenesMsRef = useRef(sceneMarkersMs)
  scenesMsRef.current = sceneMarkersMs
  const sceneTolRef = useRef(sceneToleranceMs)
  sceneTolRef.current = sceneToleranceMs
  const selectedCueIdRef = useRef(selectedCueId)
  selectedCueIdRef.current = selectedCueId
  // Scrub-on-drag inputs read inside the long-lived region-update listener
  const scrubOnDragRef = useRef(scrubOnDrag)
  scrubOnDragRef.current = scrubOnDrag
  const scrubWindowSecRef = useRef(scrubWindowSec)
  scrubWindowSecRef.current = scrubWindowSec
  // Last scrub timestamp (ms epoch); used by the throttle gate.
  const lastScrubAtRef = useRef<number>(0)

  const [isReady, setIsReady] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)

  /** Build SnapOptions for a given cue id (excluded from neighbors). */
  const buildSnapOpts = useCallback((excludingId: string | null | undefined): SnapOptions => {
    return {
      keyframesMs: keyframesMsRef.current ?? [],
      neighborsMs: deriveNeighborsMs(cuesRef.current, excludingId),
      scenesMs: scenesMsRef.current ?? [],
      minGapMs: minGapMsRef.current ?? 0,
      keyframeToleranceMs: keyframeTolRef.current,
      neighborToleranceMs: neighborTolRef.current,
      sceneToleranceMs: sceneTolRef.current,
    }
  }, [])

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
    const onRegionUpdate = (region: { id: string; start: number; end: number }) => {
      draggingRef.current = true

      // Plan B8 Task 8 — scrub-playback gate. Skipped silently when
      // disabled or when the throttle window hasn't elapsed.
      if (!scrubOnDragRef.current) return

      const now = Date.now()
      const SCRUB_THROTTLE_MS = 33 // ~30 Hz
      if (now - lastScrubAtRef.current < SCRUB_THROTTLE_MS) return
      lastScrubAtRef.current = now

      // Determine which boundary moved so we play around the edge the
      // user is currently dragging — not the cue's other side.
      const prev = cuesRef.current.find((c) => c.id === region.id)
      const win = scrubWindowSecRef.current

      let from = region.start
      let to = region.start + win
      if (prev) {
        const startMoved = Math.abs(region.start - prev.start) > EDGE_EPSILON_S
        const endMoved = Math.abs(region.end - prev.end) > EDGE_EPSILON_S
        if (endMoved && !startMoved) {
          from = Math.max(0, region.end - win)
          to = region.end
        }
      }
      void wsRef.current?.play(from, to)
    }
    // region-updated fires on mouseup; snap, commit, unfreeze.
    const onRegionUpdateEnd = (region: { id: string; start: number; end: number }) => {
      draggingRef.current = false

      const prev = cuesRef.current.find((c) => c.id === region.id)
      // No previous state to compare against — commit raw values.
      if (!prev) {
        onCueChangeRef.current(region.id, { start: region.start, end: region.end })
        return
      }

      const startMoved = Math.abs(region.start - prev.start) > EDGE_EPSILON_S
      const endMoved = Math.abs(region.end - prev.end) > EDGE_EPSILON_S
      if (!startMoved && !endMoved) return

      const opts = buildSnapOpts(region.id)
      const startDelta = region.start - prev.start
      const endDelta = region.end - prev.end
      const wholeDrag = startMoved && endMoved && Math.abs(startDelta - endDelta) < EDGE_EPSILON_S

      let newStart = region.start
      let newEnd = region.end

      if (wholeDrag) {
        // Snap the start, slide the end so the duration is preserved.
        const snappedStartMs = snap(region.start * 1000, opts).value
        const dur = prev.end - prev.start
        newStart = snappedStartMs / 1000
        newEnd = newStart + dur
      } else {
        if (startMoved) newStart = snap(region.start * 1000, opts).value / 1000
        if (endMoved) newEnd = snap(region.end * 1000, opts).value / 1000
      }

      onCueChangeRef.current(region.id, { start: newStart, end: newEnd })
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
  }, [container, audioUrl, waveColor, progressColor, height, buildSnapOpts])

  // Apply zoom level (px/s) once WaveSurfer is ready and on subsequent
  // changes. Skipped silently when undefined so the WaveSurfer default
  // stays in effect.
  useEffect(() => {
    if (!isReady) return
    if (zoomPxPerSec === undefined) return
    wsRef.current?.zoom(zoomPxPerSec)
  }, [isReady, zoomPxPerSec])

  // Forward autoCenter changes via setOptions (cheaper than re-creating
  // the WaveSurfer instance for what is just a runtime flag).
  useEffect(() => {
    if (!isReady) return
    if (autoCenter === undefined) return
    wsRef.current?.setOptions({ autoCenter })
  }, [isReady, autoCenter])

  // Plan B8 Task 10 — paint thin vertical lines on the wrapper at each
  // scene-cut. Markers are positioned with percentage left-offsets so
  // they automatically scale with WaveSurfer's zoom (the wrapper width
  // grows linearly with px-per-sec, percent stays constant per timestamp).
  useEffect(() => {
    if (!isReady) return
    const ws = wsRef.current
    if (!ws) return
    if (!sceneMarkersMs || sceneMarkersMs.length === 0) return

    let wrapper: HTMLElement | null = null
    try {
      wrapper = ws.getWrapper()
    } catch {
      return
    }
    if (!wrapper) return

    const dur = ws.getDuration()
    if (!Number.isFinite(dur) || dur <= 0) return

    // Anchor styling on the wrapper so the lines paint INSIDE the canvas
    // viewport — without this, position:absolute would resolve against the
    // nearest positioned ancestor, which may be the page <body>.
    const prevPosition = wrapper.style.position
    if (!prevPosition) wrapper.style.position = 'relative'

    const created: HTMLDivElement[] = []
    for (const ms of sceneMarkersMs) {
      const sec = ms / 1000
      if (sec < 0 || sec > dur) continue
      const el = document.createElement('div')
      el.dataset.sublarrSceneMarker = '1'
      el.style.position = 'absolute'
      el.style.top = '0'
      el.style.bottom = '0'
      el.style.left = `${(sec / dur) * 100}%`
      el.style.width = '1px'
      el.style.background = 'rgba(245, 158, 11, 0.55)' // amber-500 @ 55 %
      el.style.pointerEvents = 'none'
      el.style.zIndex = '4'
      wrapper.appendChild(el)
      created.push(el)
    }

    return () => {
      for (const el of created) el.remove()
      if (!prevPosition) wrapper!.style.position = ''
    }
  }, [isReady, sceneMarkersMs])

  // Plan B8 Task 7 — register/unregister the spectrogram plugin in
  // response to the toggle. Done outside the WaveSurfer-create effect so
  // toggling doesn't tear down the audio buffer or active regions.
  useEffect(() => {
    if (!isReady) return
    const ws = wsRef.current
    if (!ws) return

    if (!spectrogramEnabled) return

    const plugin = SpectrogramPlugin.create({
      fftSamples: spectrogramFftSamples,
      labels: true,
      labelsBackground: 'rgba(0,0,0,0.5)',
      height: 80,
      // Mel scale tracks human perception better than linear; matches the
      // default Audacity/SubtitleEdit feel.
      scale: 'mel',
    })
    ws.registerPlugin(plugin)

    return () => {
      // Prefer the explicit unregister API; fall back to the plugin's
      // own destroy in case unregister is missing on the runtime build.
      try {
        ws.unregisterPlugin(plugin)
      } catch {
        plugin.destroy?.()
      }
    }
  }, [isReady, spectrogramEnabled, spectrogramFftSamples])

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

  // Snap + clamp + commit a new start for the currently selected cue.
  // Stable identity (no deps) — both the click-map effect and the hook
  // consumer (keyboard S key) drive this through the same gate.
  const applySetStart = useCallback((timeMs: number) => {
    const cueId = selectedCueIdRef.current
    if (!cueId) return
    const cue = cuesRef.current.find((c) => c.id === cueId)
    if (!cue) return

    const opts: SnapOptions = {
      keyframesMs: keyframesMsRef.current ?? [],
      neighborsMs: deriveNeighborsMs(cuesRef.current, cueId),
      scenesMs: scenesMsRef.current ?? [],
      minGapMs: minGapMsRef.current ?? 0,
      keyframeToleranceMs: keyframeTolRef.current,
      neighborToleranceMs: neighborTolRef.current,
      sceneToleranceMs: sceneTolRef.current,
    }
    const snappedMs = snap(timeMs, opts).value
    const newStart = snappedMs / 1000
    // Reject moves that would invert/collapse the cue. minGap is the
    // floor for usable duration; default to a tiny epsilon so ms-level
    // collisions still get rejected when minGap is 0.
    const minDur = Math.max((minGapMsRef.current ?? 0) / 1000, EDGE_EPSILON_S)
    if (newStart >= cue.end - minDur) return

    onCueChangeRef.current(cueId, { start: newStart, end: cue.end })
  }, [])

  const applySetEnd = useCallback((timeMs: number) => {
    const cueId = selectedCueIdRef.current
    if (!cueId) return
    const cue = cuesRef.current.find((c) => c.id === cueId)
    if (!cue) return

    const opts: SnapOptions = {
      keyframesMs: keyframesMsRef.current ?? [],
      neighborsMs: deriveNeighborsMs(cuesRef.current, cueId),
      scenesMs: scenesMsRef.current ?? [],
      minGapMs: minGapMsRef.current ?? 0,
      keyframeToleranceMs: keyframeTolRef.current,
      neighborToleranceMs: neighborTolRef.current,
      sceneToleranceMs: sceneTolRef.current,
    }
    const snappedMs = snap(timeMs, opts).value
    const newEnd = snappedMs / 1000
    const minDur = Math.max((minGapMsRef.current ?? 0) / 1000, EDGE_EPSILON_S)
    if (newEnd <= cue.start + minDur) return

    onCueChangeRef.current(cueId, { start: cue.start, end: newEnd })
  }, [])

  // L/R click-map (Aegisub convention): only active when a cue is selected
  // AND the editor is unlocked. Listeners read latest cues/keyframes/etc
  // from refs so they don't need to re-attach.
  useEffect(() => {
    const ws = wsRef.current
    const el = container.current
    if (!ws || !el || !isReady || !enableDrag) return

    /** Compute clicked time in ms; null if container has no width. */
    const timeMsAtClient = (clientX: number): number | null => {
      const rect = el.getBoundingClientRect()
      if (rect.width <= 0) return null
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
      const dur = ws.getDuration()
      if (!Number.isFinite(dur) || dur <= 0) return null
      return ratio * dur * 1000
    }

    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0) return // primary button only
      if (!selectedCueIdRef.current) return
      const t = timeMsAtClient(e.clientX)
      if (t === null) return
      applySetStart(t)
    }

    const onContextMenu = (e: MouseEvent) => {
      // Always swallow the browser menu when the editor is unlocked, so
      // users don't see a flicker even if no cue is selected yet.
      e.preventDefault()
      if (!selectedCueIdRef.current) return
      const t = timeMsAtClient(e.clientX)
      if (t === null) return
      applySetEnd(t)
    }

    el.addEventListener('pointerdown', onPointerDown)
    el.addEventListener('contextmenu', onContextMenu)

    return () => {
      el.removeEventListener('pointerdown', onPointerDown)
      el.removeEventListener('contextmenu', onContextMenu)
    }
  }, [container, isReady, enableDrag, applySetStart, applySetEnd])

  const play = useCallback(() => {
    void wsRef.current?.play()
  }, [])
  const pause = useCallback(() => {
    wsRef.current?.pause()
  }, [])
  const playPause = useCallback(() => {
    void wsRef.current?.playPause()
  }, [])

  /** Set the start of the currently selected cue at the playhead position. */
  const setStartAtPlayhead = useCallback(() => {
    const ws = wsRef.current
    if (!ws) return
    const t = ws.getCurrentTime()
    if (!Number.isFinite(t) || t < 0) return
    applySetStart(t * 1000)
  }, [applySetStart])

  /** Set the end of the currently selected cue at the playhead position. */
  const setEndAtPlayhead = useCallback(() => {
    const ws = wsRef.current
    if (!ws) return
    const t = ws.getCurrentTime()
    if (!Number.isFinite(t) || t < 0) return
    applySetEnd(t * 1000)
  }, [applySetEnd])

  /** Seek the playhead by `deltaSec` (negative = back). Clamped to [0, dur]. */
  const seekBy = useCallback((deltaSec: number) => {
    const ws = wsRef.current
    if (!ws) return
    const dur = ws.getDuration()
    if (!Number.isFinite(dur) || dur <= 0) return
    const next = Math.max(0, Math.min(dur, ws.getCurrentTime() + deltaSec))
    ws.setTime(next)
  }, [])

  return {
    ws: wsRef.current,
    regions: regionsRef.current,
    isReady,
    isPlaying,
    play,
    pause,
    playPause,
    setStartAtPlayhead,
    setEndAtPlayhead,
    seekBy,
  }
}
