/**
 * DecisionLogModal — "Why was this subtitle chosen?"
 *
 * Renders the recorded selection pipeline of a download (history mode) or of
 * the last unsuccessful search of a wanted item (wanted mode): searched
 * providers with hits/skip reasons, the filter funnel with per-stage reject
 * counts, download attempts, the upgrade decision, and the final selection
 * with its score breakdown. A compact view by default; the expert toggle
 * reveals per-candidate rejections, provider latencies, and raw details.
 */

import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  X, Loader2, AlertCircle, ListTree, ChevronDown, ChevronRight,
  CheckCircle2, XCircle, Clock, SkipForward, Zap, Database,
} from 'lucide-react'
import { getHistoryDecision, getWantedDecision } from '@/api/client'
import { ScoreBreakdown } from '@/components/shared/ScoreBreakdown'
import { formatProviderName } from '@/lib/utils'
import type {
  DecisionLog, DecisionLogFilterStage, DecisionLogProvider, DecisionLogSearch,
} from '@/lib/types'

interface DecisionLogModalProps {
  mode: 'history' | 'wanted'
  id: number
  title: string
  onClose: () => void
}

const STEP_KEYS: Record<string, string> = {
  target_ass_direct: 'decision.step_target_ass',
  source_ass_translation: 'decision.step_source_ass',
  target_srt_direct: 'decision.step_target_srt',
  source_srt_translation: 'decision.step_source_srt',
  translate_fallback: 'decision.step_translate_fallback',
}

const STAGE_KEYS: Record<string, string> = {
  forced_only: 'decision.stage_forced_only',
  language: 'decision.stage_language',
  format: 'decision.stage_format',
  min_score: 'decision.stage_min_score',
  blacklist: 'decision.stage_blacklist',
  profile_must_contain: 'decision.stage_must_contain',
  profile_must_not_contain: 'decision.stage_must_not_contain',
  release_group_exclude: 'decision.stage_release_group',
}

const PROVIDER_SKIP_KEYS: Record<string, string> = {
  auto_disabled: 'decision.skip_auto_disabled',
  circuit_open: 'decision.skip_circuit_open',
  rate_limited: 'decision.skip_rate_limited',
  budget_exhausted: 'decision.skip_budget',
  no_pool_key: 'decision.skip_no_pool_key',
  languages_excluded: 'decision.skip_languages_excluded',
}

function ProviderStatusIcon({ status }: { status: DecisionLogProvider['status'] }) {
  switch (status) {
    case 'ok':
      return <CheckCircle2 size={13} style={{ color: 'var(--success)' }} />
    case 'skipped':
      return <SkipForward size={13} style={{ color: 'var(--text-muted)' }} />
    case 'timeout':
      return <Clock size={13} style={{ color: 'var(--warning)' }} />
    default:
      return <XCircle size={13} style={{ color: 'var(--error)' }} />
  }
}

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      {children}
    </div>
  )
}

