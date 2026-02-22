/**
 * StatCardsWidget -- Status overview cards (Ollama, Wanted, Translated Today, Queue).
 *
 * Self-contained: fetches own data via useHealth, useStats, useWantedSummary.
 * Renders a 4-card grid with hover animations. StatCard sub-components have
 * their own card styling (grid-within-grid pattern).
 */
import { useTranslation } from 'react-i18next'
import { Server, Zap, CheckCircle2, Clock } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useHealth, useStats, useWantedSummary } from '@/hooks/useApi'

function StatCard({
  icon: Icon,
  label,
  value,
  color,
  delay,
}: {
  icon: LucideIcon
  label: string
  value: string | number
  color: string
  delay: number
}) {
  return (
    <div
      data-testid="stat-card"
      className="rounded-lg p-4 flex items-center gap-4 transition-all duration-200 hover:shadow-md cursor-default animate-in"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        animationDelay: `${delay}s`,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = color
        e.currentTarget.style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      <div
        className="p-2.5 rounded-lg"
        style={{ backgroundColor: `${color}12` }}
      >
        <Icon size={20} style={{ color }} />
      </div>
      <div>
        <div
          className="text-xl font-bold tabular-nums"
          style={{ fontFamily: 'var(--font-mono)' }}
        >
          {value}
        </div>
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          {label}
        </div>
      </div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div
      className="rounded-lg p-4 flex items-center gap-4"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
      }}
    >
      <div className="skeleton w-10 h-10 rounded-lg" />
      <div className="space-y-2 flex-1">
        <div className="skeleton h-5 w-16 rounded" />
        <div className="skeleton h-3 w-24 rounded" />
      </div>
    </div>
  )
}

export default function StatCardsWidget() {
  const { t } = useTranslation('dashboard')
  const { data: health, isLoading: healthLoading } = useHealth()
  const { data: stats, isLoading: statsLoading } = useStats()
  const { data: wantedSummary } = useWantedSummary()

  if (healthLoading || statsLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 p-2">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  return (
    <div data-testid="stats-cards" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 p-2">
      <StatCard
        icon={Server}
        label={t('stats.ollama')}
        value={
          health?.services?.ollama === 'OK'
            ? t('stats.online')
            : t('stats.offline')
        }
        color={
          health?.services?.ollama === 'OK'
            ? 'var(--success)'
            : 'var(--error)'
        }
        delay={0}
      />
      <StatCard
        icon={Zap}
        label={t('stats.wanted')}
        value={wantedSummary?.by_status?.wanted ?? 0}
        color={
          wantedSummary?.total ? 'var(--warning)' : 'var(--text-muted)'
        }
        delay={0.04}
      />
      <StatCard
        icon={CheckCircle2}
        label={t('stats.translated_today')}
        value={stats?.today_translated ?? 0}
        color="var(--accent)"
        delay={0.08}
      />
      <StatCard
        icon={Clock}
        label={t('stats.queue')}
        value={stats?.pending_jobs ?? 0}
        color="var(--warning)"
        delay={0.12}
      />
    </div>
  )
}
