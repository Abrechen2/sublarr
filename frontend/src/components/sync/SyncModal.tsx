/**
 * SyncModal — AI-based subtitle sync using ffsubsync (speech detection) or alass (reference track).
 *
 * Starts an async job via POST /tools/video-sync, then polls the job status every 1.5s
 * until the job completes or fails. Supports alass with track selection from the embedded
 * track list of the episode.
 */

import { useState, useEffect, useCallback } from 'react'
import { X, Loader2, Check, AlertTriangle } from 'lucide-react'
import { getSyncEngines, startVideoSync, getSyncJobStatus, listEpisodeTracks } from '@/api/client'
import type { Track } from '@/lib/types'

interface SyncModalProps {
  episodeId: number
  subtitlePath: string
  videoPath: string
  onClose: () => void
  onComplete: () => void
}

type JobStatus = 'idle' | 'starting' | 'queued' | 'running' | 'completed' | 'failed'

export function SyncModal({ episodeId, subtitlePath, videoPath, onClose, onComplete }: SyncModalProps) {
  const [engines, setEngines] = useState<Record<string, boolean>>({})
  const [engine, setEngine] = useState<'ffsubsync' | 'alass'>('ffsubsync')
  const [tracks, setTracks] = useState<Track[]>([])
  const [refTrackIdx, setRefTrackIdx] = useState<number | undefined>()
  const [jobId, setJobId] = useState<string | null>(null)
  const [status, setStatus] = useState<JobStatus>('idle')
  const [shiftMs, setShiftMs] = useState<number | undefined>()
  const [error, setError] = useState<string | null>(null)

  const fileName = subtitlePath.split(/[\\/]/).pop() ?? subtitlePath

  // Load engines on mount
  useEffect(() => {
    void getSyncEngines().then(setEngines).catch(() => {})
  }, [])

  // Load subtitle tracks when alass is selected (for reference track picker).
  // Tracks default to [] and refTrackIdx to undefined, so no synchronous reset needed.
  useEffect(() => {
    if (engine !== 'alass') return
    void listEpisodeTracks(episodeId).then((r) => {
      setTracks(r.tracks.filter((t) => t.codec_type === 'subtitle'))
      setRefTrackIdx(undefined)
    }).catch(() => {})
  }, [engine, episodeId])

  // Poll job status
  useEffect(() => {
    if (!jobId || status === 'completed' || status === 'failed') return
    const interval = setInterval(() => {
      void getSyncJobStatus(jobId).then((r) => {
        setStatus(r.status as JobStatus)
        if (r.result && typeof r.result === 'object' && 'shift_ms' in r.result) {
          setShiftMs(r.result.shift_ms as number)
        }
        if (r.error) setError(r.error)
        if (r.status === 'completed') onComplete()
      }).catch(() => {})
    }, 1500)
    return () => clearInterval(interval)
  }, [jobId, status, onComplete])

  const handleStart = useCallback(async () => {
    setError(null)
    setStatus('starting')
    try {
      const r = await startVideoSync({
        file_path: subtitlePath,
        video_path: videoPath,
        engine,
        reference_track_index: engine === 'alass' ? refTrackIdx : undefined,
      })
      setJobId(r.job_id)
      setStatus('queued')
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? ((e as { response?: { data?: { error?: string } } }).response?.data?.error ?? 'Sync-Start fehlgeschlagen')
          : 'Sync-Start fehlgeschlagen'
      setError(msg)
      setStatus('idle')
    }
  }, [subtitlePath, videoPath, engine, refTrackIdx])

  const isRunning = status === 'starting' || status === 'queued' || status === 'running'
  const canStart = status === 'idle' && !(engine === 'alass' && refTrackIdx === undefined)

  const statusLabel: Record<JobStatus, string> = {
    idle: '',
    starting: 'Starte…',
    queued: 'In Warteschlange…',
    running: 'Läuft…',
    completed: 'Fertig',
    failed: 'Fehlgeschlagen',
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0,0,0,0.65)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-md mx-4 rounded-lg overflow-hidden flex flex-col"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          <div>
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              Untertitel synchronisieren
            </p>
            <p className="text-xs truncate max-w-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {fileName}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded transition-colors"
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-4 py-4 space-y-4">
          {/* Engine selector */}
          <div>
            <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
              Engine
            </p>
            <div className="flex gap-2">
              {(['ffsubsync', 'alass'] as const).map((e) => (
                <button
                  key={e}
                  onClick={() => setEngine(e)}
                  disabled={isRunning || engines[e] === false}
                  className="flex-1 px-3 py-2 rounded text-xs font-medium transition-colors"
                  style={{
                    backgroundColor: engine === e ? 'var(--accent-bg)' : 'var(--bg-primary)',
                    border: `1px solid ${engine === e ? 'var(--accent-dim)' : 'var(--border)'}`,
                    color: engine === e ? 'var(--accent)' : 'var(--text-secondary)',
                    opacity: engines[e] === false ? 0.4 : 1,
                  }}
                >
                  {e}
                  {engines[e] === false && (
                    <span className="ml-1" style={{ color: 'var(--text-muted)' }}>(nicht installiert)</span>
                  )}
                </button>
              ))}
            </div>
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              {engine === 'ffsubsync'
                ? 'Sprachbasiert — analysiert Audio-Sprachaktivität'
                : 'Referenz-Untertitel — synchronisiert gegen einen eingebetteten Track'}
            </p>
          </div>

          {/* Reference track selector (alass only) */}
          {engine === 'alass' && (
            <div>
              <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                Referenz-Track
              </p>
              {tracks.length === 0 ? (
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  Keine eingebetteten Untertitel-Tracks gefunden.
                </p>
              ) : (
                <select
                  value={refTrackIdx ?? ''}
                  disabled={isRunning}
                  onChange={(e) => setRefTrackIdx(e.target.value ? Number(e.target.value) : undefined)}
                  className="w-full px-3 py-2 rounded text-sm"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                  }}
                >
                  <option value="">— Track wählen —</option>
                  {tracks.map((t) => (
                    <option key={t.index} value={t.index}>
                      [{t.index}] {t.language} — {t.codec.toUpperCase()}
                      {t.title ? ` (${t.title})` : ''}
                      {t.forced ? ' [Forced]' : ''}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {/* Status / result */}
          {status !== 'idle' && (
            <div
              className="flex items-center gap-2 px-3 py-2 rounded text-xs"
              style={{
                backgroundColor: status === 'completed'
                  ? 'var(--success-bg)'
                  : status === 'failed'
                    ? 'var(--error-bg)'
                    : 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: status === 'completed'
                  ? 'var(--success)'
                  : status === 'failed'
                    ? 'var(--error)'
                    : 'var(--text-secondary)',
              }}
            >
              {isRunning && <Loader2 size={12} className="animate-spin shrink-0" />}
              {status === 'completed' && <Check size={12} className="shrink-0" />}
              {status === 'failed' && <AlertTriangle size={12} className="shrink-0" />}
              <span>
                {statusLabel[status]}
                {status === 'completed' && shiftMs !== undefined && ` — Versatz: ${shiftMs > 0 ? '+' : ''}${shiftMs} ms`}
              </span>
            </div>
          )}

          {error && (
            <p className="text-xs px-1" style={{ color: 'var(--error)' }}>
              {error}
            </p>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex justify-end gap-2 px-4 py-3"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <button
            onClick={onClose}
            className="px-4 py-2 rounded text-sm transition-colors"
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            Schließen
          </button>
          <button
            onClick={() => void handleStart()}
            disabled={!canStart || isRunning}
            className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium text-white transition-opacity"
            style={{
              backgroundColor: 'var(--accent)',
              opacity: canStart && !isRunning ? 1 : 0.4,
            }}
          >
            {isRunning && <Loader2 size={14} className="animate-spin" />}
            {isRunning ? 'Läuft…' : 'Starten'}
          </button>
        </div>
      </div>
    </div>
  )
}
