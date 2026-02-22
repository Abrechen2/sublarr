/**
 * WaveformTab — audio waveform visualization for subtitle timing.
 *
 * Extracts audio from the video file via the backend, loads it into WaveSurfer,
 * and overlays subtitle cue regions on the waveform. Provides play/pause
 * playback controls. Read-only: regions are displayed but not editable.
 */

import { useEffect, useRef, useState } from 'react'
import WaveSurfer from 'wavesurfer.js'
import RegionsPlugin from 'wavesurfer.js/plugins/regions'
import { Loader2, Play, Pause } from 'lucide-react'
import { useSubtitleParse } from '@/hooks/useApi'
import { extractWaveform } from '@/api/client'

interface WaveformTabProps {
  subtitlePath: string
  videoPath: string
}

export function WaveformTab({ subtitlePath, videoPath }: WaveformTabProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WaveSurfer | null>(null)
  const regionsRef = useRef<RegionsPlugin | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [wsReady, setWsReady] = useState(false)

  const { data: parseData } = useSubtitleParse(subtitlePath)

  // Set up WaveSurfer when videoPath changes
  useEffect(() => {
    if (!containerRef.current || !videoPath) return

    const regions = RegionsPlugin.create()
    regionsRef.current = regions

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#52525b',       // zinc-600 — WaveSurfer can't use CSS vars directly
      progressColor: '#14b8a6',   // teal-500
      height: 96,
      plugins: [regions],
    })
    wsRef.current = ws

    ws.on('play', () => { setPlaying(true) })
    ws.on('pause', () => { setPlaying(false) })
    ws.on('finish', () => { setPlaying(false) })
    ws.on('ready', () => { setWsReady(true); setLoading(false) })

    void extractWaveform(videoPath)
      .then(({ audio_url }) => ws.load(audio_url))
      .catch(() => {
        setError('Waveform konnte nicht geladen werden.')
        setLoading(false)
      })

    return () => {
      ws.destroy()
      wsRef.current = null
      regionsRef.current = null
      setWsReady(false)
      setPlaying(false)
    }
  }, [videoPath])

  // Add cue regions once wavesurfer is ready and parse data is available
  useEffect(() => {
    if (!wsReady || !parseData || !regionsRef.current) return

    regionsRef.current.clearRegions()
    parseData.cues.forEach((cue, idx) => {
      regionsRef.current!.addRegion({
        id: String(idx),
        start: cue.start,
        end: cue.end,
        color: 'rgba(20, 184, 166, 0.18)',  // teal-500 low opacity
        drag: false,
        resize: false,
      })
    })
  }, [wsReady, parseData])

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm" style={{ color: 'var(--error)' }}>{error}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {loading && (
        <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-muted)' }}>
          <Loader2 size={14} className="animate-spin" />
          Audio wird extrahiert…
        </div>
      )}

      <div
        ref={containerRef}
        className="rounded overflow-hidden"
        style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
      />

      {!loading && (
        <div className="flex items-center gap-3">
          <button
            onClick={() => { void wsRef.current?.playPause() }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
            style={{
              backgroundColor: 'var(--accent-bg)',
              color: 'var(--accent)',
              border: '1px solid var(--accent-dim)',
            }}
          >
            {playing ? <Pause size={12} /> : <Play size={12} />}
            {playing ? 'Pause' : 'Play'}
          </button>

          {parseData && (
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {parseData.cue_count} Cues · {parseData.format.toUpperCase()}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
