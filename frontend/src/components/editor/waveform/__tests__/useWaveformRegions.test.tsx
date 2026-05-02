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
}

function Harness({ cues, onCueChange, audioUrl = '/fake.wav', enableDrag = true }: HarnessProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  useWaveformRegions({ container: containerRef, audioUrl, cues, onCueChange, enableDrag })
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
})
