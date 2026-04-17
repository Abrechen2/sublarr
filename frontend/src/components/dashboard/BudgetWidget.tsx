import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { useBudgetState } from '@/hooks/useSystemApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { BudgetResponse, BudgetWindow, ProviderBudget } from '@/api/health'

// ─── Live-update helper (exported for unit tests) ───────────────────────────

export interface BudgetUpdatePayload {
  provider: string
  usage: BudgetWindow
}

/**
 * Pure cache-patch helper. Returns a new BudgetResponse with the usage of the
 * matching provider replaced. Unknown providers and undefined caches are
 * no-ops, keeping the caller (queryClient.setQueryData) safe.
 */
export function applyBudgetUpdate(
  prev: BudgetResponse | undefined,
  payload: BudgetUpdatePayload,
): BudgetResponse | undefined {
  if (!prev) return prev
  return {
    ...prev,
    providers: prev.providers.map((p) =>
      p.name === payload.provider ? { ...p, usage: payload.usage } : p,
    ),
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0min'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h === 0) return `${m}min`
  return `${h}h ${m}min`
}

type BudgetColour = 'green' | 'yellow' | 'red'

function pickColour(pct: number): BudgetColour {
  if (pct >= 90) return 'red'
  if (pct >= 70) return 'yellow'
  return 'green'
}

const COLOUR_VAR: Record<BudgetColour, string> = {
  green: 'var(--success)',
  yellow: 'var(--warning)',
  red: 'var(--error)',
}

// ─── Row component ──────────────────────────────────────────────────────────

interface BudgetRowProps {
  readonly provider: ProviderBudget
}

function BudgetRow({ provider }: BudgetRowProps) {
  const { t } = useTranslation('dashboard')
  const [expanded, setExpanded] = useState(false)
  const used = provider.usage.day
  const limit = provider.limits.day || 1
  const pct = Math.min(100, Math.max(0, (used / limit) * 100))
  const colour = pickColour(pct)
  const barColor = COLOUR_VAR[colour]
  const learningPct =
    provider.learning && provider.learning.adjustment_factor < 1.0
      ? Math.round((1 - provider.learning.adjustment_factor) * 100)
      : null
  const hasKeys = Array.isArray(provider.keys) && provider.keys.length > 0

  return (
    <li
      data-testid={`budget-row-${provider.name}`}
      data-colour={colour}
      onClick={hasKeys ? () => setExpanded((s) => !s) : undefined}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0px',
        padding: '4px 0',
        listStyle: 'none',
        cursor: hasKeys ? 'pointer' : 'default',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span
          style={{
            flex: '0 0 110px',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={provider.name}
        >
          {provider.name}
        </span>
        <div
          role="progressbar"
          aria-label={provider.name}
          aria-valuenow={used}
          aria-valuemin={0}
          aria-valuemax={limit}
          style={{
            flex: 1,
            height: '8px',
            background: 'var(--bg-secondary)',
            borderRadius: '4px',
            overflow: 'hidden',
          }}
        >
          <div
            data-testid={`budget-bar-${provider.name}`}
            style={{
              width: `${pct}%`,
              height: '100%',
              background: barColor,
              transition: 'width 200ms ease-out',
            }}
          />
        </div>
        <span
          data-testid={`budget-usage-${provider.name}`}
          style={{
            flex: '0 0 auto',
            fontSize: '11px',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
            whiteSpace: 'nowrap',
          }}
        >
          {used.toLocaleString()} / {provider.limits.day.toLocaleString()}
        </span>
        {learningPct !== null && (
          <span
            data-testid={`budget-learning-${provider.name}`}
            title={t('budget.learning_active', { factor: learningPct })}
            style={{
              flex: '0 0 auto',
              fontSize: '10px',
              color: 'var(--warning)',
              background: 'var(--warning-bg)',
              padding: '2px 6px',
              borderRadius: '4px',
              marginLeft: '4px',
            }}
          >
            -{learningPct}%
          </span>
        )}
      </div>
      {expanded && hasKeys && provider.keys && (
        <ul
          style={{ listStyle: 'none', padding: '8px 0 0 16px', margin: 0 }}
          aria-label={t('budget.per_key_breakdown')}
        >
          {provider.keys.map((k) => (
            <li
              key={k.id}
              data-testid={`key-detail-${k.id}`}
              style={{
                fontSize: '11px',
                color: 'var(--text-secondary)',
                display: 'flex',
                justifyContent: 'space-between',
                padding: '2px 0',
              }}
            >
              <span>
                {k.label} ({k.tier})
              </span>
              <span>
                {k.used.day}/{k.limit.day}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

// ─── Widget container ──────────────────────────────────────────────────────

function CardShell({
  testId,
  title,
  children,
}: {
  readonly testId: string
  readonly title?: string
  readonly children: React.ReactNode
}) {
  return (
    <div
      data-testid={testId}
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
      }}
    >
      {title && (
        <div
          style={{
            fontSize: '11px',
            fontWeight: 700,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.4px',
          }}
        >
          {title}
        </div>
      )}
      {children}
    </div>
  )
}

export function BudgetWidget() {
  const { t } = useTranslation('dashboard')
  const { data, isLoading, error } = useBudgetState()
  const queryClient = useQueryClient()

  // Subscribe to the backend `provider_budget_updated` SocketIO event so the
  // bars refresh in <1s after a provider call, instead of waiting for the
  // 5s poll cycle. The cache is patched immutably to trigger a re-render.
  useWebSocket({
    onProviderBudgetUpdated: (rawData) => {
      const payload = rawData as BudgetUpdatePayload
      if (!payload || typeof payload.provider !== 'string' || !payload.usage) return
      queryClient.setQueryData<BudgetResponse | undefined>(
        ['system', 'budget'],
        (prev) => applyBudgetUpdate(prev, payload),
      )
    },
  })

  if (isLoading) {
    return (
      <CardShell testId="budget-widget-loading">
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          {t('budget.loading')}
        </span>
      </CardShell>
    )
  }

  // Fail quietly — widget is non-critical
  if (error || !data) return null

  if (!data.enabled) {
    return (
      <CardShell testId="budget-widget-disabled">
        <span
          style={{
            fontSize: '12px',
            color: 'var(--text-muted)',
            fontStyle: 'italic',
          }}
        >
          {t('budget.disabled')}
        </span>
      </CardShell>
    )
  }

  const providers = [...data.providers].sort((a, b) => a.name.localeCompare(b.name))
  if (providers.length === 0) return null

  const nextReset = Math.min(...providers.map((p) => p.reset_seconds.day))

  return (
    <CardShell testId="budget-widget" title={t('budget.title')}>
      <ul
        style={{
          margin: 0,
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: '2px',
        }}
      >
        {providers.map((p) => (
          <BudgetRow key={p.name} provider={p} />
        ))}
      </ul>
      <div
        data-testid="budget-reset"
        style={{
          fontSize: '11px',
          color: 'var(--text-muted)',
          paddingTop: '4px',
          borderTop: '1px solid var(--border)',
        }}
      >
        {t('budget.reset_in', { time: formatDuration(nextReset) })}
      </div>
    </CardShell>
  )
}

export default BudgetWidget
