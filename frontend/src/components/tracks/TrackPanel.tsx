import { useState, useEffect, useCallback } from 'react'
import { Loader2, Download, FileText, AlertTriangle, Trash2 } from 'lucide-react'
import { listEpisodeTracks, extractTrack, convertSubtitle, removeTrackFromContainer, getRemuxJob } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import type { Track, EpisodeTracksResponse } from '@/lib/types'

interface TrackPanelProps {
  episodeId: number
  onOpenEditor: (filePath: string) => void
}

function codecColor(codecType: 'audio' | 'subtitle', codec: string): { bg: string; text: string } {
  if (codecType === 'audio') return { bg: 'rgba(99,102,241,0.12)', text: '#818cf8' }
  if (codec === 'ass' || codec === 'ssa') return { bg: 'rgba(16,185,129,0.12)', text: 'var(--success)' }
  if (codec === 'hdmv_pgs_subtitle' || codec === 'dvd_subtitle') return { bg: 'rgba(245,158,11,0.12)', text: 'var(--warning)' }
  return { bg: 'var(--bg-surface)', text: 'var(--text-secondary)' }
}

function TrackRow({ track, episodeId, videoPath, onOpenEditor }: { track: Track; episodeId: number; videoPath: string; onOpenEditor: (p: string) => void }) {
  const [extracting, setExtracting] = useState(false)
  const [usingAsSource, setUsingAsSource] = useState(false)
  const [converting, setConverting] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const isSubtitle = track.codec_type === 'subtitle'
  const isImageBased = track.codec === 'hdmv_pgs_subtitle' || track.codec === 'dvd_subtitle'
  const { bg, text } = codecColor(track.codec_type, track.codec)

  const handleExtract = async () => {
    setExtracting(true)
    try {
      const result = await extractTrack(episodeId, track.index)
      toast(`Extrahiert: ${result.output_path.split(/[\\/]/).pop()}`)
    } catch {
      toast('Extraktion fehlgeschlagen', 'error')
    } finally {
      setExtracting(false)
    }
  }

  const handleUseAsSource = async () => {
    setUsingAsSource(true)
    try {
      const result = await extractTrack(episodeId, track.index)
      onOpenEditor(result.output_path)
    } catch {
      toast('Extraktion fehlgeschlagen', 'error')
    } finally {
      setUsingAsSource(false)
    }
  }

  const pollRemuxJob = useCallback(async (jobId: string) => {
    const maxAttempts = 60
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 3000))
      try {
        const job = await getRemuxJob(jobId)
        if (job.status === 'completed') {
          toast('Stream aus Container entfernt — Backup erstellt')
          setRemoving(false)
          return
        }
        if (job.status === 'failed') {
          toast(`Remux fehlgeschlagen: ${job.error ?? 'Unbekannter Fehler'}`, 'error')
          setRemoving(false)
          return
        }
      } catch {
        // network hiccup — keep polling
      }
    }
    toast('Remux-Job Timeout — prüfe Logs', 'error')
    setRemoving(false)
  }, [])

  const handleRemoveFromContainer = async () => {
    if (!confirmRemove) {
      setConfirmRemove(true)
      return
    }
    setConfirmRemove(false)
    setRemoving(true)
    try {
      const { job_id } = await removeTrackFromContainer(episodeId, track.index)
      void pollRemuxJob(job_id)
    } catch {
      toast('Remux konnte nicht gestartet werden', 'error')
      setRemoving(false)
    }
  }

  const handleConvert = async (targetFormat: string) => {
    setConverting(true)
    try {
      const result = await convertSubtitle({
        track_index: track.index,
        video_path: videoPath,
        target_format: targetFormat as 'srt' | 'ass' | 'ssa' | 'vtt',
      })
      toast(`Konvertiert: ${result.output_path.split(/[\\/]/).pop()}`)
    } catch {
      toast('Konvertierung fehlgeschlagen', 'error')
    } finally {
      setConverting(false)
    }
  }

  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      {/* Index */}
      <td className="px-3 py-1.5 text-xs tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
        #{track.index}
      </td>
      {/* Type */}
      <td className="px-3 py-1.5">
        <span
          className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
          style={{ backgroundColor: bg, color: text, fontFamily: 'var(--font-mono)' }}
        >
          {track.codec === 'hdmv_pgs_subtitle' ? 'PGS' : track.codec === 'dvd_subtitle' ? 'VobSub' : track.codec.toUpperCase()}
        </span>
      </td>
      {/* Language */}
      <td className="px-3 py-1.5">
        {track.language ? (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold"
            style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
          >
            {track.language}
          </span>
        ) : (
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>und</span>
        )}
      </td>
      {/* Title */}
      <td className="px-3 py-1.5 text-xs truncate max-w-[160px]" style={{ color: 'var(--text-secondary)' }}>
        {track.title || <span style={{ color: 'var(--text-muted)' }}>—</span>}
      </td>
      {/* Flags */}
      <td className="px-3 py-1.5">
        <div className="flex items-center gap-1">
          {track.default && (
            <span className="text-[9px] px-1 py-0.5 rounded uppercase font-bold" style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}>
              Default
            </span>
          )}
          {track.forced && (
            <span className="text-[9px] px-1 py-0.5 rounded uppercase font-bold" style={{ backgroundColor: 'rgba(245,158,11,0.12)', color: 'var(--warning)' }}>
              Forced
            </span>
          )}
        </div>
      </td>
      {/* Actions */}
      <td className="px-3 py-1.5">
        {isSubtitle && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => void handleExtract()}
              disabled={extracting || usingAsSource}
              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors"
              style={{
                backgroundColor: 'var(--bg-surface)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                opacity: extracting ? 0.6 : 1,
              }}
              title="Als Sidecar-Datei extrahieren"
            >
              {extracting ? <Loader2 size={10} className="animate-spin" /> : <Download size={10} />}
              Extrahieren
            </button>
            {!isImageBased && (
              <button
                onClick={() => void handleUseAsSource()}
                disabled={extracting || usingAsSource}
                className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors"
                style={{
                  backgroundColor: 'var(--accent-bg)',
                  color: 'var(--accent)',
                  border: '1px solid var(--accent-dim)',
                  opacity: usingAsSource ? 0.6 : 1,
                }}
                title="Im Editor öffnen"
              >
                {usingAsSource ? <Loader2 size={10} className="animate-spin" /> : <FileText size={10} />}
                Als Quelle
              </button>
            )}
            {!isImageBased && (
              converting
                ? <Loader2 size={10} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
                : (
                  <select
                    defaultValue=""
                    disabled={extracting || usingAsSource || converting}
                    onChange={(e) => { if (e.target.value) { void handleConvert(e.target.value); e.target.value = '' } }}
                    className="px-1.5 py-1 rounded text-[10px] font-medium"
                    style={{
                      backgroundColor: 'var(--bg-surface)',
                      color: 'var(--text-secondary)',
                      border: '1px solid var(--border)',
                    }}
                    title="In anderes Format konvertieren"
                  >
                    <option value="">Konvertieren…</option>
                    {(['srt', 'ass', 'vtt'] as const)
                      .filter((f) => f !== track.codec.replace('subrip', 'srt').replace('ssa', 'ass'))
                      .map((f) => (
                        <option key={f} value={f}>{f.toUpperCase()}</option>
                      ))}
                  </select>
                )
            )}
            {isSubtitle && (
              removing ? (
                <Loader2 size={10} className="animate-spin ml-1" style={{ color: 'var(--text-muted)' }} />
              ) : (
                <button
                  onClick={() => void handleRemoveFromContainer()}
                  disabled={extracting || usingAsSource || converting}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors ml-1"
                  style={{
                    backgroundColor: confirmRemove ? 'rgba(239,68,68,0.15)' : 'var(--bg-surface)',
                    color: confirmRemove ? '#ef4444' : 'var(--text-muted)',
                    border: confirmRemove ? '1px solid rgba(239,68,68,0.4)' : '1px solid var(--border)',
                  }}
                  title={confirmRemove ? 'Klicke erneut zur Bestätigung' : 'Stream aus Container entfernen (erstellt .bak Backup)'}
                  onBlur={() => setConfirmRemove(false)}
                >
                  <Trash2 size={10} />
                  {confirmRemove ? 'Sicher?' : 'Entfernen'}
                </button>
              )
            )}
          </div>
        )}
      </td>
    </tr>
  )
}

