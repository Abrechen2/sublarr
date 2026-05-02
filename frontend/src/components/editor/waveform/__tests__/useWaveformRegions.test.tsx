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
}

vi.mock('wavesurfer.js', () => ({
  default: {
    create: vi.fn(() => fakeWs),
  },
}))

vi.mock('wavesurfer.js/plugins/regions', () => ({
  default: {
    create: vi.fn(() => fakeRegionsApi),
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
})
