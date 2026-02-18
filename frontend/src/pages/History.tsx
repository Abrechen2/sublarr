import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useHistory, useHistoryStats, useAddToBlacklist } from '@/hooks/useApi'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import {
  Clock, Download, ChevronLeft, ChevronRight, Ban, Eye, GitCompare,
} from 'lucide-react'
import SubtitleEditorModal from '@/components/editor/SubtitleEditorModal'

const PROVIDER_FILTERS = ['all', 'animetosho', 'jimaku', 'opensubtitles', 'subdl'] as const

function SummaryCard({ icon: Icon, label, value, color }: {
  icon: typeof Clock
  label: string
  value: number | string
  color: string
}) {
  return (
    <div
      className="rounded-lg p-4 flex items-center gap-3"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="p-2 rounded-lg" style={{ backgroundColor: `${color}12` }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <div className="text-lg font-bold tabular-nums" style={{ fontFamily: 'var(--font-mono)' }}>
          {value}
        </div>
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      </div>
    </div>
  )
}

export function HistoryPage() {
  const { t } = useTranslation('activity')
  const [page, setPage] = useState(1)
  const [providerFilter, setProviderFilter] = useState<string | undefined>()
  const [editorFilePath, setEditorFilePath] = useState<string | null>(null)
  const [editorMode, setEditorMode] = useState<'preview' | 'edit' | 'diff'>('preview')

  const { data: history, isLoading } = useHistory(page, 50, providerFilter)
  const { data: stats } = useHistoryStats()
  const addBlacklist = useAddToBlacklist()

  const topProvider = stats?.by_provider
    ? Object.entries(stats.by_provider).sort((a, b) => b[1] - a[1])[0]?.[0] ?? '-'
    : '-'

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1>{t('history.title')}</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
          {t('history.subtitle')}
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryCard icon={Download} label={t('history.total_downloads')} value={stats?.total_downloads ?? 0} color="var(--accent)" />
        <SummaryCard icon={Clock} label={t('history.last_24h')} value={stats?.last_24h ?? 0} color="var(--success)" />
        <SummaryCard icon={Clock} label={t('history.last_7d')} value={stats?.last_7d ?? 0} color="var(--warning)" />
        <SummaryCard icon={Download} label={t('history.top_provider')} value={topProvider} color="var(--text-secondary)" />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-1.5">
        {PROVIDER_FILTERS.map((p) => {
          const isActive = (p === 'all' && !providerFilter) || providerFilter === p
          return (
            <button
              key={p}
              onClick={() => { setProviderFilter(p === 'all' ? undefined : p); setPage(1) }}
              className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
              style={{
                backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
              }}
            >
              {p === 'all' ? t('history.all_providers') : p}
            </button>
          )
        })}
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
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.file')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.provider')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.lang')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.format')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{t('history.table.score')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>{t('history.table.date')}</th>
                <th className="text-right text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-4 py-3"><div className="skeleton h-4 w-48 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-20 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-8 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-10 rounded" /></td>
                    <td className="px-3 py-3 hidden sm:table-cell"><div className="skeleton h-4 w-8 rounded" /></td>
                    <td className="px-3 py-3 hidden md:table-cell"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-4 py-3"><div className="skeleton h-4 w-6 rounded ml-auto" /></td>
                  </tr>
                ))
              ) : history?.data?.length ? (
                history.data.map((entry) => (
                  <tr
                    key={entry.id}
                    className="transition-colors duration-100"
                    style={{ borderBottom: '1px solid var(--border)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td className="px-4 py-2.5" title={entry.file_path}>
                      <span
                        className="truncate max-w-xs text-sm block"
                        style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                      >
                        {truncatePath(entry.file_path)}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className="text-xs font-medium capitalize"
                        style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                      >
                        {entry.provider_name}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className="text-xs uppercase"
                        style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                      >
                        {entry.language}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
                        style={{
                          backgroundColor: entry.format === 'ass' ? 'var(--success)18' : 'var(--bg-primary)',
                          color: entry.format === 'ass' ? 'var(--success)' : 'var(--text-secondary)',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        {entry.format || '?'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 hidden sm:table-cell">
                      <span
                        className="text-xs tabular-nums"
                        style={{
                          fontFamily: 'var(--font-mono)',
                          color: entry.score >= 300 ? 'var(--success)' : entry.score >= 200 ? 'var(--warning)' : 'var(--text-muted)',
                        }}
                      >
                        {entry.score}
                      </span>
                    </td>
                    <td
                      className="px-3 py-2.5 text-xs tabular-nums hidden md:table-cell"
                      style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                    >
                      {entry.downloaded_at ? formatRelativeTime(entry.downloaded_at) : ''}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {entry.format && entry.language && entry.file_path && (
                          <>
                            <button
                              onClick={() => {
                                const lastDot = entry.file_path.lastIndexOf('.')
                                const base = lastDot > 0 ? entry.file_path.substring(0, lastDot) : entry.file_path
                                setEditorFilePath(`${base}.${entry.language}.${entry.format}`)
                                setEditorMode('preview')
                              }}
                              className="p-1 rounded transition-colors duration-150"
                              title="Preview subtitle"
                              style={{ color: 'var(--text-muted)' }}
                              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                            >
                              <Eye size={14} />
                            </button>
                            <button
                              onClick={() => {
                                const lastDot = entry.file_path.lastIndexOf('.')
                                const base = lastDot > 0 ? entry.file_path.substring(0, lastDot) : entry.file_path
                                setEditorFilePath(`${base}.${entry.language}.${entry.format}`)
                                setEditorMode('diff')
                              }}
                              className="p-1 rounded transition-colors duration-150"
                              title="View diff with backup"
                              style={{ color: 'var(--text-muted)' }}
                              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                            >
                              <GitCompare size={14} />
                            </button>
                          </>
                        )}
                        <button
                          onClick={() => addBlacklist.mutate({
                            provider_name: entry.provider_name,
                            subtitle_id: entry.subtitle_id,
                            language: entry.language,
                            file_path: entry.file_path,
                            reason: t('history.blacklisted_from_history'),
                          })}
                          disabled={addBlacklist.isPending}
                          className="p-1 rounded transition-colors duration-150"
                          title={t('history.add_to_blacklist')}
                          style={{ color: 'var(--text-muted)' }}
                          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
                          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                        >
                          <Ban size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
                    {t('history.no_history')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {history && history.total_pages > 1 && (
          <div
            className="flex items-center justify-between px-4 py-2.5"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {t('page_info', { page: history.page, totalPages: history.total_pages, total: history.total })}
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
                onClick={() => setPage((p) => Math.min(history.total_pages, p + 1))}
                disabled={page >= history.total_pages}
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

      {/* Subtitle Editor Modal */}
      {editorFilePath && (
        <SubtitleEditorModal
          filePath={editorFilePath}
          initialMode={editorMode}
          onClose={() => setEditorFilePath(null)}
        />
      )}
    </div>
  )
}