export function TrackPanel({ episodeId, onOpenEditor }: TrackPanelProps) {
  const [result, setResult] = useState<EpisodeTracksResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listEpisodeTracks(episodeId)
      .then((data) => { if (!cancelled) { setResult(data); setLoading(false) } })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : 'Fehler beim Laden der Tracks'
          setError(msg)
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [episodeId])

  if (loading) {
    return (
      <div className="px-4 py-3 flex items-center gap-2 text-sm" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}>
        <Loader2 size={14} className="animate-spin" />
        Tracks werden geladen…
      </div>
    )
  }

  if (error) {
    return (
      <div className="px-4 py-3 flex items-center gap-2 text-xs" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--error)' }}>
        <AlertTriangle size={14} />
        {error}
      </div>
    )
  }

  if (!result || result.tracks.length === 0) {
    return (
      <div className="px-4 py-3 text-sm" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}>
        Keine eingebetteten Tracks gefunden.
      </div>
    )
  }

  const subtitles = result.tracks.filter((t) => t.codec_type === 'subtitle')
  const audio = result.tracks.filter((t) => t.codec_type === 'audio')

  return (
    <div style={{ backgroundColor: 'var(--bg-primary)' }} className="px-4 py-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          Eingebettete Tracks ({result.tracks.length})
        </span>
        <span className="text-[10px]" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {subtitles.length} Sub · {audio.length} Audio
        </span>
      </div>

      <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
              {['#', 'Format', 'Sprache', 'Titel', 'Flags', 'Aktionen'].map((h) => (
                <th
                  key={h}
                  className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.tracks.map((track) => (
              <TrackRow
                key={track.index}
                track={track}
                episodeId={episodeId}
                videoPath={result.video_path}
                onOpenEditor={onOpenEditor}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
