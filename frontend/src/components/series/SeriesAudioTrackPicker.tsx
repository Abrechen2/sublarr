/**
 * SeriesAudioTrackPicker — lets users pin a preferred audio track index for a series.
 *
 * Loads audio tracks from the first available episode, then lets the user pick
 * one (or clear the preference back to "auto"). The picked index is stored via
 * PUT /series/<id>/audio-track-pref and used by the Whisper transcription queue.
 */

import { useState } from 'react'
import { Loader2, Music } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { listEpisodeTracks } from '@/api/client'
import { useSeriesAudioPref, useSetSeriesAudioPref } from '@/hooks/useApi'
import type { EpisodeInfo } from '@/lib/types'

interface Props {
  seriesId: number
  episodes: EpisodeInfo[]
}

export function SeriesAudioTrackPicker({ seriesId, episodes }: Props) {
  const [open, setOpen] = useState(false)

  const firstEpId = episodes.find(e => e.id != null)?.id ?? null

  const { data: pref, isLoading: prefLoading } = useSeriesAudioPref(seriesId)
  const setAudioPref = useSetSeriesAudioPref(seriesId)

  const { data: tracksData, isLoading: tracksLoading } = useQuery({
    queryKey: ['episode-tracks', firstEpId],
    queryFn: () => listEpisodeTracks(firstEpId!),
    enabled: firstEpId != null && open,
  })

  const audioTracks = tracksData?.tracks.filter(t => t.codec_type === 'audio') ?? []
  const currentIndex = pref?.preferred_audio_track_index ?? null

  function label() {
    if (prefLoading) return '…'
    if (currentIndex === null) return 'Auto'
    const track = audioTracks.find(t => t.sub_index === currentIndex)
    if (track) return trackLabel(track.sub_index, track.language, track.title)
    return `Track ${currentIndex}`
  }

  function trackLabel(subIndex: number, language: string, title: string) {
    const parts: string[] = [`#${subIndex}`]
    if (language) parts.push(language.toUpperCase())
    if (title) parts.push(title)
    return parts.join(' · ')
  }

  function handleSelect(value: number | null) {
    setAudioPref.mutate(value, { onSuccess: () => setOpen(false) })
  }

  if (firstEpId == null) return null

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={() => setOpen(v => !v)}
        className="inline-flex items-center gap-1.5 px-2 py-1 rounded transition-colors"
        style={{
          backgroundColor: currentIndex !== null ? 'var(--accent-bg)' : 'rgba(255,255,255,0.06)',
          color: currentIndex !== null ? 'var(--accent)' : 'var(--text-secondary)',
          cursor: 'pointer',
          fontSize: '0.7rem',
          fontWeight: 500,
        }}
        title="Preferred audio track for Whisper transcription"
        onMouseEnter={(e) => {
          if (currentIndex === null) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
        }}
        onMouseLeave={(e) => {
          if (currentIndex === null) e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)'
        }}
      >
        <Music size={11} />
        Audio: {label()}
      </button>

      {open && (
        <>
          {/* backdrop */}
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 49 }}
            onClick={() => setOpen(false)}
          />
          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              zIndex: 50,
              marginTop: 4,
              minWidth: 180,
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 6,
              padding: '4px 0',
              boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
            }}
          >
            {tracksLoading && (
              <div className="flex items-center gap-2 px-3 py-2" style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                <Loader2 size={12} className="animate-spin" /> Loading tracks…
              </div>
            )}

            {!tracksLoading && (
              <>
                <DropdownItem
                  active={currentIndex === null}
                  label="Auto (by language)"
                  onClick={() => handleSelect(null)}
                  pending={setAudioPref.isPending}
                />
                {audioTracks.map(track => (
                  <DropdownItem
                    key={track.sub_index}
                    active={currentIndex === track.sub_index}
                    label={trackLabel(track.sub_index, track.language, track.title)}
                    onClick={() => handleSelect(track.sub_index)}
                    pending={setAudioPref.isPending}
                  />
                ))}
                {audioTracks.length === 0 && (
                  <div style={{ padding: '6px 12px', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    No audio tracks found
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function DropdownItem({ active, label, onClick, pending }: {
  active: boolean
  label: string
  onClick: () => void
  pending: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={pending}
      style={{
        display: 'block',
        width: '100%',
        textAlign: 'left',
        padding: '5px 12px',
        fontSize: '0.75rem',
        color: active ? 'var(--accent)' : 'var(--text-primary)',
        backgroundColor: active ? 'var(--accent-bg)' : 'transparent',
        cursor: pending ? 'default' : 'pointer',
        opacity: pending ? 0.6 : 1,
        border: 'none',
      }}
      onMouseEnter={(e) => {
        if (!active && !pending) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.backgroundColor = 'transparent'
      }}
    >
      {label}
    </button>
  )
}
