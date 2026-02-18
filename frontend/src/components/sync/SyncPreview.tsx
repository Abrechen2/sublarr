/**
 * Before/after timing preview for sync operations.
 *
 * Shows a table of representative subtitle events with their
 * original and adjusted timestamps for visual comparison.
 */

import type { SyncPreviewEvent } from '@/lib/types'

interface SyncPreviewProps {
  events: SyncPreviewEvent[]
  operation: string
}

export function SyncPreview({ events, operation }: SyncPreviewProps) {
  if (events.length === 0) {
    return (
      <div className="text-center py-4 text-xs" style={{ color: 'var(--text-muted)' }}>
        No preview events available.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          Preview: {operation}
        </span>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {events.length} sample events
        </span>
      </div>

      <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-elevated)', borderBottom: '1px solid var(--border)' }}>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-2 py-1.5" style={{ color: 'var(--text-muted)', width: '40px' }}>#</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-2 py-1.5" style={{ color: 'var(--text-muted)' }}>Before Start</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-2 py-1.5" style={{ color: 'var(--text-muted)' }}>Before End</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-2 py-1.5" style={{ color: 'var(--accent)' }}>After Start</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-2 py-1.5" style={{ color: 'var(--accent)' }}>After End</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-2 py-1.5" style={{ color: 'var(--text-muted)' }}>Text</th>
            </tr>
          </thead>
          <tbody>
            {events.map((evt, i) => {
              const startChanged = evt.before_start !== evt.after_start
              const endChanged = evt.before_end !== evt.after_end
              return (
                <tr
                  key={evt.index}
                  style={{
                    borderBottom: i < events.length - 1 ? '1px solid var(--border)' : undefined,
                    backgroundColor: 'var(--bg-surface)',
                  }}
                >
                  <td
                    className="px-2 py-1.5 text-xs tabular-nums"
                    style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}
                  >
                    {evt.index}
                  </td>
                  <td
                    className="px-2 py-1.5 text-xs tabular-nums"
                    style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                  >
                    {evt.before_start}
                  </td>
                  <td
                    className="px-2 py-1.5 text-xs tabular-nums"
                    style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                  >
                    {evt.before_end}
                  </td>
                  <td
                    className="px-2 py-1.5 text-xs tabular-nums font-medium"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      color: startChanged ? 'var(--accent)' : 'var(--text-secondary)',
                      backgroundColor: startChanged ? 'var(--accent-bg)' : undefined,
                    }}
                  >
                    {evt.after_start}
                  </td>
                  <td
                    className="px-2 py-1.5 text-xs tabular-nums font-medium"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      color: endChanged ? 'var(--accent)' : 'var(--text-secondary)',
                      backgroundColor: endChanged ? 'var(--accent-bg)' : undefined,
                    }}
                  >
                    {evt.after_end}
                  </td>
                  <td
                    className="px-2 py-1.5 text-xs truncate max-w-[200px]"
                    style={{ color: 'var(--text-secondary)' }}
                    title={evt.text}
                  >
                    {evt.text.length > 40 ? evt.text.substring(0, 40) + '...' : evt.text}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
