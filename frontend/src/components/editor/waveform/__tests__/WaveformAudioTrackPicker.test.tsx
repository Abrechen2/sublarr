/**
 * Tests for `WaveformAudioTrackPicker` (Plan B8 Task 6 Step 3+4).
 *
 * The picker is a thin <select> over the audio-tracks list returned by
 * the backend. The unit it owns is the user-visible mapping between
 * tracks and their audio-position index — track 0/1/2 in the dropdown
 * must produce the same `track_index` value the backend expects in
 * `/api/v1/tools/waveform-extract`.
 */

import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { WaveformAudioTrackPicker } from '../WaveformAudioTrackPicker'
import type { AudioTrack } from '@/api/system/tools'

const TRACKS: AudioTrack[] = [
  {
    index: 1,
    codec_type: 'audio',
    codec: 'aac',
    channels: 2,
    language: 'jpn',
    title: 'Stereo',
    default: true,
    forced: false,
  },
  {
    index: 2,
    codec_type: 'audio',
    codec: 'ac3',
    channels: 6,
    language: 'eng',
    title: '5.1 Surround',
    default: false,
    forced: false,
  },
  {
    index: 3,
    codec_type: 'audio',
    codec: 'opus',
    channels: 2,
    language: 'ger',
    title: '',
    default: false,
    forced: false,
  },
]

describe('WaveformAudioTrackPicker', () => {
  it('renders one option per track with descriptive label', () => {
    render(
      <WaveformAudioTrackPicker tracks={TRACKS} selectedAudioIdx={0} onChange={vi.fn()} />,
    )

    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.options).toHaveLength(3)
    // Labels include language and channel count for disambiguation
    expect(select.options[0].textContent).toMatch(/jpn/i)
    expect(select.options[1].textContent).toMatch(/eng/i)
    expect(select.options[2].textContent).toMatch(/ger/i)
  })

  it('calls onChange with the audio-position index (0-based)', () => {
    const onChange = vi.fn()
    render(
      <WaveformAudioTrackPicker tracks={TRACKS} selectedAudioIdx={0} onChange={onChange} />,
    )

    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: '1' } })

    expect(onChange).toHaveBeenCalledWith(1)
  })

  it('reflects the current selection', () => {
    render(
      <WaveformAudioTrackPicker tracks={TRACKS} selectedAudioIdx={2} onChange={vi.fn()} />,
    )

    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.value).toBe('2')
  })

  it('renders nothing when there is only one track (no choice to offer)', () => {
    const { container } = render(
      <WaveformAudioTrackPicker
        tracks={[TRACKS[0]]}
        selectedAudioIdx={0}
        onChange={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the track list is empty', () => {
    const { container } = render(
      <WaveformAudioTrackPicker tracks={[]} selectedAudioIdx={0} onChange={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
