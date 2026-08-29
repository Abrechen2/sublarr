/**
 * ProvidersOverview — dedicated per-provider statistics page.
 *
 * Consolidates the provider data that was previously scattered across the
 * dashboard sidebar, settings tiles and the statistics table: success and
 * result rates, response times, last success/failure, circuit-breaker and
 * throttle state, and API budget usage.
 */

import { useTranslation } from 'react-i18next'
import { Server } from 'lucide-react'
import { useProviders, useBudgetState, useTestProvider } from '@/hooks/useApi'
import type { ProviderInfo, ProviderStatusReason } from '@/types/providers'
import type { ProviderBudget } from '@/api/health'
import { formatProviderName, formatRelativeTime, formatNumber } from '@/lib/utils'
import { toast } from '@/components/shared/Toast'

type StatusTier = 'ok' | 'warn' | 'error' | 'off'

function providerTier(p: ProviderInfo): { tier: StatusTier; label: string } {
  if (!p.enabled) return { tier: 'off', label: 'off' }
  if (p.stats?.auto_disabled || p.throttle_reason === 'auto_disabled') {
    return { tier: 'error', label: 'auto_disabled' }
  }
  if (p.circuit_breaker_state === 'open') return { tier: 'error', label: 'circuit_open' }
  if (p.circuit_breaker_state === 'half_open') return { tier: 'warn', label: 'recovering' }
  if (p.throttled_until && p.throttle_reason === 'rate_limited') {
    return { tier: 'warn', label: 'rate_limited' }
  }
  if (p.healthy === false) {
    // Every unhealthy provider used to read "Unreachable", which pointed at
    // the network whatever the actual cause was — a provider with no account
    // configured looked like an outage (#201). The backend now names the
    // reason; only fall back to the old label when it does not.
    const byReason: Partial<Record<ProviderStatusReason, { tier: StatusTier; label: string }>> = {
      auto_disabled: { tier: 'error', label: 'auto_disabled' },
      circuit_open: { tier: 'error', label: 'circuit_open' },
      consecutive_failures: { tier: 'error', label: 'consecutive_failures' },
      // Answers fine, delivers nothing — useless, but not broken.
      no_results: { tier: 'warn', label: 'no_results' },
      // A form field away from working, so not an error state.
      no_credentials: { tier: 'warn', label: 'no_credentials' },
      not_initialized: { tier: 'error', label: 'not_initialized' },
    }
    return (
      (p.status_reason && byReason[p.status_reason]) ?? { tier: 'error', label: 'unreachable' }
    )
  }
  if ((p.stats?.avg_response_time_ms ?? 0) > 5000) return { tier: 'warn', label: 'slow' }
  return { tier: 'ok', label: 'healthy' }
}

const TIER_COLOR: Record<StatusTier, string> = {
  ok: 'var(--success)',
  warn: 'var(--warning)',
  error: 'var(--error)',
  off: 'var(--text-muted)',
}

