import { useTranslation } from 'react-i18next'
import { Loader2, Download } from 'lucide-react'
import { ScoreBadge } from './ScoreBadge'
import type { WantedSearchResponse } from '@/lib/types'

export interface EpisodeSearchPanelProps {
  readonly results: WantedSearchResponse | null
  readonly isLoading: boolean
  readonly onProcess: (wantedId: number) => void
}

export function EpisodeSearchPanel({ results, isLoading, onProcess }: EpisodeSearchPanelProps) {
  const { t } = useTranslation('library')
  if (isLoading) {
    return (
      <div
        className="px-6 py-4 flex items-center gap-2 text-sm"
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}
      >
        <Loader2 size={14} className="animate-spin" />
        {t('series_detail.searching_providers')}
      </div>
    )
  }

  if (!results) return null

  const allResults = [
    ...results.target_results.map((r) => ({ ...r, _type: 'target' as const })),
    ...results.source_results.map((r) => ({ ...r, _type: 'source' as const })),
  ]

  if (allResults.length === 0) {
    return (
      <div
        className="px-6 py-4 text-sm"
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}
      >
        {t('series_detail.no_search_results')}
      </div>
    )
  }

  return (
    <div style={{ backgroundColor: 'var(--bg-primary)' }} className="px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          {t('series_detail.search_results', { count: allResults.length })}
        </span>
        <button
          onClick={() => onProcess(results.wanted_id)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-white hover:opacity-90"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <Download size={11} />
          {t('series_detail.download_best')}
        </button>
      </div>
      <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Provider</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Type</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Format</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Score</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Release</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Lang</th>
            </tr>
          </thead>
          <tbody>
            {allResults.map((r, i) => (
              <tr
                key={`${r.provider}-${r.subtitle_id}-${i}`}
                style={{ borderBottom: i < allResults.length - 1 ? '1px solid var(--border)' : undefined }}
              >
                <td className="px-3 py-1.5 text-xs" style={{ fontFamily: 'var(--font-mono)' }}>
                  {r.provider}
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase font-medium"
                    style={{
                      backgroundColor: r._type === 'target' ? 'rgba(16,185,129,0.1)' : 'rgba(29,184,212,0.1)',
                      color: r._type === 'target' ? 'var(--success)' : 'var(--accent)',
                    }}
                  >
                    {r._type === 'target' ? 'Target' : 'Source'}
                  </span>
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
                    style={{
                      backgroundColor: r.format === 'ass' ? 'rgba(16,185,129,0.1)' : 'var(--bg-surface)',
                      color: r.format === 'ass' ? 'var(--success)' : 'var(--text-secondary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {r.format}
                  </span>
                </td>
                <td className="px-3 py-1.5">
                  <ScoreBadge score={r.score} />
                </td>
                <td className="px-3 py-1.5 text-xs truncate max-w-[200px]" title={r.release_info || r.filename} style={{ color: 'var(--text-secondary)' }}>
                  {r.release_info || r.filename || '-'}
                </td>
                <td className="px-3 py-1.5 text-xs uppercase" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {r.language}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
