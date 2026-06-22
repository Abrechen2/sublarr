import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Download, FileText, AlertTriangle, Trash2, ScanSearch, Sparkles } from 'lucide-react'
import { listEpisodeTracks, extractTrack, convertSubtitle, removeTrackFromContainer, getRemuxJob, restoreRemuxBackup, detectDubtitle, getCachedDubtitle } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import { HealthSection } from './HealthSection'
import type { Track, EpisodeTracksResponse, DubtitleCandidate } from '@/lib/types'

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

function DubtitleBadge({ dub }: { dub: DubtitleCandidate }) {
  const { t } = useTranslation('library')
  if (dub.is_dubtitle) {
    const score = dub.audio_score != null ? dub.audio_score.toFixed(2) : null
    return (
      <span
        className="flex items-center gap-0.5 text-[9px] px-1 py-0.5 rounded uppercase font-bold"
        style={{ backgroundColor: 'rgba(16,185,129,0.15)', color: 'var(--success)' }}
        title={score ? t('track_panel.dubtitle_score', { score }) : dub.reason}
      >
        <Sparkles size={9} />
        {t('track_panel.dubtitle_badge')}
        {score && <span className="font-mono">{score}</span>}
      </span>
    )
  }
  const labelKey = `track_panel.dub_label_${dub.tier1_label}` as const
  const score = dub.audio_score != null ? ` ${dub.audio_score.toFixed(2)}` : ''
  return (
    <span
      className="text-[9px] px-1 py-0.5 rounded uppercase font-medium"
      style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-muted)' }}
      title={dub.reason}
    >
      {t(labelKey)}
      {score && <span className="font-mono">{score}</span>}
    </span>
  )
}

