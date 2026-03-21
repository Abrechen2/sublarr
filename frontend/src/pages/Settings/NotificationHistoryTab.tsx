import { useState } from 'react'
import { Loader2, RotateCcw } from 'lucide-react'
import { useNotificationHistory, useResendNotification } from '@/hooks/useSystemApi'
import { toast } from '@/components/shared/Toast'

// ─── NotificationHistoryTab ───────────────────────────────────────────────────

export function NotificationHistoryTab() {
  const [page, setPage] = useState(1)
  const [eventFilter, setEventFilter] = useState<string | undefined>(undefined)
  const { data, isLoading } = useNotificationHistory(page, eventFilter)
  const resendMut = useResendNotification()

  const entries = data?.entries ?? []
  const totalPages = data?.total_pages ?? 1

  const handleResend = (id: number) => {
    resendMut.mutate(id, {
      onSuccess: () => toast('Notification resent'),
      onError: () => toast('Resend failed', 'error'),
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-20">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div
        data-testid="history-empty"
        className="rounded-lg p-6 text-center text-sm"
        style={{ color: 'var(--text-muted)', backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        No notification history yet.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Event filter */}
      <div className="flex items-center gap-2">
        <label className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Filter by event:
        </label>
        <input
          type="text"
          placeholder="e.g. subtitle_found"
          value={eventFilter ?? ''}
          onChange={(e) => { setEventFilter(e.target.value || undefined); setPage(1) }}
          className="px-2 py-1 rounded text-xs focus:outline-none"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            minWidth: '180px',
          }}
          data-testid="history-event-filter"
        />
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface-hover)', color: 'var(--text-muted)' }}>
              <th className="px-3 py-2 text-left font-medium">Timestamp</th>
              <th className="px-3 py-2 text-left font-medium">Event</th>
              <th className="px-3 py-2 text-left font-medium">Channel</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-left font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry: { id: number; timestamp: string; event_type: string; channel: string; status: string }) => (
              <tr
                key={entry.id}
                style={{ borderTop: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <td className="px-3 py-2 whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                  {new Date(entry.timestamp).toLocaleString()}
                </td>
                <td className="px-3 py-2">{entry.event_type}</td>
                <td className="px-3 py-2">{entry.channel}</td>
                <td className="px-3 py-2">
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                    style={{
                      backgroundColor: entry.status === 'sent'
                        ? 'color-mix(in srgb, var(--success) 12%, transparent)'
                        : 'color-mix(in srgb, var(--error) 12%, transparent)',
                      color: entry.status === 'sent' ? 'var(--success)' : 'var(--error)',
                    }}
                  >
                    {entry.status}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <button
                    className="flex items-center gap-1 text-xs px-2 py-1 rounded"
                    style={{
                      color: 'var(--accent)',
                      border: '1px solid var(--accent)',
                      backgroundColor: 'transparent',
                      cursor: 'pointer',
                    }}
                    onClick={() => handleResend(entry.id)}
                    disabled={resendMut.isPending}
                  >
                    <RotateCcw size={10} />
                    Resend
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center gap-2 justify-end">
          <button
            className="text-xs px-2 py-1 rounded"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              opacity: page <= 1 ? 0.4 : 1,
            }}
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            data-testid="history-prev-btn"
          >
            Prev
          </button>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {page} / {totalPages}
          </span>
          <button
            className="text-xs px-2 py-1 rounded"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              opacity: page >= totalPages ? 0.4 : 1,
            }}
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            data-testid="history-next-btn"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
