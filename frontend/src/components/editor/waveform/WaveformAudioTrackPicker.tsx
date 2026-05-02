/**
 * WaveformAudioTrackPicker — dropdown letting the user switch between
 * audio streams of the underlying video file (Plan B8 Task 6 Step 3).
 *
 * The `value` is the **audio-position** (0-based among audio streams),
 * which is what the backend's `/tools/waveform-extract` route accepts as
 * `track_index` (mapped to ffmpeg's `0:a:<idx>`). The absolute ffprobe
 * `index` is only used for label disambiguation.
 *
 * Hidden when there is at most one audio track — there's no useful
 * choice to offer.
 */

import type { AudioTrack } from '@/api/system/tools'

export interface WaveformAudioTrackPickerProps {
  tracks: AudioTrack[]
  /** 0-based position WITHIN the audio-tracks list. */
  selectedAudioIdx: number
  onChange: (audioIdx: number) => void
}

function describeTrack(track: AudioTrack): string {
  const channels =
    track.channels === 1 ? 'mono' : track.channels === 2 ? 'stereo' : `${track.channels}ch`
  const language = track.language || 'und'
  const title = track.title ? ` "${track.title}"` : ''
  const flags = [
    track.default ? 'default' : null,
    track.forced ? 'forced' : null,
  ].filter(Boolean)
  const flagSuffix = flags.length > 0 ? ` (${flags.join(', ')})` : ''
  return `${language} · ${track.codec} · ${channels}${title}${flagSuffix}`
}

export function WaveformAudioTrackPicker({
  tracks,
  selectedAudioIdx,
  onChange,
}: WaveformAudioTrackPickerProps) {
  if (tracks.length <= 1) return null

  return (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      Track:
      <select
        value={selectedAudioIdx}
        onChange={(e) => onChange(Number(e.target.value))}
        className="bg-surface text-primary border border-border rounded px-1.5 py-0.5 text-xs"
      >
        {tracks.map((track, audioIdx) => (
          <option key={track.index} value={audioIdx}>
            {describeTrack(track)}
          </option>
        ))}
      </select>
    </label>
  )
}
