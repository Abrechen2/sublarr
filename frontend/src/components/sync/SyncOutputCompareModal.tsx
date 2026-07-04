/**
 * SyncOutputCompareModal — non-destructive sync preview (V1.6 #4).
 *
 * Fetches candidate outputs from POST /tools/video-sync/compare (which never
 * overwrites the sidecar), shows the original timeline vs each engine's synced
 * timeline side by side, and lets the user keep the original or apply a chosen
 * engine. "Apply" runs the existing async sync job (POST /tools/video-sync).
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Loader2, AlertTriangle, Check, X, ArrowRight } from 'lucide-react'
import { syncCompare, startVideoSync } from '@/api/client'
import type { SyncCandidate } from '@/api/client'
import { toast } from '@/components/shared/Toast'

interface Props {
  subtitlePath: string
  videoPath: string
  onClose: () => void
  onApplied: () => void
}

const MAX_ROWS = 200

function fmt(ms: number): string {
  const sign = ms < 0 ? '-' : ''
  const a = Math.abs(ms)
  const m = Math.floor(a / 60000)
  const s = Math.floor((a % 60000) / 1000)
  const cs = Math.floor((a % 1000) / 10)
  return `${sign}${m}:${String(s).padStart(2, '0')}.${String(cs).padStart(2, '0')}`
}

function delta(ms: number): string {
  return `${ms >= 0 ? '+' : ''}${(ms / 1000).toFixed(2)}s`
}

export function SyncOutputCompareModal({ subtitlePath, videoPath, onClose, onApplied }: Props) {
  const { t } = useTranslation('library')
  const fileName = subtitlePath.split(/[\\/]/).pop() ?? subtitlePath

  const { data, isLoading, isError } = useQuery({
    queryKey: ['sync-compare', subtitlePath, videoPath],
    queryFn: () => syncCompare({ file_path: subtitlePath, video_path: videoPath }),
    retry: false,
    staleTime: 0,
  })

  const okCandidates = useMemo(
    () => (data?.candidates ?? []).filter((c): c is SyncCandidate & { cues: NonNullable<SyncCandidate['cues']> } => c.status === 'ok' && !!c.cues),
    [data],
  )
  const failed = (data?.candidates ?? []).filter((c) => c.status !== 'ok')

  const [selected, setSelected] = useState<'ffsubsync' | 'alass' | null>(null)
  const active = okCandidates.find((c) => c.engine === selected) ?? okCandidates[0] ?? null

  const apply = useMutation({
    mutationFn: (engine: 'ffsubsync' | 'alass') =>
      startVideoSync({ file_path: subtitlePath, video_path: videoPath, engine }),
    onSuccess: () => {
      toast(t('sync_compare.applied'))
      onApplied()
    },
    onError: () => toast(t('sync_compare.apply_failed'), 'error'),
  })

  const original = data?.original ?? []
  const rows = active ? Math.min(Math.max(original.length, active.cues.length), MAX_ROWS) : 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sync-compare-title"
        className="w-full max-w-2xl rounded-lg flex flex-col"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', maxHeight: '85vh' }}
      >
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <div>
            <h2 id="sync-compare-title" className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
              {t('sync_compare.title')}
            </h2>
            <p className="text-[11px] text-muted truncate">{fileName}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded" style={{ color: 'var(--text-muted)' }} title={t('sync_compare.close')}>
            <X size={16} />
          </button>
        </div>

        <div className="px-4 py-3 overflow-auto">
          {isLoading && (
            <div className="flex items-center gap-2 justify-center py-8" style={{ color: 'var(--text-muted)' }}>
              <Loader2 size={16} className="animate-spin" /> {t('sync_compare.running')}
            </div>
          )}

          {(isError || (data && !data.any_output)) && !isLoading && (
            <div className="flex items-start gap-2 py-4" style={{ color: 'var(--warning)' }}>
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              <div className="text-xs">
                <p className="font-medium">{t('sync_compare.no_output')}</p>
                {failed.map((c) => (
                  <p key={c.engine} className="text-[11px] mt-1">
                    {c.engine}: {t(`sync_compare.status_${c.status}`)}{c.error ? ` — ${c.error}` : ''}
                  </p>
                ))}
              </div>
            </div>
          )}

          {active && (
            <>
              {/* Engine selector (when more than one engine produced output) */}
              {okCandidates.length > 1 && (
                <div className="flex gap-1.5 mb-2">
                  {okCandidates.map((c) => (
                    <button
                      key={c.engine}
                      onClick={() => setSelected(c.engine)}
                      className="px-2 py-1 rounded text-[11px] font-medium"
                      style={{
                        backgroundColor: c.engine === active.engine ? 'var(--accent-bg)' : 'var(--bg-primary)',
                        border: `1px solid ${c.engine === active.engine ? 'var(--accent-dim)' : 'var(--border)'}`,
                        color: c.engine === active.engine ? 'var(--accent)' : 'var(--text-secondary)',
                      }}
                    >
                      {c.engine}
                    </button>
                  ))}
                </div>
              )}

              <p className="text-[11px] text-muted mb-2">
                {t('sync_compare.shift_summary', {
                  engine: active.engine,
                  shift: active.shift_ms != null ? delta(active.shift_ms) : '—',
                })}
              </p>

              {/* Side-by-side cue table */}
              <div className="rounded border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
                <div className="grid grid-cols-[1fr_1fr] text-[10px] font-semibold uppercase" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}>
                  <div className="px-2 py-1">{t('sync_compare.original')}</div>
                  <div className="px-2 py-1" style={{ borderLeft: '1px solid var(--border)' }}>{t('sync_compare.synced', { engine: active.engine })}</div>
                </div>
                <div style={{ maxHeight: '40vh', overflowY: 'auto' }}>
                  {Array.from({ length: rows }, (_, i) => {
                    const o = original[i]
                    const s = active.cues[i]
                    return (
                      <div key={i} className="grid grid-cols-[1fr_1fr] text-[11px]" style={{ borderTop: '1px solid var(--border)' }}>
                        <div className="px-2 py-1" style={{ color: 'var(--text-secondary)' }}>
                          {o ? <><span style={{ fontFamily: 'var(--font-mono)' }}>{fmt(o.start)}</span> <span className="opacity-60 truncate">{o.text}</span></> : ''}
                        </div>
                        <div className="px-2 py-1 flex items-center gap-1" style={{ borderLeft: '1px solid var(--border)', color: 'var(--text-primary)' }}>
                          {s ? (
                            <>
                              <span style={{ fontFamily: 'var(--font-mono)' }}>{fmt(s.start)}</span>
                              {o && s.start !== o.start && (
                                <span className="text-[9px]" style={{ color: 'var(--accent)' }}>
                                  <ArrowRight size={8} className="inline" />{delta(s.start - o.start)}
                                </span>
                              )}
                            </>
                          ) : ''}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
              {Math.max(original.length, active.cues.length) > MAX_ROWS && (
                <p className="text-[10px] text-muted mt-1">{t('sync_compare.truncated', { shown: MAX_ROWS })}</p>
              )}
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 px-4 py-3" style={{ borderTop: '1px solid var(--border)' }}>
          <button onClick={onClose} className="rounded px-3 py-1.5 text-xs" style={{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
            {t('sync_compare.keep_original')}
          </button>
          {active && (
            <button
              onClick={() => apply.mutate(active.engine)}
              disabled={apply.isPending}
              className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)', opacity: apply.isPending ? 0.5 : 1 }}
            >
              {apply.isPending ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              {t('sync_compare.apply', { engine: active.engine })}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