function Stat({ label, value, title }: { label: string; value: React.ReactNode; title?: string }) {
  return (
    <div style={{ minWidth: 0 }} title={title}>
      <div
        className="tabular-nums truncate"
        style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
      >
        {value}
      </div>
      <div style={{ fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
        {label}
      </div>
    </div>
  )
}

function BudgetBar({ budget }: { budget: ProviderBudget }) {
  const { t } = useTranslation('statistics')
  const used = budget.usage.day
  const limit = budget.limits.day
  if (!limit) return null
  const pct = Math.min(100, Math.round((used / limit) * 100))
  const color = pct >= 90 ? 'var(--error)' : pct >= 70 ? 'var(--warning)' : 'var(--accent)'
  return (
    <div style={{ marginTop: '8px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)', marginBottom: '3px' }}>
        <span>{t('providers_page.budget_day')}</span>
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)' }}>{used}/{limit}</span>
      </div>
      <div style={{ height: '4px', borderRadius: '2px', background: 'var(--bg-primary)', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color }} />
      </div>
    </div>
  )
}

function ProviderCard({ provider, budget }: { provider: ProviderInfo; budget?: ProviderBudget }) {
  const { t } = useTranslation('statistics')
  const testProvider = useTestProvider()
  const { tier, label } = providerTier(provider)
  const stats = provider.stats

  const downloadPct = Math.round((stats?.download_rate ?? 0) * 100)
  const resultPct = Math.round((stats?.result_rate ?? 0) * 100)

  const onTest = async () => {
    try {
      const res = await testProvider.mutateAsync({ name: provider.name })
      toast(`${formatProviderName(provider.name)}: ${res.message}`, res.healthy ? 'success' : 'error')
    } catch {
      toast(t('providers_page.test_failed'), 'error')
    }
  }

  return (
    <div
      data-testid={`provider-card-${provider.name}`}
      className="rounded-lg p-4"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', opacity: provider.enabled ? 1 : 0.55 }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span
          data-testid={`provider-status-${provider.name}`}
          data-tier={tier}
          style={{ width: 8, height: 8, borderRadius: '50%', background: TIER_COLOR[tier], flexShrink: 0 }}
        />
        <span className="font-semibold text-sm truncate" style={{ color: 'var(--text-primary)' }}>
          {formatProviderName(provider.name)}
        </span>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded uppercase font-medium ml-auto"
          style={{ color: TIER_COLOR[tier], backgroundColor: `color-mix(in srgb, ${TIER_COLOR[tier]} 12%, transparent)` }}
        >
          {t(`providers_page.status.${label}`)}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-x-3 gap-y-3">
        <Stat
          label={t('providers_page.download_rate')}
          value={`${downloadPct}%`}
          title={t('providers_page.download_rate_tooltip')}
        />
        <Stat
          label={t('providers_page.result_rate')}
          value={`${resultPct}%`}
          title={t('providers_page.result_rate_tooltip')}
        />
        <Stat label={t('providers_page.downloads')} value={formatNumber(provider.downloads ?? 0)} />
        <Stat
          label={t('providers_page.contribution')}
          value={
            provider.contribution_share === undefined
              ? '—'
              : `${Math.round(provider.contribution_share * 100)}%`
          }
          title={t('providers_page.contribution_tooltip')}
        />
        <Stat
          label={t('providers_page.avg_response')}
          value={stats?.avg_response_time_ms ? `${Math.round(stats.avg_response_time_ms)} ms` : '—'}
        />
        <Stat
          label={t('providers_page.last_success')}
          value={stats?.last_success_at ? formatRelativeTime(stats.last_success_at) : '—'}
        />
        <Stat
          label={t('providers_page.last_failure')}
          value={stats?.last_failure_at ? formatRelativeTime(stats.last_failure_at) : '—'}
        />
      </div>

      {provider.earns_its_place === false && (
        <div
          data-testid={`provider-no-contribution-${provider.name}`}
          style={{ marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}
        >
          {t('providers_page.earns_nothing')}
        </div>
      )}

      {(stats?.consecutive_failures ?? 0) > 0 && (
        <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--warning)' }}>
          {t('providers_page.consecutive_failures', { count: stats?.consecutive_failures ?? 0 })}
        </div>
      )}

      {budget && <BudgetBar budget={budget} />}

      <div className="flex justify-end mt-3">
        <button
          onClick={onTest}
          disabled={testProvider.isPending || !provider.enabled}
          className="px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150"
          style={{
            border: '1px solid var(--border)',
            backgroundColor: 'var(--bg-primary)',
            color: 'var(--text-secondary)',
            opacity: testProvider.isPending || !provider.enabled ? 0.6 : 1,
          }}
        >
          {testProvider.isPending ? t('providers_page.testing') : t('providers_page.test')}
        </button>
      </div>
    </div>
  )
}

export function ProvidersOverviewPage() {
  const { t } = useTranslation('statistics')
  const { data: providersData, isLoading } = useProviders()
  const { data: budgetData } = useBudgetState()

  const providers = [...(providersData?.providers ?? [])].sort((a, b) => {
    if (a.enabled !== b.enabled) return a.enabled ? -1 : 1
    // Contribution first — the question the page exists to answer is "which
    // of these earns its place?", and a high download rate over three
    // searches says less than a real share of the library (#200). Falls back
    // to the old ordering while a backend without the field is in play.
    const byShare = (b.contribution_share ?? -1) - (a.contribution_share ?? -1)
    if (byShare !== 0) return byShare
    return (b.stats?.download_rate ?? 0) - (a.stats?.download_rate ?? 0)
  })
  const budgets = new Map((budgetData?.providers ?? []).map((b) => [b.name, b]))

  const enabled = providers.filter((p) => p.enabled)
  const healthy = enabled.filter((p) => providerTier(p).tier === 'ok')
  const totalDownloads = providers.reduce((sum, p) => sum + (p.downloads ?? 0), 0)

  return (
    <div className="space-y-5">
      <div>
        <h1>{t('providers_page.title')}</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
          {t('providers_page.subtitle')}
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: t('providers_page.summary_enabled'), value: `${enabled.length}/${providers.length}` },
          { label: t('providers_page.summary_healthy'), value: `${healthy.length}/${enabled.length}` },
          { label: t('providers_page.summary_downloads'), value: formatNumber(totalDownloads) },
          {
            label: t('providers_page.summary_budget'),
            value: budgetData?.enabled ? t('providers_page.budget_on') : t('providers_page.budget_off'),
          },
        ].map((card) => (
          <div
            key={card.label}
            className="rounded-lg p-4 flex items-center gap-3"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="p-2 rounded-lg" style={{ backgroundColor: 'var(--accent-bg)' }}>
              <Server size={18} style={{ color: 'var(--accent)' }} />
            </div>
            <div>
              <div className="text-lg font-bold tabular-nums" style={{ fontFamily: 'var(--font-mono)' }}>
                {card.value}
              </div>
              <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{card.label}</div>
            </div>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton rounded-lg" style={{ height: '180px' }} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {providers.map((p) => (
            <ProviderCard key={p.name} provider={p} budget={budgets.get(p.name)} />
          ))}
        </div>
      )}
    </div>
  )
}

export default ProvidersOverviewPage
