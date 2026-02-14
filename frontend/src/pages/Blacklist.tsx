import { useState } from 'react'
import { useBlacklist, useRemoveFromBlacklist, useClearBlacklist } from '@/hooks/useApi'
import { formatRelativeTime } from '@/lib/utils'
import {
  Ban, Trash2, ChevronLeft, ChevronRight, AlertTriangle,
} from 'lucide-react'

export function BlacklistPage() {
  const [page, setPage] = useState(1)
  const [showClearConfirm, setShowClearConfirm] = useState(false)

  const { data: blacklist, isLoading } = useBlacklist(page, 50)
  const removeEntry = useRemoveFromBlacklist()
  const clearAll = useClearBlacklist()

  const handleClearAll = () => {
    clearAll.mutate(undefined, {
      onSuccess: () => setShowClearConfirm(false),
    })
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1>Blacklist</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            {blacklist?.total ?? 0} blacklisted subtitles will be excluded from search results
          </p>
        </div>
        {(blacklist?.total ?? 0) > 0 && (
          <div>
            {showClearConfirm ? (
              <div className="flex items-center gap-2">
                <span className="text-xs" style={{ color: 'var(--warning)' }}>Clear all entries?</span>
                <button
                  onClick={handleClearAll}
                  disabled={clearAll.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white"
                  style={{ backgroundColor: 'var(--error)' }}
                >
                  <Trash2 size={12} />
                  Confirm
                </button>
                <button
                  onClick={() => setShowClearConfirm(false)}
                  className="px-3 py-1.5 rounded-md text-xs font-medium"
                  style={{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowClearConfirm(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium hover:opacity-90"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              >
                <Trash2 size={14} />
                Clear All
              </button>
            )}
          </div>
        )}
      </div>

      {/* Summary */}
      <div
        className="rounded-lg p-4 flex items-center gap-3"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="p-2 rounded-lg" style={{ backgroundColor: 'var(--error)12' }}>
          <Ban size={18} style={{ color: 'var(--error)' }} />
        </div>
        <div>
          <div className="text-lg font-bold tabular-nums" style={{ fontFamily: 'var(--font-mono)' }}>
            {blacklist?.total ?? 0}
          </div>
          <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>Blocked Subtitles</div>
        </div>
      </div>

      {/* Table */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[600px]">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>Provider</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>Subtitle ID</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>Lang</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>Title / Path</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>Reason</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>Added</th>
                <th className="text-right text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-4 py-3"><div className="skeleton h-4 w-24 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-32 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-8 rounded" /></td>
                    <td className="px-3 py-3 hidden sm:table-cell"><div className="skeleton h-4 w-40 rounded" /></td>
                    <td className="px-3 py-3 hidden md:table-cell"><div className="skeleton h-4 w-20 rounded" /></td>
                    <td className="px-3 py-3 hidden lg:table-cell"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-4 py-3"><div className="skeleton h-4 w-6 rounded ml-auto" /></td>
                  </tr>
                ))
              ) : blacklist?.data?.length ? (
                blacklist.data.map((entry) => (
                  <tr
                    key={entry.id}
                    className="transition-colors duration-100"
                    style={{ borderBottom: '1px solid var(--border)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td className="px-4 py-2.5">
                      <span
                        className="text-xs font-medium capitalize"
                        style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}
                      >
                        {entry.provider_name}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className="text-xs truncate max-w-[200px] block"
                        style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                        title={entry.subtitle_id}
                      >
                        {entry.subtitle_id}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className="text-xs uppercase"
                        style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                      >
                        {entry.language || '-'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 hidden sm:table-cell">
                      <span
                        className="text-xs truncate max-w-[250px] block"
                        style={{ color: 'var(--text-secondary)' }}
                        title={entry.file_path || entry.title}
                      >
                        {entry.title || entry.file_path || '-'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 hidden md:table-cell">
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        {entry.reason || '-'}
                      </span>
                    </td>
                    <td
                      className="px-3 py-2.5 text-xs tabular-nums hidden lg:table-cell"
                      style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                    >
                      {entry.added_at ? formatRelativeTime(entry.added_at) : ''}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        onClick={() => removeEntry.mutate(entry.id)}
                        disabled={removeEntry.isPending}
                        className="p-1 rounded transition-colors duration-150"
                        title="Remove from blacklist"
                        style={{ color: 'var(--text-muted)' }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
                        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
                    <div className="flex flex-col items-center gap-2">
                      <AlertTriangle size={20} style={{ color: 'var(--text-muted)' }} />
                      No blacklisted subtitles. Use the ban button on search results or history to block unwanted subtitles.
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {blacklist && blacklist.total_pages > 1 && (
          <div
            className="flex items-center justify-between px-4 py-2.5"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Page {blacklist.page} of {blacklist.total_pages} ({blacklist.total} total)
            </span>
            <div className="flex gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded-md transition-all duration-150"
                style={{
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-secondary)',
                }}
              >
                <ChevronLeft size={14} />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(blacklist.total_pages, p + 1))}
                disabled={page >= blacklist.total_pages}
                className="p-1.5 rounded-md transition-all duration-150"
                style={{
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-secondary)',
                }}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
