import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Download, FileText, AlertTriangle, Trash2, ScanSearch, Sparkles } from 'lucide-react'
import { listEpisodeTracks, extractTrack, convertSubtitle, removeTrackFromContainer, getRemuxJob, restoreRemuxBackup, detectDubtitle, getCachedDubtitle, listEpisodeSubtitles, deleteSubtitles, getSubtitleDownloadUrl, setTrackDefault } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import { HealthSection } from './HealthSection'
import type { Track, EpisodeTracksResponse, DubtitleCandidate, SidecarSubtitle } from '@/lib/types'

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
  const [settingDefault, setSettingDefault] = useState(false)
  const [isDefault, setIsDefault] = useState(track.default)
  const isSubtitle = track.codec_type === 'subtitle'
  const isAudio = track.codec_type === 'audio'
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

  const handleSetDefault = async () => {
    setSettingDefault(true)
    try {
      await setTrackDefault(episodeId, track.index)
      setIsDefault(true)
      toast(t('track_panel.set_default_done'))
    } catch {
      toast(t('track_panel.set_default_failed'), 'error')
    } finally {
      setSettingDefault(false)
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
          {isDefault && (
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
        {isAudio && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => void handleSetDefault()}
              disabled={settingDefault || isDefault}
              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors"
              style={{
                backgroundColor: 'var(--bg-surface)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                opacity: settingDefault || isDefault ? 0.5 : 1,
              }}
              title={t('track_panel.set_default_title')}
            >
              {settingDefault ? (
                <Loader2 size={10} className="animate-spin" />
              ) : (
                t('track_panel.set_default')
              )}
            </button>
          </div>
        )}
      </td>
    </tr>
  )
}

