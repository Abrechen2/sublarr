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
import TimelinePlugin from 'wavesurfer.js/plugins/timeline'

import { snap, type SnapOptions } from './snap'
import { detectGapsAndOverlaps } from './gapOverlap'

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
  /**
   * When true, paint thin teal vertical lines at each keyframe so the
   * editor can see the snap targets they're aligning to. Default off
   * because keyframes are dense (~one per 0.5 s) and clutter the wave.
   * The keyframes themselves are passed via `keyframesMs` regardless;
   * this flag only controls the visual overlay.
   */
  showKeyframeMarkers?: boolean
  /**
   * Vertical amplitude zoom (`barHeight`). Scales the waveform peaks
   * so quiet dialogue is editable. Default 1 (no scaling); 5 is the
   * practical upper bound before the waveform clips.
   */
  ampZoom?: number
  /**
   * Audio playback rate. Wired to `ws.setPlaybackRate(rate, true)` so
   * pitch is preserved (Web Audio `preservesPitch`). Default 1.0.
   */
  playbackRate?: number
  /**
   * Render thin amber bars for tight inter-cue gaps and red bars for
   * overlaps. Default true — these are quality signals the editor wants
   * to see permanently. Pure visualisation; no behavioural side-effect.
   */
  showGapOverlapMarkers?: boolean
  /**
   * Tolerance in ms below which an inter-cue gap is "tight". Default 80.
   * Matches `minGapMs` so the editor sees the line they're trying to
   * stay above.
   */
  gapToleranceMs?: number
  /**
   * VAD speech-activity segments in seconds. Painted as a green strip just
   * above the gap/overlap lane so the editor can see where dialogue is
   * (anime mixes bury speech under BGM/SFX). Opt-in via `showSpeechLane`.
   */
  speechSegments?: { start: number; end: number }[]
  /** Show the speech-activity lane. Default false — opt-in, never disturbs the
   *  locked surfaces when off. */
  showSpeechLane?: boolean
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
   * Loop-audition (`L` key): repeat the [fromSec, toSec] window until
   * stopped. Any other transport action (play/pause/seek) cancels the loop
   * so the user never gets "stuck" inside it.
   */
  startLoop: (fromSec: number, toSec: number) => void
  /** Stop a running loop-audition and pause playback. */
  stopLoop: () => void
  /** True while a loop-audition window is active. */
  isLooping: boolean
  /**
   * Snap-and-set the selected cue's start to the current playhead. Used by
   * the keyboard `S` hotkey (Aegisub convention).
   */
  setStartAtPlayhead: () => void
  /** Snap-and-set the selected cue's end to the current playhead (`D` key). */
  setEndAtPlayhead: () => void
  /** Seek the playhead by `deltaSec` seconds; negative means back. */
  seekBy: (deltaSec: number) => void
  /** Seek the playhead to an absolute time in seconds (clamped to [0, dur]). */
  seekTo: (sec: number) => void
  /**
   * Currently visible [startSec, endSec] of the wave viewport. `null` until
   * WaveSurfer fires its first scroll event after `ready`. The cue list uses
   * this for its sync-highlight band.
   */
  visibleRange: [number, number] | null
  /**
   * Current playhead position in seconds. Throttled to ~10 Hz via
   * `ws.on('timeupdate', ...)`. Used by the cue list to highlight the cue
   * being played and (when auto-follow is on) to scroll it into view.
   */
  playheadSec: number
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
  showKeyframeMarkers = false,
  ampZoom,
  playbackRate,
  showGapOverlapMarkers = true,
  gapToleranceMs = 80,
  speechSegments,
  showSpeechLane = false,
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
  // Speech-edge snap targets — only active while the speech lane is shown, so
  // enabling "Sprache" both draws the lane and lets boundaries snap to it.
  const speechSegmentsRef = useRef(speechSegments)
  speechSegmentsRef.current = speechSegments
  const showSpeechLaneRef = useRef(showSpeechLane)
  showSpeechLaneRef.current = showSpeechLane
  const selectedCueIdRef = useRef(selectedCueId)
  selectedCueIdRef.current = selectedCueId
  // Scrub-on-drag inputs read inside the long-lived region-update listener
  const scrubOnDragRef = useRef(scrubOnDrag)
  scrubOnDragRef.current = scrubOnDrag
  const scrubWindowSecRef = useRef(scrubWindowSec)
  scrubWindowSecRef.current = scrubWindowSec
  // Last scrub timestamp (ms epoch); used by the throttle gate.
  const lastScrubAtRef = useRef<number>(0)
  // Loop-audition window in seconds; null when no loop is active. Read by
  // the long-lived pause/finish listeners to decide whether to restart.
  const loopRef = useRef<{ from: number; to: number } | null>(null)

  const [isReady, setIsReady] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isLooping, setIsLooping] = useState(false)
  const [visibleRange, setVisibleRange] = useState<[number, number] | null>(null)
  const [playheadSec, setPlayheadSec] = useState<number>(0)

  /** Build SnapOptions for a given cue id (excluded from neighbors). */
  const buildSnapOpts = useCallback((excludingId: string | null | undefined): SnapOptions => {
    return {
      keyframesMs: keyframesMsRef.current ?? [],
      neighborsMs: deriveNeighborsMs(cuesRef.current, excludingId),
      scenesMs: scenesMsRef.current ?? [],
      speechEdgesMs: showSpeechLaneRef.current
        ? (speechSegmentsRef.current ?? []).flatMap((s) => [s.start * 1000, s.end * 1000])
        : [],
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

    // Sticky time-axis above the waveform (gold-standard follow-up).
    // Pinned via insertPosition='beforebegin' so it sits above the
    // canvas and stays in sync as the user zooms.
    const timelinePlugin = TimelinePlugin.create({
      height: 18,
      insertPosition: 'beforebegin',
      timeInterval: 1,
      primaryLabelInterval: 5,
      secondaryLabelInterval: 1,
      style: { fontSize: '10px', color: 'rgba(148, 163, 184, 0.85)' },
    })

    const ws = WaveSurfer.create({
      container: container.current,
      waveColor,
      progressColor,
      height,
      plugins: [regionsPlugin, timelinePlugin],
    })
    wsRef.current = ws

    const onPlay = () => setIsPlaying(true)
    // WaveSurfer's play(from, to) pauses when the window ends; if a
    // loop-audition is active and the playhead landed at (or past) the
    // window's end, restart it. A manual pause mid-window falls through
    // and just pauses — the loop flag stays set until explicitly cleared.
    const restartLoopIfEnded = () => {
      const loop = loopRef.current
      const ws2 = wsRef.current
      if (!loop || !ws2) return false
      if (ws2.getCurrentTime() < loop.to - 0.05) return false
      void ws2.play(loop.from, loop.to)
      return true
    }
    const onPause = () => {
      if (restartLoopIfEnded()) return
      setIsPlaying(false)
    }
    const onFinish = () => {
      if (restartLoopIfEnded()) return
      setIsPlaying(false)
    }
    const onReady = () => {
      setIsReady(true)
    }
    // Throttle timeupdate to ~10 Hz so React doesn't re-render the cue
    // list 60 times per second during playback. The user can't perceive
    // a 100 ms delay on a row highlight; the saved frames matter.
    let lastTimeUpdateAt = 0
    const onTimeUpdate = (t: unknown) => {
      const now = Date.now()
      if (now - lastTimeUpdateAt < 100) return
      lastTimeUpdateAt = now
      if (typeof t === 'number' && Number.isFinite(t)) {
        setPlayheadSec(t)
      }
    }

    ws.on('play', onPlay)
    ws.on('pause', onPause)
    ws.on('finish', onFinish)
    ws.on('ready', onReady)
    // NOTE: WaveSurfer v7's `scroll` event is unreliable -- it does not fire
    // when `ws.zoom()` is applied programmatically. The visible range is
    // computed from the native scroller's scrollLeft + ResizeObserver in a
    // separate effect below; we deliberately do NOT subscribe to ws.on('scroll').
    ws.on('timeupdate', onTimeUpdate)

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
      ws.un('timeupdate', onTimeUpdate)
      regionsPlugin.un('region-update', onRegionUpdate)
      regionsPlugin.un('region-updated', onRegionUpdateEnd)
      ws.destroy()
      wsRef.current = null
      regionsRef.current = null
      loopRef.current = null
      setIsReady(false)
      setIsPlaying(false)
      setIsLooping(false)
      setVisibleRange(null)
      setPlayheadSec(0)
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

  // Compute + maintain `visibleRange` from the scroller's actual layout.
  // We wait one animation frame after every trigger so the post-zoom
  // wrapper resize has flushed before we measure. Triggers: ready, zoom,
  // native scroll, ResizeObserver (window resize / modal grow).
  useEffect(() => {
    if (!isReady) return
    const ws = wsRef.current
    if (!ws) return
    let wrapper: HTMLElement | null = null
    let scroller: HTMLElement | null = null
    try {
      wrapper = ws.getWrapper()
      scroller = (wrapper?.parentElement ?? wrapper) as HTMLElement | null
    } catch {
      return
    }
    if (!wrapper || !scroller) return

    let cancelled = false
    let rafHandle = 0
    const recompute = () => {
      // Guard: WS may have been destroyed between RAF schedule + fire.
      if (cancelled || wsRef.current !== ws) return
      let dur: number
      try {
        dur = ws.getDuration()
      } catch {
        return
      }
      if (!Number.isFinite(dur) || dur <= 0) return
      const totalWidth = wrapper!.clientWidth
      const visibleW = scroller!.clientWidth
      if (totalWidth <= 0 || visibleW <= 0) return
      const scrollLeft = scroller!.scrollLeft
      const startSec = (scrollLeft / totalWidth) * dur
      const endSec = ((scrollLeft + visibleW) / totalWidth) * dur
      setVisibleRange([startSec, endSec])
    }
    const scheduleRecompute = () => {
      if (cancelled) return
      cancelAnimationFrame(rafHandle)
      rafHandle = requestAnimationFrame(recompute)
    }

    scroller.addEventListener('scroll', scheduleRecompute, { passive: true })
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(scheduleRecompute) : null
    ro?.observe(wrapper)
    ro?.observe(scroller)

    // Initial compute after the current frame; covers post-ready + zoom
    // changes that re-trigger this effect.
    scheduleRecompute()

    return () => {
      cancelled = true
      cancelAnimationFrame(rafHandle)
      scroller!.removeEventListener('scroll', scheduleRecompute)
      ro?.disconnect()
    }
  }, [isReady, zoomPxPerSec])

  // Forward autoCenter changes via setOptions (cheaper than re-creating
  // the WaveSurfer instance for what is just a runtime flag).
  useEffect(() => {
    if (!isReady) return
    if (autoCenter === undefined) return
    wsRef.current?.setOptions({ autoCenter })
  }, [isReady, autoCenter])

  // Vertical amplitude zoom — drives WaveSurfer's barHeight so quiet
  // dialogue scenes get usable visual peaks. setOptions hot-applies
  // without re-decoding the audio.
  useEffect(() => {
    if (!isReady) return
    if (ampZoom === undefined) return
    wsRef.current?.setOptions({ barHeight: ampZoom })
  }, [isReady, ampZoom])

  // Playback-rate slider — pitch is preserved (`preservesPitch=true`),
  // matching Aegisub's slow-mo audition workflow.
  useEffect(() => {
    if (!isReady) return
    if (playbackRate === undefined) return
    wsRef.current?.setPlaybackRate(playbackRate, true)
  }, [isReady, playbackRate])

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

  // Keyframe markers (gold-standard follow-up). Same DOM-overlay pattern
  // as scene markers but tinted teal at lower opacity so the dense cluster
  // (~one per 0.5 s) doesn't dominate the waveform. Off by default;
  // toggle via the toolbar.
  useEffect(() => {
    if (!isReady) return
    if (!showKeyframeMarkers) return
    const ws = wsRef.current
    if (!ws) return
    const kf = keyframesMs
    if (!kf || kf.length === 0) return

    let wrapper: HTMLElement | null = null
    try {
      wrapper = ws.getWrapper()
    } catch {
      return
    }
    if (!wrapper) return

    const dur = ws.getDuration()
    if (!Number.isFinite(dur) || dur <= 0) return

    const prevPosition = wrapper.style.position
    if (!prevPosition) wrapper.style.position = 'relative'

    const created: HTMLDivElement[] = []
    for (const ms of kf) {
      const sec = ms / 1000
      if (sec < 0 || sec > dur) continue
      const el = document.createElement('div')
      el.dataset.sublarrKeyframeMarker = '1'
      el.style.position = 'absolute'
      el.style.top = '0'
      el.style.bottom = '0'
      el.style.left = `${(sec / dur) * 100}%`
      el.style.width = '1px'
      el.style.background = 'rgba(20, 184, 166, 0.28)' // teal-500 @ 28 %
      el.style.pointerEvents = 'none'
      el.style.zIndex = '3' // below scene markers (z-index:4)
      wrapper.appendChild(el)
      created.push(el)
    }

    return () => {
      for (const el of created) el.remove()
      if (!prevPosition) wrapper!.style.position = ''
    }
  }, [isReady, showKeyframeMarkers, keyframesMs])

  // Gap/overlap quality markers (gold-standard follow-up). Tight gaps
  // paint amber, overlaps paint red. Both are intervals (not zero-width
  // lines) drawn at the bottom 6 px of the waveform so they don't
  // obscure the regions themselves.
  useEffect(() => {
    if (!isReady) return
    if (!showGapOverlapMarkers) return
    const ws = wsRef.current
    if (!ws) return

    const { overlaps, tightGaps } = detectGapsAndOverlaps(cues, { gapToleranceMs })
    if (overlaps.length === 0 && tightGaps.length === 0) return

    let wrapper: HTMLElement | null = null
    try {
      wrapper = ws.getWrapper()
    } catch {
      return
    }
    if (!wrapper) return

    const dur = ws.getDuration()
    if (!Number.isFinite(dur) || dur <= 0) return

    const prevPosition = wrapper.style.position
    if (!prevPosition) wrapper.style.position = 'relative'

    const created: HTMLDivElement[] = []
    const paint = (
      start: number,
      end: number,
      bg: string,
      tooltip: string,
      kind: 'overlap' | 'tightGap',
    ) => {
      const safeStart = Math.max(0, start)
      const safeEnd = Math.min(dur, end)
      if (safeEnd <= safeStart) {
        // Zero-width interval (touching cues): paint a 2 px tick instead
        // so it's visible.
        const el = document.createElement('div')
        el.dataset.sublarrGapOverlap = kind
        el.title = tooltip
        el.style.position = 'absolute'
        el.style.bottom = '0'
        el.style.height = '6px'
        el.style.left = `${(safeStart / dur) * 100}%`
        el.style.width = '2px'
        el.style.background = bg
        el.style.pointerEvents = 'none'
        el.style.zIndex = '5'
        wrapper!.appendChild(el)
        created.push(el)
        return
      }
      const el = document.createElement('div')
      el.dataset.sublarrGapOverlap = kind
      el.title = tooltip
      el.style.position = 'absolute'
      el.style.bottom = '0'
      el.style.height = '6px'
      el.style.left = `${(safeStart / dur) * 100}%`
      el.style.width = `${((safeEnd - safeStart) / dur) * 100}%`
      el.style.background = bg
      el.style.pointerEvents = 'none'
      el.style.zIndex = '5'
      wrapper!.appendChild(el)
      created.push(el)
    }

    for (const ov of overlaps) {
      paint(
        ov.start,
        ov.end,
        'rgba(239, 68, 68, 0.55)', // red-500 @ 55 %
        `Overlap: cues ${ov.prevId} ↔ ${ov.nextId}`,
        'overlap',
      )
    }
    for (const tg of tightGaps) {
      paint(
        tg.start,
        tg.end,
        'rgba(245, 158, 11, 0.55)', // amber-500 @ 55 %
        `Tight gap (<${gapToleranceMs} ms): cues ${tg.prevId} → ${tg.nextId}`,
        'tightGap',
      )
    }

    return () => {
      for (const el of created) el.remove()
      if (!prevPosition) wrapper!.style.position = ''
    }
  }, [isReady, cues, showGapOverlapMarkers, gapToleranceMs])

  // VAD speech-activity lane (Waveform Phase 2). Opt-in via `showSpeechLane`
  // so it never touches the locked surfaces when off. Speech segments paint as
  // a green strip just above the gap/overlap quality lane, using the same
  // percent-of-duration DOM overlay so they scale with WaveSurfer's zoom.
  useEffect(() => {
    if (!isReady) return
    if (!showSpeechLane) return
    const ws = wsRef.current
    if (!ws) return
    const segs = speechSegments
    if (!segs || segs.length === 0) return

    let wrapper: HTMLElement | null = null
    try {
      wrapper = ws.getWrapper()
    } catch {
      return
    }
    if (!wrapper) return

    const dur = ws.getDuration()
    if (!Number.isFinite(dur) || dur <= 0) return

    const prevPosition = wrapper.style.position
    if (!prevPosition) wrapper.style.position = 'relative'

    const created: HTMLDivElement[] = []
    for (const seg of segs) {
      const safeStart = Math.max(0, seg.start)
      const safeEnd = Math.min(dur, seg.end)
      if (safeEnd <= safeStart) continue
      const el = document.createElement('div')
      el.dataset.sublarrSpeechSegment = '1'
      el.style.position = 'absolute'
      el.style.bottom = '8px' // just above the 6 px gap/overlap lane
      el.style.height = '5px'
      el.style.left = `${(safeStart / dur) * 100}%`
      el.style.width = `${((safeEnd - safeStart) / dur) * 100}%`
      el.style.background = 'rgba(34, 197, 94, 0.55)' // green-500 @ 55 %
      el.style.borderRadius = '2px'
      el.style.pointerEvents = 'none'
      el.style.zIndex = '4'
      wrapper.appendChild(el)
      created.push(el)
    }

    return () => {
      for (const el of created) el.remove()
      if (!prevPosition) wrapper!.style.position = ''
    }
  }, [isReady, showSpeechLane, speechSegments])

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

  /** Drop the loop window without touching playback. Called by every other
   *  transport action so a running loop never "captures" them. */
  const clearLoop = useCallback(() => {
    if (loopRef.current === null) return
    loopRef.current = null
    setIsLooping(false)
  }, [])

  const play = useCallback(() => {
    clearLoop()
    void wsRef.current?.play()
  }, [clearLoop])
  const pause = useCallback(() => {
    clearLoop()
    wsRef.current?.pause()
  }, [clearLoop])
  const playPause = useCallback(() => {
    clearLoop()
    void wsRef.current?.playPause()
  }, [clearLoop])

  const startLoop = useCallback((fromSec: number, toSec: number) => {
    const ws = wsRef.current
    if (!ws) return
    const dur = ws.getDuration()
    if (!Number.isFinite(dur) || dur <= 0) return
    const from = Math.max(0, Math.min(dur, fromSec))
    const to = Math.max(0, Math.min(dur, toSec))
    if (to - from < 0.01) return
    loopRef.current = { from, to }
    setIsLooping(true)
    void ws.play(from, to)
  }, [])

  const stopLoop = useCallback(() => {
    clearLoop()
    wsRef.current?.pause()
  }, [clearLoop])

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

  /** Seek the playhead to an absolute time in seconds. Clamped to [0, dur]. */
  const seekTo = useCallback((sec: number) => {
    const ws = wsRef.current
    if (!ws) return
    const dur = ws.getDuration()
    if (!Number.isFinite(dur) || dur <= 0) return
    if (!Number.isFinite(sec)) return
    ws.setTime(Math.max(0, Math.min(dur, sec)))
  }, [])

  return {
    ws: wsRef.current,
    regions: regionsRef.current,
    isReady,
    isPlaying,
    play,
    pause,
    playPause,
    startLoop,
    stopLoop,
    isLooping,
    setStartAtPlayhead,
    setEndAtPlayhead,
    seekBy,
    seekTo,
    visibleRange,
    playheadSec,
  }
}
