import type { SchedulerStatus } from '@/lib/types'
import { useTranslation } from 'react-i18next'

// Map scheduler status to Sublarr semantic colour tokens.
// Sublarr uses `--success`, `--error`, `--warning` (no `danger`) plus matching
// *-bg variants already tinted at ~10% alpha — see frontend/src/index.css.
const STATUS_COLOR: Record<SchedulerStatus, string> = {
  ok: 'bg-success-bg text-success',
  error: 'bg-error-bg text-error',
  timeout: 'bg-warning-bg text-warning',
  missed: 'bg-warning-bg text-warning',
  skipped_overlap: 'bg-elevated text-muted',
}

export function StatusBadge({ status }: { status: SchedulerStatus }) {
  const { t } = useTranslation('settings')
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLOR[status]}`}
      aria-label={`Status: ${status}`}
    >
      {t(`scheduler.status.${status}`, { defaultValue: status })}
    </span>
  )
}