function TrackTable({
  caption,
  tracks,
  episodeId,
  videoPath,
  onOpenEditor,
  dubCandidates,
  t,
}: {
  caption: string
  tracks: Track[]
  episodeId: number
  videoPath: string
  onOpenEditor: (p: string) => void
  dubCandidates?: Map<number, DubtitleCandidate>
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  return (
    <div className="space-y-1">
      <span
        className="text-[10px] font-semibold uppercase tracking-wider"
        style={{ color: 'var(--text-muted)' }}
      >
        {caption}
      </span>
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
            {tracks.map((track) => (
              <TrackRow
                key={track.index}
                track={track}
                episodeId={episodeId}
                videoPath={videoPath}
                onOpenEditor={onOpenEditor}
                dub={dubCandidates?.get(track.sub_index)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function SidecarRow({
  sidecar,
  onOpenEditor,
  onDeleted,
  t,
}: {
  sidecar: SidecarSubtitle
  onOpenEditor: (p: string) => void
  onDeleted: (path: string) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const name = sidecar.path.split(/[\\/]/).pop() ?? sidecar.path

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setDeleting(true)
    try {
      await deleteSubtitles([sidecar.path], false)
      onDeleted(sidecar.path)
    } catch {
      toast(t('series_detail.delete_failed'), 'error')
    } finally {
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      {/* Source */}
      <td className="px-3 py-1.5">
        <span
          className="text-[9px] px-1 py-0.5 rounded uppercase font-bold"
          style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
          title={t('track_panel.source_sidecar')}
        >
          {t('track_panel.source_sidecar')}
        </span>
      </td>
      {/* Format */}
      <td className="px-3 py-1.5">
        <span
          className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
          style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
        >
          {sidecar.format.toUpperCase()}
        </span>
      </td>
      {/* Language */}
      <td className="px-3 py-1.5">
        <span className="text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold" style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}>
          {sidecar.language}
        </span>
      </td>
      {/* Title (filename) */}
      <td className="px-3 py-1.5 text-xs truncate max-w-[160px]" style={{ color: 'var(--text-secondary)' }} title={name}>
        {name}
      </td>
      {/* Flags */}
      <td className="px-3 py-1.5">
        {sidecar.modifier && (
          <span className="text-[9px] px-1 py-0.5 rounded uppercase font-bold" style={{ backgroundColor: 'rgba(245,158,11,0.12)', color: 'var(--warning)' }}>
            {sidecar.modifier}
          </span>
        )}
      </td>
      {/* Actions */}
      <td className="px-3 py-1.5">
        <div className="flex items-center gap-1">
          <button
            onClick={() => onOpenEditor(sidecar.path)}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium"
            style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
            title={t('track_panel.open_in_editor')}
          >
            <FileText size={10} />
            {t('track_panel.open_in_editor')}
          </button>
          <a
            href={getSubtitleDownloadUrl(sidecar.path)}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium"
            style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
            title={t('track_panel.download')}
          >
            <Download size={10} />
            {t('track_panel.download')}
          </a>
          <button
            onClick={() => void handleDelete()}
            onBlur={() => setConfirmDelete(false)}
            disabled={deleting}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium"
            style={{
              backgroundColor: confirmDelete ? 'rgba(239,68,68,0.15)' : 'var(--bg-surface)',
              color: confirmDelete ? '#ef4444' : 'var(--text-muted)',
              border: confirmDelete ? '1px solid rgba(239,68,68,0.4)' : '1px solid var(--border)',
            }}
          >
            <Trash2 size={10} />
            {confirmDelete ? t('track_panel.sure') : t('track_panel.delete')}
          </button>
        </div>
      </td>
    </tr>
  )
}

const _LANG3_TO_2: Record<string, string> = { ger: 'de', deu: 'de', eng: 'en', jpn: 'ja' }
function _normLang(lang: string | undefined): string {
  const n = (lang || 'und').toLowerCase().split('-')[0]
  return _LANG3_TO_2[n] ?? n
}

// Phase 3 — unified, language-first subtitle view: embedded tracks AND sidecar
// files in ONE table sorted by language, instead of two disjoint tables.
function SubtitleSection({
  subtitles,
  sidecars,
  episodeId,
  videoPath,
  onOpenEditor,
  dubCandidates,
  onSidecarDeleted,
  t,
}: {
  subtitles: Track[]
  sidecars: SidecarSubtitle[]
  episodeId: number
  videoPath: string
  onOpenEditor: (p: string) => void
  dubCandidates: Map<number, DubtitleCandidate> | null
  onSidecarDeleted: (path: string) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  type Entry =
    | { kind: 'embedded'; lang: string; track: Track }
    | { kind: 'sidecar'; lang: string; sidecar: SidecarSubtitle }
  const entries: Entry[] = [
    ...subtitles.map((tr): Entry => ({ kind: 'embedded', lang: _normLang(tr.language), track: tr })),
    ...sidecars.map((s): Entry => ({ kind: 'sidecar', lang: _normLang(s.language), sidecar: s })),
  ].sort((a, b) => a.lang.localeCompare(b.lang) || a.kind.localeCompare(b.kind))

  if (entries.length === 0) return null

  return (
    <div className="space-y-1">
      <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
        {t('track_panel.section_subtitles', { count: entries.length })}
      </span>
      <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
              {[t('track_panel.col_source'), t('track_panel.col_format'), t('track_panel.col_language'), t('track_panel.col_title'), t('track_panel.col_flags'), t('track_panel.col_actions')].map((h) => (
                <th key={h} className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((e) =>
              e.kind === 'embedded' ? (
                <TrackRow
                  key={`emb-${e.track.index}`}
                  track={e.track}
                  episodeId={episodeId}
                  videoPath={videoPath}
                  onOpenEditor={onOpenEditor}
                  dub={dubCandidates?.get(e.track.sub_index)}
                />
              ) : (
                <SidecarRow
                  key={`side-${e.sidecar.path}`}
                  sidecar={e.sidecar}
                  onOpenEditor={onOpenEditor}
                  onDeleted={onSidecarDeleted}
                  t={t}
                />
              ),
            )}
          </tbody>
        </table>
      </div>
    </div>
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
  const [sidecars, setSidecars] = useState<SidecarSubtitle[]>([])

  // Load sidecar subtitle files so they show alongside the embedded tracks
  // (both are subtitles — the panel must not hide the on-disk ones).
  useEffect(() => {
    let cancelled = false
    listEpisodeSubtitles(episodeId)
      .then((res) => {
        if (!cancelled) setSidecars(res.subtitles ?? [])
      })
      .catch(() => {
        if (!cancelled) setSidecars([])
      })
    return () => {
      cancelled = true
    }
  }, [episodeId])

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

      <SubtitleSection
        subtitles={subtitles}
        sidecars={sidecars}
        episodeId={episodeId}
        videoPath={result.video_path}
        onOpenEditor={onOpenEditor}
        dubCandidates={dubCandidates}
        onSidecarDeleted={(path) => setSidecars((prev) => prev.filter((s) => s.path !== path))}
        t={t}
      />

      {audio.length > 0 && (
        <TrackTable
          caption={t('track_panel.section_audio', { count: audio.length })}
          tracks={audio}
          episodeId={episodeId}
          videoPath={result.video_path}
          onOpenEditor={onOpenEditor}
          dubCandidates={undefined}
          t={t}
        />
      )}

      <HealthSection episodeId={episodeId} onOpenEditor={onOpenEditor} />
    </div>
  )
}
