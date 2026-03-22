import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { formatRelativeTime } from '@/lib/utils'
import { ScoreBadge } from './ScoreBadge'
import type { EpisodeHistoryEntry } from '@/lib/types'

export interface EpisodeHistoryPanelProps {
  readonly entries: EpisodeHistoryEntry[]
  readonly isLoading: boolean
}

export function EpisodeHistoryPanel({ entries, isLoading }: EpisodeHistoryPanelProps) {
  const { t } = useTranslation('library')
  if (isLoading) {
    return (
      <div
        className="px-6 py-4 flex items-center gap-2 text-sm"
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}
      >
        <Loader2 size={14} className="animate-spin" />
        {t('series_detail.loading_history')}
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div
        className="px-6 py-4 text-sm"
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}
      >
        {t('series_detail.no_history')}
      </div>
    )
  }

  return (
    <div style={{ backgroundColor: 'var(--bg-primary)' }} className="px-4 py-3">
      <span className="text-xs font-semibold uppercase tracking-wider mb-2 block" style={{ color: 'var(--text-muted)' }}>
        {t('series_detail.history_count', { count: entries.length })}
      </span>
      <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Date</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Action</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Provider</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Format</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Score</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, i) => (
              <tr
                key={i}
                style={{ borderBottom: i < entries.length - 1 ? '1px solid var(--border)' : undefined }}
              >
                <td className="px-3 py-1.5 text-xs tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {entry.date ? formatRelativeTime(entry.date) : '-'}
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase font-medium"
                    style={{
                      backgroundColor: entry.action === 'download' ? 'rgba(29,184,212,0.1)' : 'rgba(16,185,129,0.1)',
                      color: entry.action === 'download' ? 'var(--accent)' : 'var(--success)',
                    }}
                  >
                    {entry.action}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-xs" style={{ fontFamily: 'var(--font-mono)' }}>
                  {entry.provider_name || '-'}
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
                    style={{
                      backgroundColor: entry.format === 'ass' ? 'rgba(16,185,129,0.1)' : 'var(--bg-surface)',
                      color: entry.format === 'ass' ? 'var(--success)' : 'var(--text-secondary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {entry.format || '-'}
                  </span>
                </td>
                <td className="px-3 py-1.5">
                  {entry.score > 0 ? <ScoreBadge score={entry.score} /> : <span className="text-xs" style={{ color: 'var(--text-muted)' }}>-</span>}
                </td>
                <td className="px-3 py-1.5 text-xs" style={{ color: entry.status === 'completed' || entry.status === 'downloaded' ? 'var(--success)' : entry.error ? 'var(--error)' : 'var(--text-secondary)' }}>
                  {entry.error || entry.status || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
