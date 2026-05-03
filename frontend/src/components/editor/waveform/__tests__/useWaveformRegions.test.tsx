/**
 * Unit tests for `useWaveformRegions` (Plan B8 Task 3).
 *
 * Strategy: mock `wavesurfer.js` and its regions plugin to expose their
 * event emitters as plain `vi.fn` calls so the test can replay
 * `region-updated` and assert `onCueChange` got the patched timings.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'
import { useRef } from 'react'

import { useWaveformRegions, type WaveformCue, type CuePatch } from '../useWaveformRegions'

type Listener = (...args: unknown[]) => void

// ─── Mocks ───────────────────────────────────────────────────────────────

const wsListeners = new Map<string, Listener[]>()
const regionsListeners = new Map<string, Listener[]>()

const fakeRegionsApi = {
  on: vi.fn((event: string, fn: Listener) => {
    if (!regionsListeners.has(event)) regionsListeners.set(event, [])
    regionsListeners.get(event)!.push(fn)
  }),
  un: vi.fn((event: string, fn: Listener) => {
    const arr = regionsListeners.get(event) ?? []
    regionsListeners.set(event, arr.filter((l) => l !== fn))
  }),
  addRegion: vi.fn(),
  clearRegions: vi.fn(),
}

const fakeSpectrogramPlugin = { destroy: vi.fn(), id: 'spec' }

const fakeWs = {
  on: vi.fn((event: string, fn: Listener) => {
    if (!wsListeners.has(event)) wsListeners.set(event, [])
    wsListeners.get(event)!.push(fn)
  }),
  un: vi.fn((event: string, fn: Listener) => {
    const arr = wsListeners.get(event) ?? []
    wsListeners.set(event, arr.filter((l) => l !== fn))
  }),
  load: vi.fn(() => Promise.resolve()),
  destroy: vi.fn(),
  play: vi.fn(),
  pause: vi.fn(),
  playPause: vi.fn(),
  // Tests stub a known duration so click-map ratio math is deterministic
  getDuration: vi.fn(() => 10),
  getCurrentTime: vi.fn(() => 0),
  setTime: vi.fn(),
  zoom: vi.fn(),
  setOptions: vi.fn(),
  setPlaybackRate: vi.fn(),
  registerPlugin: vi.fn(() => fakeSpectrogramPlugin),
  unregisterPlugin: vi.fn(),
  // Provide a real DOM node so the scene-markers effect can append children
  getWrapper: vi.fn(() => fakeWsWrapperEl),
}

// Tests inspect this wrapper for inserted scene-marker children.
const fakeWsWrapperEl: HTMLDivElement = (() => {
  const el = (typeof document !== 'undefined' ? document.createElement('div') : null) as
    | HTMLDivElement
    | null
  return el ?? ({} as HTMLDivElement)
})()

vi.mock('wavesurfer.js', () => ({
  default: {
    create: vi.fn(() => fakeWs),
  },
}))

vi.mock('wavesurfer.js/plugins/timeline', () => ({
  default: {
    create: vi.fn(() => ({ destroy: vi.fn() })),
  },
}))

vi.mock('wavesurfer.js/plugins/regions', () => ({
  default: {
    create: vi.fn(() => fakeRegionsApi),
  },
}))

const fakeSpectrogramApi = { id: 'spec' }
vi.mock('wavesurfer.js/plugins/spectrogram', () => ({
  default: {
    create: vi.fn(() => fakeSpectrogramApi),
  },
}))

// ─── Test harness ────────────────────────────────────────────────────────

function fireWs(event: string, ...args: unknown[]) {
  for (const fn of wsListeners.get(event) ?? []) fn(...args)
}

function fireRegions(event: string, ...args: unknown[]) {
  for (const fn of regionsListeners.get(event) ?? []) fn(...args)
}

const SAMPLE_CUES: WaveformCue[] = [
  { id: '0', start: 0.5, end: 1.5 },
  { id: '1', start: 2.0, end: 3.5 },
  { id: '2', start: 5.0, end: 7.0 },
]

interface HarnessProps {
  cues: WaveformCue[]
  onCueChange: (id: string, patch: CuePatch) => void
  audioUrl?: string | null
  enableDrag?: boolean
  selectedCueId?: string | null
  keyframesMs?: number[]
  minGapMs?: number
  keyframeToleranceMs?: number
  neighborToleranceMs?: number
  zoomPxPerSec?: number
  autoCenter?: boolean
  spectrogramEnabled?: boolean
  scrubOnDrag?: boolean
  sceneMarkersMs?: number[]
}

function Harness({
  cues,
  onCueChange,
  audioUrl = '/fake.wav',
  enableDrag = true,
  selectedCueId,
  keyframesMs,
  minGapMs,
  keyframeToleranceMs,
  neighborToleranceMs,
  zoomPxPerSec,
  autoCenter,
  spectrogramEnabled,
  scrubOnDrag,
  sceneMarkersMs,
}: HarnessProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  useWaveformRegions({
    container: containerRef,
    audioUrl,
    cues,
    onCueChange,
    enableDrag,
    selectedCueId,
    keyframesMs,
    minGapMs,
    keyframeToleranceMs,
    neighborToleranceMs,
    zoomPxPerSec,
    autoCenter,
    spectrogramEnabled,
    scrubOnDrag,
    sceneMarkersMs,
  })
  return <div ref={containerRef} data-testid="waveform-host" />
}

// ─── Tests ───────────────────────────────────────────────────────────────

beforeEach(() => {
  wsListeners.clear()
  regionsListeners.clear()
  vi.clearAllMocks()
})

describe('useWaveformRegions', () => {
  it('renders cues as regions once WaveSurfer signals ready', () => {
    const onCueChange = vi.fn()
    render(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} />)

    // Before "ready", regions should NOT be added (waveform isn't drawn yet)
    expect(fakeRegionsApi.addRegion).not.toHaveBeenCalled()

    // Fire WaveSurfer's ready event -> hook flips isReady -> sync effect runs
    act(() => {
      fireWs('ready')
    })

    expect(fakeRegionsApi.clearRegions).toHaveBeenCalled()
    expect(fakeRegionsApi.addRegion).toHaveBeenCalledTimes(3)
    expect(fakeRegionsApi.addRegion).toHaveBeenNthCalledWith(1, expect.objectContaining({
      id: '0', start: 0.5, end: 1.5, drag: true, resize: true,
    }))
  })

  it('does not paint cue text inside the wave region (text lives in the cue list)', () => {
    // Stacked-Lanes follow-up: regions are pure timing rectangles. The
    // cue text moved to the WaveformCueList lane below the wave because
    // overlaying labels on tightly-packed cues turned the wave into an
    // unreadable wall of letters.
    const cues: WaveformCue[] = [
      { id: '0', start: 0.5, end: 1.5 },
      { id: '1', start: 2.5, end: 3.5 },
    ]
    render(<Harness cues={cues} onCueChange={vi.fn()} />)

    act(() => {
      fireWs('ready')
    })

    const calls = fakeRegionsApi.addRegion.mock.calls
    expect(calls[0][0].content).toBeUndefined()
    expect(calls[1][0].content).toBeUndefined()
  })

  it('respects enableDrag=false (read-only mode)', () => {
    const onCueChange = vi.fn()
    render(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} enableDrag={false} />)

    act(() => {
      fireWs('ready')
    })

    expect(fakeRegionsApi.addRegion).toHaveBeenCalledWith(expect.objectContaining({
      drag: false, resize: false,
    }))
  })

  it('commits cue change on region-updated (drag-end) event', () => {
    const onCueChange = vi.fn()
    render(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} />)

    act(() => {
      fireWs('ready')
      fireRegions('region-updated', { id: '1', start: 2.4, end: 3.9 })
    })

    expect(onCueChange).toHaveBeenCalledTimes(1)
    expect(onCueChange).toHaveBeenCalledWith('1', { start: 2.4, end: 3.9 })
  })

  it('does NOT commit on region-update (per-frame drag)', () => {
    const onCueChange = vi.fn()
    render(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} />)

    act(() => {
      fireWs('ready')
      fireRegions('region-update', { id: '1', start: 2.1, end: 3.6 })
    })

    expect(onCueChange).not.toHaveBeenCalled()
  })

  it('does not rewrite regions during an active drag', () => {
    const onCueChange = vi.fn()
    const { rerender } = render(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} />)

    act(() => {
      fireWs('ready')
    })
    // After ready, regions are drawn. Reset the tracker so the next assertion
    // measures only post-drag-start activity.
    fakeRegionsApi.clearRegions.mockClear()
    fakeRegionsApi.addRegion.mockClear()

    // Simulate drag start (per-frame event without a corresponding end)
    act(() => {
      fireRegions('region-update', { id: '1', start: 2.1, end: 3.6 })
    })

    // Parent now re-renders with new cue list (e.g. another component edited)
    const newCues = [...SAMPLE_CUES, { id: '3', start: 9, end: 11 }]
    rerender(<Harness cues={newCues} onCueChange={onCueChange} />)

    // Sync effect must skip its rebuild while dragging
    expect(fakeRegionsApi.clearRegions).not.toHaveBeenCalled()
    expect(fakeRegionsApi.addRegion).not.toHaveBeenCalled()
  })

  it('does nothing when audioUrl is null', () => {
    const onCueChange = vi.fn()
    render(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} audioUrl={null} />)

    expect(fakeWs.load).not.toHaveBeenCalled()
    expect(fakeRegionsApi.addRegion).not.toHaveBeenCalled()
  })

  // ─── B8.4 Step 2: drag-end snap ───────────────────────────────────────

  describe('drag-end snap', () => {
    it('snaps the start when only the left edge moved', () => {
      const onCueChange = vi.fn()
      render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          // 2050 ms is within 80 ms of 2000 -> snap there. cue '1' was 2.0-3.5s,
          // user dragged left edge to 2.05; we expect snap back to 2.0
          keyframesMs={[2000]}
          keyframeToleranceMs={150}
        />,
      )

      act(() => {
        fireWs('ready')
        fireRegions('region-updated', { id: '1', start: 2.05, end: 3.5 })
      })

      expect(onCueChange).toHaveBeenCalledWith('1', { start: 2.0, end: 3.5 })
    })

    it('snaps the end when only the right edge moved', () => {
      const onCueChange = vi.fn()
      render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          keyframesMs={[3600]}
          keyframeToleranceMs={150}
        />,
      )

      act(() => {
        fireWs('ready')
        // cue '1' was 2.0-3.5s; user dragged right edge to 3.55. Snap to 3.6
        fireRegions('region-updated', { id: '1', start: 2.0, end: 3.55 })
      })

      expect(onCueChange).toHaveBeenCalledWith('1', { start: 2.0, end: 3.6 })
    })

    it('preserves duration on whole-region drag (snaps start, slides end)', () => {
      const onCueChange = vi.fn()
      render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          // cue '1' is 2.0-3.5 (1500 ms wide). Drag both edges +0.08 to 2.08-3.58.
          // Keyframe at 2100 -> snap start to 2.1, end becomes 2.1 + 1.5 = 3.6
          keyframesMs={[2100]}
          keyframeToleranceMs={150}
        />,
      )

      act(() => {
        fireWs('ready')
        fireRegions('region-updated', { id: '1', start: 2.08, end: 3.58 })
      })

      expect(onCueChange).toHaveBeenCalledWith('1', { start: 2.1, end: 3.6 })
    })

    it('commits raw values when no snap targets are in range', () => {
      const onCueChange = vi.fn()
      render(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} />)

      act(() => {
        fireWs('ready')
        fireRegions('region-updated', { id: '1', start: 2.4, end: 3.9 })
      })

      expect(onCueChange).toHaveBeenCalledWith('1', { start: 2.4, end: 3.9 })
    })
  })

  // ─── B8.4 Step 3: Aegisub L/R click-map ───────────────────────────────

  describe('L/R click-map', () => {
    function stubRect(host: HTMLElement) {
      // jsdom returns an all-zero DOMRect by default; stub a 1000-px wide host
      // so click ratios are easy to reason about (1 px = 10 ms at duration 10 s)
      host.getBoundingClientRect = () =>
        ({ left: 0, top: 0, right: 1000, bottom: 100, width: 1000, height: 100, x: 0, y: 0, toJSON: () => '' }) as DOMRect
    }

    it('L-click on body sets snapped start of selected cue', () => {
      const onCueChange = vi.fn()
      const { getByTestId } = render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          selectedCueId="1"
          keyframesMs={[2100]}
          keyframeToleranceMs={150}
        />,
      )
      const host = getByTestId('waveform-host')
      stubRect(host)

      act(() => {
        fireWs('ready')
      })

      // Click at x=205 -> 20.5% of 10 s = 2.05 s = 2050 ms.
      // Keyframe at 2100 within 150 -> snap start to 2.1; end stays at 3.5.
      act(() => {
        host.dispatchEvent(
          new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 205, clientY: 50 }),
        )
      })

      expect(onCueChange).toHaveBeenCalledWith('1', { start: 2.1, end: 3.5 })
    })

    it('R-click on body sets snapped end of selected cue', () => {
      const onCueChange = vi.fn()
      const { getByTestId } = render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          selectedCueId="1"
          keyframesMs={[3600]}
          keyframeToleranceMs={150}
        />,
      )
      const host = getByTestId('waveform-host')
      stubRect(host)

      act(() => {
        fireWs('ready')
      })

      // Click at x=355 -> 3550 ms; snap to 3600 ms = 3.6 s
      act(() => {
        const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 355, clientY: 50 })
        host.dispatchEvent(e)
      })

      expect(onCueChange).toHaveBeenCalledWith('1', { start: 2.0, end: 3.6 })
    })

    it('does not fire when no cue is selected', () => {
      const onCueChange = vi.fn()
      const { getByTestId } = render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} selectedCueId={null} />,
      )
      const host = getByTestId('waveform-host')
      stubRect(host)

      act(() => {
        fireWs('ready')
      })

      act(() => {
        host.dispatchEvent(
          new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 205, clientY: 50 }),
        )
      })

      expect(onCueChange).not.toHaveBeenCalled()
    })

    it('does not fire in read-only mode (enableDrag=false)', () => {
      const onCueChange = vi.fn()
      const { getByTestId } = render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          enableDrag={false}
          selectedCueId="1"
        />,
      )
      const host = getByTestId('waveform-host')
      stubRect(host)

      act(() => {
        fireWs('ready')
      })

      act(() => {
        host.dispatchEvent(
          new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 205, clientY: 50 }),
        )
        host.dispatchEvent(
          new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 355, clientY: 50 }),
        )
      })

      expect(onCueChange).not.toHaveBeenCalled()
    })

    it('clamps L-click so start cannot collapse onto the end', () => {
      const onCueChange = vi.fn()
      const { getByTestId } = render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          selectedCueId="1"
          minGapMs={100}
        />,
      )
      const host = getByTestId('waveform-host')
      stubRect(host)

      act(() => {
        fireWs('ready')
      })

      // Click at x=400 -> 4000 ms = 4.0 s. cue '1' end is 3.5 s, so clamp must
      // keep at least 100 ms duration. Result rejected (no commit) since the
      // requested start would invert the cue.
      act(() => {
        host.dispatchEvent(
          new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 400, clientY: 50 }),
        )
      })

      expect(onCueChange).not.toHaveBeenCalled()
    })

    it('right-click prevents default browser context menu', () => {
      const onCueChange = vi.fn()
      const { getByTestId } = render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} selectedCueId="1" />,
      )
      const host = getByTestId('waveform-host')
      stubRect(host)

      act(() => {
        fireWs('ready')
      })

      const e = new MouseEvent('contextmenu', {
        bubbles: true,
        cancelable: true,
        clientX: 300,
        clientY: 50,
      })
      act(() => {
        host.dispatchEvent(e)
      })

      expect(e.defaultPrevented).toBe(true)
    })
  })

  // ─── B8.6 Step 1+2: zoom + auto-center ────────────────────────────────

  describe('zoom + auto-center', () => {
    it('calls ws.zoom() when zoomPxPerSec changes after ready', () => {
      const onCueChange = vi.fn()
      const { rerender } = render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} zoomPxPerSec={10} />,
      )

      act(() => {
        fireWs('ready')
      })

      // First call applies the initial zoom value once isReady flips
      expect(fakeWs.zoom).toHaveBeenLastCalledWith(10)

      rerender(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} zoomPxPerSec={42} />)
      expect(fakeWs.zoom).toHaveBeenLastCalledWith(42)
    })

    it('does not call ws.zoom() before WaveSurfer signals ready', () => {
      const onCueChange = vi.fn()
      render(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} zoomPxPerSec={20} />)

      // Without firing 'ready', the zoom call must not have happened
      expect(fakeWs.zoom).not.toHaveBeenCalled()
    })

    it('forwards autoCenter changes via ws.setOptions', () => {
      const onCueChange = vi.fn()
      const { rerender } = render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} autoCenter={true} />,
      )

      act(() => {
        fireWs('ready')
      })

      expect(fakeWs.setOptions).toHaveBeenCalledWith(
        expect.objectContaining({ autoCenter: true }),
      )

      fakeWs.setOptions.mockClear()
      rerender(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} autoCenter={false} />)

      expect(fakeWs.setOptions).toHaveBeenCalledWith(
        expect.objectContaining({ autoCenter: false }),
      )
    })
  })

  // ─── B8.7: spectrogram toggle ─────────────────────────────────────────

  describe('spectrogram toggle', () => {
    it('does not register the plugin when disabled', () => {
      const onCueChange = vi.fn()
      render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} spectrogramEnabled={false} />,
      )

      act(() => {
        fireWs('ready')
      })

      expect(fakeWs.registerPlugin).not.toHaveBeenCalled()
    })

    it('registers the plugin once enabled after ready', () => {
      const onCueChange = vi.fn()
      const { rerender } = render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} spectrogramEnabled={false} />,
      )

      act(() => {
        fireWs('ready')
      })

      rerender(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} spectrogramEnabled={true} />,
      )

      expect(fakeWs.registerPlugin).toHaveBeenCalledTimes(1)
    })

    it('unregisters the plugin when toggled off', () => {
      const onCueChange = vi.fn()
      const { rerender } = render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} spectrogramEnabled={true} />,
      )

      act(() => {
        fireWs('ready')
      })
      expect(fakeWs.registerPlugin).toHaveBeenCalledTimes(1)

      rerender(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} spectrogramEnabled={false} />,
      )

      // Either unregisterPlugin OR plugin.destroy must have run.
      const cleaned =
        fakeWs.unregisterPlugin.mock.calls.length > 0 ||
        fakeSpectrogramPlugin.destroy.mock.calls.length > 0
      expect(cleaned).toBe(true)
    })
  })

  // ─── B8.8: audio scrubbing while dragging ─────────────────────────────

  describe('scrub on drag', () => {
    it('does not play when scrubOnDrag is false', () => {
      const onCueChange = vi.fn()
      render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} scrubOnDrag={false} />,
      )

      act(() => {
        fireWs('ready')
        fireRegions('region-update', { id: '1', start: 2.1, end: 3.5 })
      })

      expect(fakeWs.play).not.toHaveBeenCalled()
    })

    it('plays a 200 ms window at the moving start edge', () => {
      const onCueChange = vi.fn()
      render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} scrubOnDrag={true} />,
      )

      act(() => {
        fireWs('ready')
        // cue '1' was 2.0-3.5; user dragged left edge to 2.1.
        fireRegions('region-update', { id: '1', start: 2.1, end: 3.5 })
      })

      // ws.play(start, start + 0.2)
      expect(fakeWs.play).toHaveBeenCalledTimes(1)
      const [from, to] = fakeWs.play.mock.calls[0] as [number, number]
      expect(from).toBeCloseTo(2.1, 5)
      expect(to).toBeCloseTo(2.3, 5)
    })

    it('plays a 200 ms window at the moving end edge', () => {
      const onCueChange = vi.fn()
      render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} scrubOnDrag={true} />,
      )

      act(() => {
        fireWs('ready')
        // cue '1' was 2.0-3.5; user dragged right edge to 3.6.
        fireRegions('region-update', { id: '1', start: 2.0, end: 3.6 })
      })

      expect(fakeWs.play).toHaveBeenCalledTimes(1)
      const [from, to] = fakeWs.play.mock.calls[0] as [number, number]
      expect(from).toBeCloseTo(3.4, 5)
      expect(to).toBeCloseTo(3.6, 5)
    })

    it('throttles to ~30 Hz: rapid back-to-back updates collapse', () => {
      const onCueChange = vi.fn()
      render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} scrubOnDrag={true} />,
      )

      act(() => {
        fireWs('ready')
      })

      // Fire 5 updates within the same JS tick — all share Date.now(), so
      // the throttle gate must collapse them into a single play call.
      act(() => {
        for (let i = 0; i < 5; i++) {
          fireRegions('region-update', {
            id: '1',
            start: 2.0 + i * 0.005,
            end: 3.5,
          })
        }
      })

      expect(fakeWs.play).toHaveBeenCalledTimes(1)
    })
  })

  // ─── B8.10: scene-detection markers ───────────────────────────────────

  describe('scene markers', () => {
    function clearWrapper() {
      while (fakeWsWrapperEl.firstChild) fakeWsWrapperEl.removeChild(fakeWsWrapperEl.firstChild)
    }

    it('paints one marker element per provided timestamp', () => {
      clearWrapper()
      const onCueChange = vi.fn()
      // duration mock returns 10 s; positions: 1s -> 10%, 5s -> 50%, 9s -> 90%
      render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          sceneMarkersMs={[1000, 5000, 9000]}
        />,
      )

      act(() => {
        fireWs('ready')
      })

      const markers = fakeWsWrapperEl.querySelectorAll('[data-sublarr-scene-marker="1"]')
      expect(markers).toHaveLength(3)
    })

    it('positions markers using percentage of duration', () => {
      clearWrapper()
      const onCueChange = vi.fn()
      render(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} sceneMarkersMs={[5000]} />,
      )

      act(() => {
        fireWs('ready')
      })

      const marker = fakeWsWrapperEl.querySelector(
        '[data-sublarr-scene-marker="1"]',
      ) as HTMLElement
      // 5 s of a 10 s duration -> 50%
      expect(marker.style.left).toBe('50%')
    })

    it('skips markers that fall outside the audio duration', () => {
      clearWrapper()
      const onCueChange = vi.fn()
      // 100 s is well past the mocked 10 s duration -> excluded
      render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          sceneMarkersMs={[1000, 100_000]}
        />,
      )

      act(() => {
        fireWs('ready')
      })

      expect(fakeWsWrapperEl.querySelectorAll('[data-sublarr-scene-marker="1"]')).toHaveLength(1)
    })

    it('removes existing markers when the list changes', () => {
      clearWrapper()
      const onCueChange = vi.fn()
      const { rerender } = render(
        <Harness
          cues={SAMPLE_CUES}
          onCueChange={onCueChange}
          sceneMarkersMs={[1000, 5000]}
        />,
      )

      act(() => {
        fireWs('ready')
      })
      expect(fakeWsWrapperEl.querySelectorAll('[data-sublarr-scene-marker="1"]')).toHaveLength(2)

      // Switch to a single-marker list — old markers should be cleared first
      rerender(
        <Harness cues={SAMPLE_CUES} onCueChange={onCueChange} sceneMarkersMs={[3000]} />,
      )

      const markers = fakeWsWrapperEl.querySelectorAll('[data-sublarr-scene-marker="1"]')
      expect(markers).toHaveLength(1)
      expect((markers[0] as HTMLElement).style.left).toBe('30%')
    })

    it('does nothing when the list is empty', () => {
      clearWrapper()
      const onCueChange = vi.fn()
      render(<Harness cues={SAMPLE_CUES} onCueChange={onCueChange} sceneMarkersMs={[]} />)

      act(() => {
        fireWs('ready')
      })

      expect(fakeWsWrapperEl.querySelectorAll('[data-sublarr-scene-marker="1"]')).toHaveLength(0)
    })
  })
})
