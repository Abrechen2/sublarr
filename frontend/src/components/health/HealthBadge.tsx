import { ShieldCheck } from 'lucide-react'

interface HealthBadgeProps {
  score: number | null
  size?: 'sm' | 'md'
}

function getScoreColor(score: number): string {
  if (score >= 80) return 'var(--success)'
  if (score >= 50) return 'var(--warning)'
  return 'var(--error)'
}

export function HealthBadge({ score, size = 'sm' }: HealthBadgeProps) {
  if (score === null) {
    // Not yet checked
    if (size === 'sm') {
      return (
        <span
          className="inline-flex items-center justify-center rounded-full text-[10px] font-bold"
          style={{
            width: 16,
            height: 16,
            backgroundColor: 'var(--bg-surface)',
            color: 'var(--text-muted)',
            border: '1px solid var(--border)',
          }}
          title="Quality Score: Not checked"
        >
          ?
        </span>
      )
    }
    return (
      <span
        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
        style={{
          backgroundColor: 'var(--bg-surface)',
          color: 'var(--text-muted)',
          border: '1px solid var(--border)',
        }}
        title="Quality Score: Not checked"
      >
        <ShieldCheck size={12} />
        Score: ?
      </span>
    )
  }

  const color = getScoreColor(score)

  if (size === 'sm') {
    return (
      <span
        className="inline-flex items-center justify-center rounded-full text-[10px] font-bold tabular-nums"
        style={{
          width: 16,
          height: 16,
          backgroundColor: `${color}18`,
          color,
        }}
        title={`Quality Score: ${score}/100`}
      >
        {score}
      </span>
    )
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium tabular-nums"
      style={{
        backgroundColor: `${color}18`,
        color,
        border: `1px solid ${color}30`,
      }}
      title={`Quality Score: ${score}/100`}
    >
      <ShieldCheck size={12} />
      Score: {score}
    </span>
  )
}
