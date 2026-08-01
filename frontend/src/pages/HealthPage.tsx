/**
 * Health page — "where does it hurt" overview of the library.
 *
 * Three bounded views from GET /api/v1/health/library: series with missing
 * subtitles, wanted items stuck in a failure state (unmatched episodes), and
 * per-provider health (circuit breaker ⋈ provider stats).
 */
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { HeartPulse, Loader2, AlertTriangle, CheckCircle2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { StatTile } from '@/components/statistics/primitives'
import { getLibraryHealth, type HealthProblemRow, type HealthProviderRow } from '@/api/system/healthLibrary'
import { formatRelativeTime, formatProviderName } from '@/lib/utils'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-secondary">{title}</h2>
      {children}
    </section>
  )
}

function Th({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <th
      scope="col"
      className={`text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2 ${className}`}
      style={{ color: 'var(--text-muted)' }}
    >
      {children}
    </th>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-6 text-sm" style={{ color: 'var(--text-secondary)' }}>
      <CheckCircle2 size={15} style={{ color: 'var(--success)' }} />
      {label}
    </div>
  )
}

function FailureKindBadge({ kind, status, t }: { kind: string | null; status: string; t: (key: string) => string }) {
  const key = kind ?? status
  const label = t(`failure.${key}`) === `failure.${key}` ? key : t(`failure.${key}`)
  const isHard = kind === 'unsourceable' || status === 'failed'
  return (
    <span
      className="text-[10px] px-1.5 py-0.5 rounded font-bold uppercase"
      style={{
        backgroundColor: isHard ? 'color-mix(in srgb, var(--error) 12%, transparent)' : 'color-mix(in srgb, var(--warning) 12%, transparent)',
        color: isHard ? 'var(--error)' : 'var(--warning)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {label}
    </span>
  )
}

function ProblemRow({ item, t }: { item: HealthProblemRow; t: (key: string) => string }) {
  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td className="px-3 py-2">
        <div className="text-sm font-medium truncate max-w-xs" style={{ color: 'var(--text-primary)' }}>{item.title}</div>
        {item.season_episode && (
          <div className="text-[11px]" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{item.season_episode}</div>
        )}
      </td>
      <td className="px-3 py-2 text-xs uppercase" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
        {item.target_language}
      </td>
      <td className="px-3 py-2">
        <FailureKindBadge kind={item.failure_kind} status={item.status} t={t} />
      </td>
      <td className="px-3 py-2 text-xs truncate max-w-[240px] hidden md:table-cell" title={item.error} style={{ color: 'var(--text-secondary)' }}>
        {item.error || '—'}
      </td>
      <td className="px-3 py-2 text-xs tabular-nums hidden sm:table-cell" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
        {item.search_count}
      </td>
      <td className="px-3 py-2 text-xs tabular-nums hidden lg:table-cell" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
        {item.updated_at ? formatRelativeTime(item.updated_at) : ''}
      </td>
    </tr>
  )
}

function ProviderRow({ p, t }: { p: HealthProviderRow; t: (key: string) => string }) {
  const stateColor = p.breaker_state === 'closed' && !p.auto_disabled ? 'var(--success)' : p.breaker_state === 'half_open' ? 'var(--warning)' : 'var(--error)'
  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          {p.degraded && <AlertTriangle size={13} style={{ color: 'var(--warning)' }} />}
          <span className="text-sm font-medium capitalize" style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
            {formatProviderName(p.provider)}
          </span>
        </div>
      </td>
      <td className="px-3 py-2">
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-bold uppercase"
          style={{ backgroundColor: `color-mix(in srgb, ${stateColor} 12%, transparent)`, color: stateColor, fontFamily: 'var(--font-mono)' }}
        >
          {p.auto_disabled ? t('providers.auto_disabled') : t(`providers.state_${p.breaker_state}`)}
        </span>
      </td>
      <td className="px-3 py-2 text-xs tabular-nums hidden sm:table-cell" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
        {p.searches}
      </td>
      <td className="px-3 py-2 text-xs tabular-nums" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
        {p.hit_rate != null ? `${Math.round(p.hit_rate * 100)}%` : '—'}
      </td>
      <td className="px-3 py-2 text-xs tabular-nums hidden md:table-cell" style={{ color: p.failed_downloads > 0 ? 'var(--warning)' : 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
        {p.failed_downloads}
      </td>
      <td className="px-3 py-2 text-xs tabular-nums hidden lg:table-cell" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
        {p.breaker_failures}
      </td>
    </tr>
  )
}

export function HealthPage() {
  const { t } = useTranslation('health')

  const { data, isLoading } = useQuery({
    queryKey: ['library-health'],
    queryFn: getLibraryHealth,
    refetchInterval: 60_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-60" style={{ color: 'var(--text-muted)' }}>
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  const totals = data?.totals
  const degradedProviders = (data?.providers ?? []).filter((p) => p.degraded)
  const healthyProviders = (data?.providers ?? []).filter((p) => !p.degraded)

  return (
    // Data surface — tables of problem items benefit from the full canvas, so
    // this joins the "wide" tier rather than keeping its own 1024px cap.
    <div className="w-full p-4 space-y-6">
      <PageHeader title={t('title')} subtitle={t('subtitle')} className="mb-0" />

      {/* Totals */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <StatTile label={t('totals.wanted')} value={totals?.wanted ?? 0} />
        <StatTile label={t('totals.problems')} value={totals?.problems ?? 0} />
        <StatTile label={t('totals.unmatched')} value={totals?.unmatched ?? 0} />
        <StatTile label={t('totals.series_affected')} value={totals?.series_affected ?? 0} />
        <StatTile label={t('totals.providers_degraded')} value={totals?.providers_degraded ?? 0} />
      </div>

      {/* Series with missing subtitles */}
      <Section title={t('series.title')}>
        <div className="rounded-lg overflow-hidden" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
          {data?.series.length ? (
            <div className="overflow-x-auto max-h-[320px] overflow-y-auto">
              <table className="w-full min-w-[420px]">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <Th>{t('series.col_title')}</Th>
                    <Th>{t('series.col_type')}</Th>
                    <Th>{t('series.col_missing')}</Th>
                    <Th>{t('series.col_problems')}</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.series.map((s) => (
                    <tr key={`${s.item_type}:${s.title}`} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td className="px-3 py-2 text-sm font-medium truncate max-w-xs" style={{ color: 'var(--text-primary)' }}>{s.title}</td>
                      <td className="px-3 py-2 text-xs" style={{ color: 'var(--text-muted)' }}>{t(`series.type_${s.item_type}`)}</td>
                      <td className="px-3 py-2 text-xs tabular-nums" style={{ color: 'var(--warning)', fontFamily: 'var(--font-mono)' }}>{s.missing}</td>
                      <td className="px-3 py-2 text-xs tabular-nums" style={{ color: s.problems > 0 ? 'var(--error)' : 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{s.problems}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState label={t('series.empty')} />
          )}
        </div>
        <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {t('series.hint')} <Link to="/wanted" className="underline" style={{ color: 'var(--accent)' }}>{t('series.wanted_link')}</Link>
        </p>
      </Section>

      {/* Problem items (failed / unmatched) */}
      <Section title={t('problems.title')}>
        <div className="rounded-lg overflow-hidden" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
          {data?.problems.length ? (
            <div className="overflow-x-auto max-h-[380px] overflow-y-auto">
              <table className="w-full min-w-[520px]">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <Th>{t('problems.col_item')}</Th>
                    <Th>{t('problems.col_lang')}</Th>
                    <Th>{t('problems.col_kind')}</Th>
                    <Th className="hidden md:table-cell">{t('problems.col_error')}</Th>
                    <Th className="hidden sm:table-cell">{t('problems.col_attempts')}</Th>
                    <Th className="hidden lg:table-cell">{t('problems.col_updated')}</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.problems.map((item) => (
                    <ProblemRow key={item.id} item={item} t={t} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState label={t('problems.empty')} />
          )}
        </div>
      </Section>

      {/* Provider health */}
      <Section title={t('providers.title')}>
        <div className="rounded-lg overflow-hidden" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
          {data?.providers.length ? (
            <div className="overflow-x-auto max-h-[380px] overflow-y-auto">
              <table className="w-full min-w-[520px]">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <Th>{t('providers.col_provider')}</Th>
                    <Th>{t('providers.col_state')}</Th>
                    <Th className="hidden sm:table-cell">{t('providers.col_searches')}</Th>
                    <Th>{t('providers.col_hit_rate')}</Th>
                    <Th className="hidden md:table-cell">{t('providers.col_failed_downloads')}</Th>
                    <Th className="hidden lg:table-cell">{t('providers.col_breaker_failures')}</Th>
                  </tr>
                </thead>
                <tbody>
                  {[...degradedProviders, ...healthyProviders].map((p) => (
                    <ProviderRow key={p.provider} p={p} t={t} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState label={t('providers.empty')} />
          )}
        </div>
      </Section>

      <div className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>
        <HeartPulse size={12} />
        {t('refresh_note')}
      </div>
    </div>
  )
}
