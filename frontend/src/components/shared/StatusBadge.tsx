import { cn } from '@/lib/utils'

interface StatusBadgeProps {
  status: string
  className?: string
}

const statusStyles: Record<string, { bg: string; text: string; dot: string }> = {
  healthy:          { bg: 'var(--success-bg)', text: 'var(--success)', dot: 'var(--success)' },
  completed:        { bg: 'var(--success-bg)', text: 'var(--success)', dot: 'var(--success)' },
  running:          { bg: 'var(--accent-bg)',  text: 'var(--accent)',  dot: 'var(--accent)' },
  queued:           { bg: 'var(--warning-bg)', text: 'var(--warning)', dot: 'var(--warning)' },
  failed:           { bg: 'var(--error-bg)',   text: 'var(--error)',   dot: 'var(--error)' },
  unhealthy:        { bg: 'var(--error-bg)',   text: 'var(--error)',   dot: 'var(--error)' },
  wanted:           { bg: 'var(--warning-bg)', text: 'var(--warning)', dot: 'var(--warning)' },
  searching:        { bg: 'var(--accent-bg)',  text: 'var(--accent)',  dot: 'var(--accent)' },
  found:            { bg: 'var(--success-bg)', text: 'var(--success)', dot: 'var(--success)' },
  ignored:          { bg: 'rgba(124,130,147,0.08)', text: 'var(--text-muted)', dot: 'var(--text-muted)' },
  'not configured': { bg: 'rgba(124,130,147,0.08)', text: 'var(--text-secondary)', dot: 'var(--text-muted)' },
  skipped:          { bg: 'rgba(124,130,147,0.08)', text: 'var(--text-secondary)', dot: 'var(--text-muted)' },
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const style = statusStyles[status.toLowerCase()] || statusStyles['not configured']
  const isRunning = status.toLowerCase() === 'running'

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium',
        className
      )}
      style={{ backgroundColor: style.bg, color: style.text }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{
          backgroundColor: style.dot,
          color: style.dot,
          animation: isRunning ? 'dotGlow 2s ease-in-out infinite' : undefined,
        }}
      />
      {status}
    </span>
  )
}

/**
 * Compact badge for subtitle type indication.
 * Only renders for "forced" type -- "full" is the default and shows nothing.
 */
export function SubtitleTypeBadge({ subtitleType, className }: { subtitleType: string; className?: string }) {
  if (subtitleType !== 'forced') return null

  return (
    <span
      className={cn(
        'inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium',
        className
      )}
      style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
    >
      Forced
    </span>
  )
}
