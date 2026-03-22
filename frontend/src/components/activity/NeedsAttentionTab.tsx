import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Search, SkipForward } from 'lucide-react'
import { useWantedItems, useSearchWantedItem, useUpdateWantedStatus } from '@/hooks/useApi'
import { formatRelativeTime } from '@/lib/utils'
import type { WantedItem } from '@/lib/types'

// ─── Types ────────────────────────────────────────────────────────────────────

type IssueType = 'failed' | 'low_score'

interface ResolvedItem {
  readonly item: WantedItem
  readonly issueType: IssueType
}

function resolveIssueType(item: WantedItem): IssueType | null {
  if (item.status === 'failed') return 'failed'
  if (item.current_score !== null && item.current_score > 0 && item.current_score < 50) return 'low_score'
  return null
}

// ─── Issue Pill ───────────────────────────────────────────────────────────────

function IssuePill({ issueType, score }: { readonly issueType: IssueType; readonly score: number }) {
  const { t } = useTranslation('common')

  const label =
    issueType === 'failed'
      ? t('needsAttention.reason.noMatch', 'No Match')
      : t('needsAttention.reason.lowScore', `Score ${score}`)

  const color = issueType === 'failed' ? 'var(--error)' : 'var(--warning)'

  return (
    <span
      data-testid="issue-pill"
      className="inline-block text-[10px] font-medium px-1.5 py-0.5 rounded"
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)`,
      }}
    >
      {label}
    </span>
  )
}

// ─── NeedsAttentionTab ────────────────────────────────────────────────────────

export function NeedsAttentionTab() {
  const { t } = useTranslation('common')
  const { t: ta } = useTranslation('activity')
  const { data, isLoading } = useWantedItems(1, 100)
  const searchMutation = useSearchWantedItem()
  const statusMutation = useUpdateWantedStatus()

  const attentionItems: readonly ResolvedItem[] = useMemo(() => {
    const items: WantedItem[] = data?.data ?? []
    const resolved: ResolvedItem[] = []
    for (const item of items) {
      const issueType = resolveIssueType(item)
      if (issueType !== null) {
        resolved.push({ item, issueType })
      }
    }
    return resolved
  }, [data?.data])

  const handleSearch = (id: number) => searchMutation.mutate(id)
  const handleSkip = (id: number) => statusMutation.mutate({ itemId: id, status: 'ignored' })

  if (isLoading) {
    return (
      <div
        data-testid="needs-attention-loading"
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[600px]">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Title', 'Issue', 'Score', 'Last Tried', 'Actions'].map((h) => (
                  <th
                    key={h}
                    className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td className="px-4 py-3"><div className="skeleton h-4 w-48 rounded" /></td>
                  <td className="px-4 py-3"><div className="skeleton h-4 w-20 rounded" /></td>
                  <td className="px-4 py-3"><div className="skeleton h-4 w-10 rounded" /></td>
                  <td className="px-4 py-3"><div className="skeleton h-4 w-16 rounded" /></td>
                  <td className="px-4 py-3"><div className="skeleton h-4 w-20 rounded" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  if (attentionItems.length === 0) {
    return (
      <div
        data-testid="needs-attention-empty"
        className="rounded-lg p-8 text-center"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <AlertTriangle size={24} style={{ color: 'var(--text-muted)', margin: '0 auto 8px' }} />
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {t('needsAttention.empty', 'No items need attention')}
        </p>
      </div>
    )
  }

  return (
    <div
      data-testid="needs-attention-tab"
      className="rounded-lg overflow-hidden"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[600px]">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th
                className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5"
                style={{ color: 'var(--text-muted)' }}
              >
                {ta('table.content', 'Title')}
              </th>
              <th
                className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5"
                style={{ color: 'var(--text-muted)' }}
              >
                {t('needsAttention.column.issue', 'Issue')}
              </th>
              <th
                className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5"
                style={{ color: 'var(--text-muted)' }}
              >
                {t('needsAttention.column.score', 'Score')}
              </th>
              <th
                className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5 hidden sm:table-cell"
                style={{ color: 'var(--text-muted)' }}
              >
                {t('needsAttention.column.lastTried', 'Last Tried')}
              </th>
              <th
                className="text-right text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5"
                style={{ color: 'var(--text-muted)' }}
              >
                {t('needsAttention.column.actions', 'Actions')}
              </th>
            </tr>
          </thead>
          <tbody>
            {attentionItems.map(({ item, issueType }) => (
              <tr
                key={item.id}
                data-testid={`attention-row-${item.id}`}
                className="transition-colors duration-100"
                style={{ borderBottom: '1px solid var(--border)' }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
              >
                <td className="px-4 py-2.5">
                  <div className="min-w-0">
                    <div
                      className="font-medium text-sm truncate max-w-xs"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {item.title}
                    </div>
                    {item.season_episode && (
                      <div
                        className="text-[11px] mt-0.5"
                        style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
                      >
                        {item.season_episode}
                      </div>
                    )}
                  </div>
                </td>
                <td className="px-4 py-2.5">
                  <IssuePill issueType={issueType} score={item.current_score} />
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className="text-xs tabular-nums"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      color:
                        item.current_score >= 300
                          ? 'var(--success)'
                          : item.current_score >= 200
                            ? 'var(--warning)'
                            : 'var(--text-muted)',
                    }}
                  >
                    {item.current_score}
                  </span>
                </td>
                <td
                  className="px-4 py-2.5 text-xs tabular-nums hidden sm:table-cell"
                  style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                >
                  {item.last_search_at ? formatRelativeTime(item.last_search_at) : '-'}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      data-testid={`btn-search-${item.id}`}
                      onClick={() => handleSearch(item.id)}
                      disabled={searchMutation.isPending}
                      className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors"
                      style={{
                        border: '1px solid var(--accent)',
                        backgroundColor: 'var(--accent-bg)',
                        color: 'var(--accent)',
                      }}
                      title={t('needsAttention.action.search', 'Search')}
                    >
                      <Search size={11} />
                      {t('needsAttention.action.search', 'Search')}
                    </button>
                    <button
                      data-testid={`btn-skip-${item.id}`}
                      onClick={() => handleSkip(item.id)}
                      disabled={statusMutation.isPending}
                      className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors"
                      style={{
                        border: '1px solid var(--border)',
                        color: 'var(--text-secondary)',
                      }}
                      title={t('needsAttention.action.skip', 'Skip')}
                    >
                      <SkipForward size={11} />
                      {t('needsAttention.action.skip', 'Skip')}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