function FilterStageRow({ stage, expert, t }: {
  stage: DecisionLogFilterStage
  expert: boolean
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  const [open, setOpen] = useState(false)
  const label = t(STAGE_KEYS[stage.stage] ?? stage.stage)
  const extra = stage.threshold !== undefined
    ? ` (≥ ${stage.threshold})`
    : stage.wanted
      ? ` (${Array.isArray(stage.wanted) ? stage.wanted.join(', ') : stage.wanted})`
      : stage.rule
        ? ` (${stage.rule.join(', ')})`
        : ''
  const canExpand = expert && (stage.rejected?.length ?? 0) > 0

  return (
    <div className="text-xs">
      <button
        onClick={() => canExpand && setOpen(o => !o)}
        className="flex items-center gap-1.5 w-full text-left"
        style={{ color: 'var(--text-secondary)', cursor: canExpand ? 'pointer' : 'default' }}
      >
        {canExpand ? (open ? <ChevronDown size={12} /> : <ChevronRight size={12} />) : <span className="w-3" />}
        <span style={{ color: 'var(--error)', fontFamily: 'var(--font-mono)' }}>−{stage.removed}</span>
        <span>{t('decision.stage_removed', { label: label + extra })}</span>
        <span className="ml-auto" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {t('decision.stage_remaining', { count: stage.remaining })}
        </span>
      </button>
      {canExpand && open && (
        <div className="mt-1 ml-5 space-y-0.5">
          {stage.rejected!.map((r, i) => (
            <div key={i} className="flex items-center gap-2 truncate" style={{ color: 'var(--text-muted)' }}>
              <span className="capitalize shrink-0">{formatProviderName(r.provider)}</span>
              <span className="uppercase shrink-0" style={{ fontFamily: 'var(--font-mono)' }}>{r.language}</span>
              <span className="uppercase shrink-0" style={{ fontFamily: 'var(--font-mono)' }}>{r.format}</span>
              <span className="shrink-0 tabular-nums" style={{ fontFamily: 'var(--font-mono)' }}>{r.score}</span>
              <span className="truncate" title={r.filename}>{r.filename}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function SearchSection({ search, expert, t }: {
  search: DecisionLogSearch
  expert: boolean
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  const okProviders = search.providers.filter(p => p.status === 'ok')
  return (
    <SectionCard>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t(STEP_KEYS[search.step] ?? search.step)}
        </span>
        {search.format && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
            style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
          >
            {search.format}
          </span>
        )}
        {search.languages.map(l => (
          <span
            key={l}
            className="text-[10px] px-1.5 py-0.5 rounded uppercase"
            style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
          >
            {l}
          </span>
        ))}
        {search.cache_hit && (
          <span className="flex items-center gap-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
            <Database size={11} /> {t('decision.cache_hit')}
          </span>
        )}
        <span className="ml-auto text-xs tabular-nums" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {t('decision.results_summary', { total: search.results_total, final: search.results_final })}
        </span>
      </div>

      {/* Providers */}
      {search.providers.length > 0 && (
        <div className="space-y-1">
          {search.providers.map((p, i) => (
            <div key={i} className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <ProviderStatusIcon status={p.status} />
              <span className="capitalize font-medium">{formatProviderName(p.name)}</span>
              {p.status === 'ok' && (
                <span style={{ color: 'var(--text-muted)' }}>
                  {t('decision.provider_hits', { count: p.hits ?? 0 })}
                  {expert && p.elapsed_ms !== undefined ? ` · ${p.elapsed_ms} ms` : ''}
                </span>
              )}
              {p.status === 'skipped' && (
                <span style={{ color: 'var(--text-muted)' }}>
                  {t(PROVIDER_SKIP_KEYS[p.reason ?? ''] ?? 'decision.skip_generic')}
                  {expert && p.detail ? ` — ${p.detail}` : ''}
                </span>
              )}
              {p.status === 'timeout' && <span style={{ color: 'var(--warning)' }}>{t('decision.provider_timeout')}</span>}
              {p.status === 'rate_limited' && <span style={{ color: 'var(--warning)' }}>{t('decision.provider_rate_limited')}</span>}
              {p.status === 'error' && (
                <span style={{ color: 'var(--error)' }} className="truncate" title={p.detail}>
                  {t('decision.provider_error')}{expert && p.detail ? ` — ${p.detail}` : ''}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {search.early_exit && (
        <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--success)' }}>
          <Zap size={12} />
          {t('decision.early_exit', {
            provider: formatProviderName(search.early_exit.provider),
            score: search.early_exit.score,
          })}
        </div>
      )}

      {/* Filter funnel */}
      {search.filters.length > 0 && (
        <div className="space-y-1 pt-1" style={{ borderTop: '1px dashed var(--border)' }}>
          <div className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--text-muted)' }}>
            {t('decision.filters_title')}
          </div>
          {search.filters.map((f, i) => (
            <FilterStageRow key={i} stage={f} expert={expert} t={t} />
          ))}
        </div>
      )}

      {/* Download attempts */}
      {search.download_attempts.length > 0 && (
        <div className="space-y-1 pt-1" style={{ borderTop: '1px dashed var(--border)' }}>
          <div className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--text-muted)' }}>
            {t('decision.downloads_title')}
          </div>
          {search.download_attempts.map((a, i) => (
            <div key={i} className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              {a.status === 'selected'
                ? <CheckCircle2 size={13} style={{ color: 'var(--success)' }} />
                : <XCircle size={13} style={{ color: 'var(--error)' }} />}
              <span className="capitalize font-medium">{formatProviderName(a.provider)}</span>
              <span style={{ color: 'var(--text-muted)' }}>
                {t(`decision.attempt_${a.status}`, { defaultValue: a.status })}
              </span>
              {expert && a.detail && (
                <span className="truncate" style={{ color: 'var(--text-muted)' }} title={a.detail}>{a.detail}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {expert && (search.unfinished_providers?.length ?? 0) > 0 && (
        <div className="text-xs" style={{ color: 'var(--warning)' }}>
          {t('decision.unfinished_providers', { providers: search.unfinished_providers!.join(', ') })}
        </div>
      )}
      {okProviders.length === 0 && search.providers.length === 0 && !search.cache_hit && (
        <div className="text-xs italic" style={{ color: 'var(--text-muted)' }}>
          {t('decision.no_providers')}
        </div>
      )}
    </SectionCard>
  )
}

export function DecisionLogModal({ mode, id, title, onClose }: DecisionLogModalProps) {
  const { t } = useTranslation('activity')
  const [expert, setExpert] = useState(false)

  const query = useQuery<DecisionLog>({
    queryKey: ['decision-log', mode, id],
    queryFn: () => (mode === 'history' ? getHistoryDecision(id) : getWantedDecision(id)),
  })

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const log = query.data
  const final = log?.final
  const isFound = final?.status === 'found' || final?.status === 'duplicate_skipped'

  return createPortal(
    <>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none" aria-modal="true" role="dialog">
        <div
          className="pointer-events-auto w-full max-w-3xl rounded-lg shadow-2xl flex flex-col max-h-[85vh] overflow-hidden"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: '1px solid var(--border)' }}>
            <div className="flex items-center gap-3 min-w-0">
              <ListTree className="w-5 h-5 shrink-0" style={{ color: 'var(--accent)' }} />
              <div className="min-w-0">
                <p className="text-xs uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                  {t('decision.title')}
                </p>
                <h2 className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{title}</h2>
              </div>
            </div>
            <div className="flex items-center gap-2 ml-3 shrink-0">
              <button
                onClick={() => setExpert(e => !e)}
                className="px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150"
                style={{
                  backgroundColor: expert ? 'var(--accent-bg)' : 'var(--bg-surface)',
                  color: expert ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${expert ? 'var(--accent-dim)' : 'var(--border)'}`,
                }}
              >
                {t('decision.expert_mode')}
              </button>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg transition-colors"
                style={{ color: 'var(--text-muted)' }}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-auto min-h-0 p-4 space-y-3">
            {query.isLoading && (
              <div className="flex flex-col items-center justify-center py-16 gap-3" style={{ color: 'var(--text-muted)' }}>
                <Loader2 className="w-8 h-8 animate-spin" style={{ color: 'var(--accent)' }} />
              </div>
            )}
            {query.isError && (
              <div className="flex flex-col items-center justify-center py-16 gap-3" style={{ color: 'var(--error)' }}>
                <AlertCircle className="w-8 h-8" />
                <p className="text-sm">{t('decision.not_available')}</p>
              </div>
            )}

            {log && (
              <>
                {/* Final outcome */}
                <SectionCard>
                  <div className="flex items-center gap-2 flex-wrap">
                    {isFound
                      ? <CheckCircle2 size={16} style={{ color: 'var(--success)' }} />
                      : <XCircle size={16} style={{ color: 'var(--error)' }} />}
                    <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {t(`decision.status_${final?.status ?? 'unknown'}`, { defaultValue: final?.status ?? t('decision.status_unknown') })}
                    </span>
                    {final?.provider && (
                      <span className="text-xs capitalize" style={{ color: 'var(--text-secondary)' }}>
                        {formatProviderName(final.provider)}
                      </span>
                    )}
                    {final?.language && (
                      <span className="text-xs uppercase" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                        {final.language}
                      </span>
                    )}
                    {final?.format && (
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
                        style={{
                          backgroundColor: final.format === 'ass' ? 'color-mix(in srgb, var(--success) 10%, transparent)' : 'var(--bg-primary)',
                          color: final.format === 'ass' ? 'var(--success)' : 'var(--text-secondary)',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        {final.format}
                      </span>
                    )}
                    {final?.score !== undefined && (
                      <ScoreBreakdown score={final.score} breakdown={final.score_breakdown ?? {}} />
                    )}
                  </div>
                  {(final?.reason || final?.error) && (
                    <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {final.reason ?? final.error}
                    </div>
                  )}
                  {expert && final?.filename && (
                    <div className="text-xs truncate" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }} title={final.filename}>
                      {final.filename}
                    </div>
                  )}
                  {log.upgrade && (
                    <div className="text-xs" style={{ color: log.upgrade.approved ? 'var(--success)' : 'var(--warning)' }}>
                      {t(log.upgrade.approved ? 'decision.upgrade_approved' : 'decision.upgrade_rejected', {
                        reason: log.upgrade.reason,
                        old: log.upgrade.old_score,
                        new: log.upgrade.new_score,
                      })}
                    </div>
                  )}
                </SectionCard>

                {/* Searches */}
                {log.searches.map((s, i) => (
                  <SearchSection key={i} search={s} expert={expert} t={t} />
                ))}

                {/* Skipped steps */}
                {log.steps.length > 0 && (
                  <SectionCard>
                    <div className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--text-muted)' }}>
                      {t('decision.skipped_steps')}
                    </div>
                    {log.steps.map((s, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                        <SkipForward size={12} style={{ color: 'var(--text-muted)' }} />
                        <span>{t(STEP_KEYS[s.step] ?? s.step)}</span>
                        <span style={{ color: 'var(--text-muted)' }}>— {s.reason}</span>
                      </div>
                    ))}
                  </SectionCard>
                )}

                {log.truncated && (
                  <div className="text-xs italic" style={{ color: 'var(--text-muted)' }}>
                    {t('decision.truncated')}
                  </div>
                )}
                {expert && (
                  <div className="text-[11px]" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {log.started_at} → {log.finished_at}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </>,
    document.body,
  )
}
