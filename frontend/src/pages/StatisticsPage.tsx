/** Statistics page (V1.6 #9) — six analytics sections with a shared time range. */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BarChart3, Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import type { StatRange } from '@/api/client'
import {
  useStatSubtitles, useStatTranslation, useStatProviders, useStatSystem,
  useStatLibrary, useStatTrends,
} from '@/hooks/useStatistics'
import { StatTile, BreakdownBars, TrendsChart } from '@/components/statistics/primitives'

const RANGES: StatRange[] = ['24h', '7d', '30d', 'all']

function fmtNum(n: number): string {
  return n.toLocaleString()
}
function fmtBytes(n: number): string {
  if (!n) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)))
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`
}
function fmtDuration(s: number): string {
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`
}
function fmtCost(micro: number): string {
  return `$${(micro / 1_000_000).toFixed(2)}`
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-secondary">{title}</h2>
      {children}
    </section>
  )
}

export function StatisticsPage() {
  const { t } = useTranslation('statistics')
  const [range, setRange] = useState<StatRange>('30d')

  const subtitles = useStatSubtitles(range)
  const translation = useStatTranslation(range)
  const providers = useStatProviders()
  const system = useStatSystem()
  const library = useStatLibrary()
  const trends = useStatTrends(range)

  const loading = subtitles.isLoading || library.isLoading

  return (
    // Data surface — charts and tables read better with the full canvas, so
    // this joins the "wide" tier instead of keeping its own 1024px cap.
    <div className="w-full p-4 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <BarChart3 size={18} style={{ color: 'var(--accent)' }} />
          <div>
            <h1 className="text-lg font-semibold text-primary">{t('title')}</h1>
            <p className="text-[11px] text-muted">{t('subtitle')}</p>
          </div>
        </div>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className="px-2.5 py-1 rounded text-xs font-medium"
              style={{
                backgroundColor: r === range ? 'var(--accent-bg)' : 'var(--bg-surface)',
                border: `1px solid ${r === range ? 'var(--accent-dim)' : 'var(--border)'}`,
                color: r === range ? 'var(--accent)' : 'var(--text-secondary)',
              }}
            >
              {t(`range.${r}`)}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-40" style={{ color: 'var(--text-muted)' }}>
          <Loader2 size={20} className="animate-spin" />
        </div>
      ) : (
        <>
          {/* Overview */}
          <Section title={t('overview.title')}>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
              <StatTile label={t('overview.subtitle_files')} value={fmtNum(library.data?.subtitle_files ?? 0)} />
              <StatTile label={t('overview.downloads')} value={fmtNum(subtitles.data?.total ?? 0)} />
              <StatTile label={t('overview.translations')} value={fmtNum(translation.data?.total ?? 0)} />
              <StatTile label={t('overview.wanted')} value={fmtNum(library.data?.wanted_items ?? 0)} />
              <StatTile label={t('overview.mt_awaiting')} value={fmtNum(translation.data?.mt_awaiting_original ?? 0)} />
              <StatTile label={t('overview.avg_score')} value={subtitles.data?.avg_score ?? 0} />
            </div>
          </Section>

          {/* Trends */}
          <Section title={t('trends.title')}>
            <div className="rounded-lg p-3 bg-surface border border-border">
              <TrendsChart
                dates={trends.data?.dates ?? []}
                series={[
                  { key: 'downloads', label: t('trends.downloads'), values: trends.data?.downloads ?? [] },
                  { key: 'translations', label: t('trends.translations'), values: trends.data?.translations ?? [] },
                  { key: 'syncs', label: t('trends.syncs'), values: trends.data?.syncs ?? [] },
                ]}
                emptyLabel={t('no_data')}
              />
            </div>
          </Section>

          {/* Subtitles breakdowns */}
          <Section title={t('subtitles.title')}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
              <StatTile
                label={t('subtitles.sync_rate')}
                value={subtitles.data?.sync_rate != null ? `${Math.round(subtitles.data.sync_rate * 100)}%` : '—'}
                sub={t('subtitles.sync_runs', { count: subtitles.data?.sync_runs ?? 0 })}
              />
              <StatTile label={t('subtitles.sync_ok')} value={fmtNum(subtitles.data?.sync_ok ?? 0)} />
              <StatTile
                label={t('subtitles.sync_failed')}
                value={fmtNum((subtitles.data?.sync_runs ?? 0) - (subtitles.data?.sync_ok ?? 0))}
              />
              <StatTile label={t('overview.avg_score')} value={subtitles.data?.avg_score ?? 0} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {(['by_source', 'by_language', 'by_provider'] as const).map((k) => (
                <div key={k} className="rounded-lg p-3 bg-surface border border-border">
                  <div className="text-[11px] uppercase tracking-wide text-muted mb-1">{t(`subtitles.${k}`)}</div>
                  <BreakdownBars data={subtitles.data?.[k] ?? {}} emptyLabel={t('no_data')} />
                </div>
              ))}
            </div>
          </Section>

          {/* Translation */}
          <Section title={t('translation.title')}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
              <StatTile label={t('translation.chars')} value={fmtNum(translation.data?.total_chars ?? 0)} />
              <StatTile label={t('translation.cost')} value={fmtCost(translation.data?.total_cost_micro_usd ?? 0)} />
              <StatTile label={t('translation.pass_rate')} value={`${Math.round((translation.data?.pass_rate ?? 0) * 100)}%`} />
              <StatTile label={t('translation.avg_latency')} value={`${fmtNum(translation.data?.avg_latency_ms ?? 0)} ms`} />
            </div>
            <div className="rounded-lg p-3 bg-surface border border-border">
              <div className="text-[11px] uppercase tracking-wide text-muted mb-1">{t('translation.by_backend')}</div>
              <BreakdownBars data={translation.data?.by_backend ?? {}} emptyLabel={t('no_data')} />
            </div>
          </Section>

          {/* Providers table */}
          <Section title={t('providers.title')}>
            <div className="rounded-lg bg-surface border border-border overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted uppercase text-[10px]" style={{ borderBottom: '1px solid var(--border)' }}>
                    <th className="text-left px-3 py-2">{t('providers.provider')}</th>
                    <th className="text-right px-3 py-2">{t('providers.searches')}</th>
                    <th className="text-right px-3 py-2">{t('providers.hit_rate')}</th>
                    <th className="text-right px-3 py-2">{t('providers.downloads')}</th>
                    <th className="text-right px-3 py-2">{t('providers.avg_score')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(providers.data?.providers ?? []).filter((p) => p.searches > 0 || p.downloads > 0).map((p) => (
                    <tr key={p.provider} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td className="px-3 py-1.5 text-primary">
                        {p.provider}
                        {p.auto_disabled && <span className="ml-1 text-[10px]" style={{ color: 'var(--error)' }}>· {t('providers.disabled')}</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right text-secondary">{fmtNum(p.searches)}</td>
                      <td className="px-3 py-1.5 text-right text-secondary">{Math.round(p.hit_rate * 100)}%</td>
                      <td className="px-3 py-1.5 text-right text-secondary">{fmtNum(p.downloads)}</td>
                      <td className="px-3 py-1.5 text-right text-secondary">{p.avg_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          {/* System */}
          <Section title={t('system.title')}>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              <StatTile label={t('system.cpu')} value={`${Math.round(system.data?.cpu_percent ?? 0)}%`} />
              <StatTile label={t('system.memory')} value={`${Math.round(system.data?.memory_percent ?? 0)}%`} />
              <StatTile label={t('system.disk')} value={`${Math.round(system.data?.disk_percent ?? 0)}%`} />
              <StatTile label={t('system.uptime')} value={fmtDuration(system.data?.uptime_seconds ?? 0)} />
              <StatTile label={t('system.db_size')} value={fmtBytes(system.data?.db_size_bytes ?? 0)} />
            </div>
          </Section>
        </>
      )}
    </div>
  )
}