function TrackRow({ track, episodeId, videoPath, onOpenEditor, dub }: { track: Track; episodeId: number; videoPath: string; onOpenEditor: (p: string) => void; dub?: DubtitleCandidate }) {
  const { t } = useTranslation('library')
  const [extracting, setExtracting] = useState(false)
  const [usingAsSource, setUsingAsSource] = useState(false)
  const [converting, setConverting] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [remuxBackup, setRemuxBackup] = useState<{ backupPath: string; videoPath: string } | null>(null)
  const [restoring, setRestoring] = useState(false)
  const isSubtitle = track.codec_type === 'subtitle'
  const isImageBased = track.codec === 'hdmv_pgs_subtitle' || track.codec === 'dvd_subtitle'
  const { bg, text } = codecColor(track.codec_type, track.codec)

  const handleExtract = async () => {
    setExtracting(true)
    try {
      const result = await extractTrack(episodeId, track.index)
      toast(t('track_panel.extracted', { name: result.output_path.split(/[\\/]/).pop() }))
    } catch {
      toast(t('track_panel.extraction_failed'), 'error')
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
      toast(t('track_panel.extraction_failed'), 'error')
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
          toast(t('track_panel.stream_removed'))
          setRemoving(false)
          if (job.result?.backup_path && job.result?.video_path) {
            setRemuxBackup({ backupPath: job.result.backup_path, videoPath: job.result.video_path })
          }
          return
        }
        if (job.status === 'failed') {
          toast(t('track_panel.remux_failed', { error: job.error ?? t('track_panel.unknown_error') }), 'error')
          setRemoving(false)
          return
        }
      } catch {
        // network hiccup — keep polling
      }
    }
    toast(t('track_panel.remux_timeout'), 'error')
    setRemoving(false)
  }, [t])

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
      toast(t('track_panel.remux_start_failed'), 'error')
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
      toast(t('track_panel.converted', { name: result.output_path.split(/[\\/]/).pop() }))
    } catch {
      toast(t('track_panel.conversion_failed'), 'error')
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
          {dub && <DubtitleBadge dub={dub} />}
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
              title={t('extract_sidecar')}
            >
              {extracting ? <Loader2 size={10} className="animate-spin" /> : <Download size={10} />}
              {t('track_panel.extract')}
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
                title={t('track_panel.open_in_editor')}
              >
                {usingAsSource ? <Loader2 size={10} className="animate-spin" /> : <FileText size={10} />}
                {t('track_panel.as_source')}
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
                    title={t('track_panel.convert_format')}
                  >
                    <option value="">{t('track_panel.converting_ellipsis')}</option>
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
              ) : remuxBackup ? (
                restoring ? (
                  <Loader2 size={10} className="animate-spin ml-1" style={{ color: 'var(--text-muted)' }} />
                ) : (
                  <button
                    onClick={() => {
                      setRestoring(true)
                      restoreRemuxBackup(remuxBackup.backupPath, remuxBackup.videoPath)
                        .then(() => { toast(t('track_panel.stream_restored')); setRemuxBackup(null) })
                        .catch(() => toast(t('track_panel.restore_failed'), 'error'))
                        .finally(() => setRestoring(false))
                    }}
                    className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors ml-1"
                    style={{
                      backgroundColor: 'rgba(245,158,11,0.12)',
                      color: 'var(--warning)',
                      border: '1px solid rgba(245,158,11,0.3)',
                    }}
                    title={t('restore_from_backup')}
                  >
                    <Trash2 size={10} />
                    {t('track_panel.undo')}
                  </button>
                )
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
                  title={confirmRemove ? t('track_panel.confirm_again_title') : t('track_panel.remove_from_container_title')}
                  onBlur={() => setConfirmRemove(false)}
                  data-testid={`remux-remove-track-${track.index}`}
                >
                  <Trash2 size={10} />
                  {confirmRemove ? t('track_panel.sure') : t('track_panel.remove')}
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
  const { t } = useTranslation('library')
  const [result, setResult] = useState<EpisodeTracksResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detecting, setDetecting] = useState(false)
  const [dubCandidates, setDubCandidates] = useState<Map<number, DubtitleCandidate> | null>(null)
  const [dubMessage, setDubMessage] = useState<string | null>(null)

  // Auto-load a previously cached result (from a prior detect or the
  // scheduled sweep) so the dubtitle flag shows on open without re-detecting.
  useEffect(() => {
    let cancelled = false
    getCachedDubtitle(episodeId)
      .then((res) => {
        if (!cancelled && res) {
          setDubCandidates(new Map(res.candidates.map((c) => [c.sub_index, c])))
          setDubMessage(res.message)
        }
      })
      .catch(() => { /* no cached result — silent */ })
    return () => { cancelled = true }
  }, [episodeId])

  const handleDetectDubtitle = async () => {
    setDetecting(true)
    try {
      const res = await detectDubtitle(episodeId)
      setDubCandidates(new Map(res.candidates.map((c) => [c.sub_index, c])))
      setDubMessage(res.message)
    } catch {
      toast(t('track_panel.dubtitle_detect_failed'), 'error')
    } finally {
      setDetecting(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    listEpisodeTracks(episodeId)
      .then((data) => { if (!cancelled) { setResult(data); setLoading(false) } })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : t('track_panel.load_error')
          setError(msg)
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [episodeId, t])

  if (loading) {
    return (
      <div className="px-4 py-3 flex items-center gap-2 text-sm" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}>
        <Loader2 size={14} className="animate-spin" />
        {t('track_panel.loading_tracks')}
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
        {t('track_panel.no_tracks')}
      </div>
    )
  }

  const subtitles = result.tracks.filter((t) => t.codec_type === 'subtitle')
  const audio = result.tracks.filter((t) => t.codec_type === 'audio')

  return (
    <div style={{ backgroundColor: 'var(--bg-primary)' }} className="px-4 py-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          {t('track_panel.embedded_tracks_count', { count: result.tracks.length })}
        </span>
        <div className="flex items-center gap-2">
          {subtitles.length > 1 && (
            <button
              onClick={() => void handleDetectDubtitle()}
              disabled={detecting}
              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors"
              style={{
                backgroundColor: 'var(--accent-bg)',
                color: 'var(--accent)',
                border: '1px solid var(--accent-dim)',
                opacity: detecting ? 0.6 : 1,
              }}
              title={t('track_panel.dubtitle_detect')}
            >
              {detecting ? <Loader2 size={10} className="animate-spin" /> : <ScanSearch size={10} />}
              {detecting ? t('track_panel.dubtitle_detecting') : t('track_panel.dubtitle_detect')}
            </button>
          )}
          <span className="text-[10px]" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {t('track_panel.sub_audio_count', { sub: subtitles.length, audio: audio.length })}
          </span>
        </div>
      </div>

      {dubMessage && (
        <div
          className="flex items-start gap-2 px-3 py-2 rounded-md text-xs"
          style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--text-secondary)', border: '1px solid var(--accent-dim)' }}
        >
          <Sparkles size={13} style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 1 }} />
          <span>{dubMessage}</span>
        </div>
      )}

      <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
              {['#', t('track_panel.col_format'), t('track_panel.col_language'), t('track_panel.col_title'), t('track_panel.col_flags'), t('track_panel.col_actions')].map((h) => (
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
                dub={track.codec_type === 'subtitle' ? dubCandidates?.get(track.sub_index) : undefined}
              />
            ))}
          </tbody>
        </table>
      </div>

      <HealthSection episodeId={episodeId} onOpenEditor={onOpenEditor} />
    </div>
  )
}
