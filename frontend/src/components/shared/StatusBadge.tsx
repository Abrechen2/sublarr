import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  AlertCircle,
  Search,
  MinusCircle,
} from 'lucide-react'

interface StatusBadgeProps {
  status: string
  className?: string
}

const statusStyles: Record<string, { bg: string; text: string }> = {
  healthy:          { bg: 'var(--success-bg)', text: 'var(--success)' },
  completed:        { bg: 'var(--success-bg)', text: 'var(--success)' },
  running:          { bg: 'var(--accent-bg)',  text: 'var(--accent)' },
  queued:           { bg: 'var(--warning-bg)', text: 'var(--warning)' },
  failed:           { bg: 'var(--error-bg)',   text: 'var(--error)' },
  unhealthy:        { bg: 'var(--error-bg)',   text: 'var(--error)' },
  wanted:           { bg: 'var(--warning-bg)', text: 'var(--warning)' },
  searching:        { bg: 'var(--accent-bg)',  text: 'var(--accent)' },
  found:            { bg: 'var(--success-bg)', text: 'var(--success)' },
  extracted:        { bg: 'rgba(20,184,166,0.12)',  text: 'rgb(20,184,166)' },
  ignored:          { bg: 'rgba(124,130,147,0.08)', text: 'var(--text-muted)' },
  'not configured': { bg: 'rgba(124,130,147,0.08)', text: 'var(--text-secondary)' },
  skipped:          { bg: 'rgba(124,130,147,0.08)', text: 'var(--text-secondary)' },
}

const statusIcons: Record<string, typeof CheckCircle2> = {
  healthy:          CheckCircle2,
  completed:        CheckCircle2,
  found:            CheckCircle2,
  extracted:        CheckCircle2,
  running:          Loader2,
  queued:           Clock,
  failed:           XCircle,
  unhealthy:        XCircle,
  wanted:           AlertCircle,
  searching:        Search,
  ignored:          MinusCircle,
  skipped:          MinusCircle,
  'not configured': MinusCircle,
}

// Map API status strings to common:status translation keys
const statusTranslationKeys: Record<string, string> = {
  healthy: 'status.healthy',
  completed: 'status.completed',
  running: 'status.running',
  queued: 'status.queued',
  failed: 'status.failed',
  unhealthy: 'status.unhealthy',
  wanted: 'status.wanted',
  searching: 'status.searching',
  found: 'status.found',
  extracted: 'status.extracted',
  ignored: 'status.ignored',
  'not configured': 'status.not_configured',
  skipped: 'status.skipped',
  online: 'status.online',
  offline: 'status.offline',
  enabled: 'status.enabled',
  disabled: 'status.disabled',
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const { t } = useTranslation('common')
  const key = status.toLowerCase()
  const style = statusStyles[key] || statusStyles['not configured']
  const Icon = statusIcons[key] || MinusCircle
  const isRunning = key === 'running'
  const translationKey = statusTranslationKeys[key]
  const label = translationKey ? t(translationKey) : status

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium',
        className
      )}
      style={{ backgroundColor: style.bg, color: style.text }}
    >
      <Icon
        size={11}
        strokeWidth={2.5}
        className={isRunning ? 'animate-spin' : undefined}
        aria-hidden="true"
      />
      {label}
    </span>
  )
}

/**
 * Compact badge for subtitle type indication.
 * Only renders for "forced" type -- "full" is the default and shows nothing.
 */
export function SubtitleTypeBadge({ subtitleType, className }: { subtitleType: string; className?: string }) {
  const { t } = useTranslation('common')
  if (subtitleType !== 'forced') return null

  return (
    <span
      className={cn(
        'inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium',
        className
      )}
      style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
    >
      {t('status.forced', 'Forced')}
    </span>
  )
}
