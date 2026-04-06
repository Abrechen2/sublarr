/**
 * UnifiedHistoryTab — merges Download-Verlauf and ActivityLog into one tab.
 *
 * Sub-filter pills switch between:
 *   - Downloads  → HistoryPage (subtitle_downloads, full provider/score detail)
 *   - Extraktionen / Löschungen / Scans → ActivityLogTab with pre-selected filter
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { HistoryPage } from '@/pages/History'
import { ActivityLogTab } from '@/components/activity/ActivityLogTab'

type SubFilter = 'downloads' | 'extract' | 'delete' | 'scan'

export function UnifiedHistoryTab() {
  const { t } = useTranslation('activity')
  const [filter, setFilter] = useState<SubFilter>('downloads')

  const pills: { id: SubFilter; label: string }[] = [
    { id: 'downloads', label: t('history.filter_downloads') },
    { id: 'extract',   label: t('history.filter_extract') },
    { id: 'delete',    label: t('history.filter_delete') },
    { id: 'scan',      label: t('history.filter_scan') },
  ]

  return (
    <div>
      {/* Sub-filter pills */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '16px' }}>
        {pills.map((p) => (
          <button
            key={p.id}
            onClick={() => setFilter(p.id)}
            style={{
              padding: '4px 12px',
              borderRadius: '4px',
              border: '1px solid var(--border)',
              background: filter === p.id ? 'var(--accent)' : 'transparent',
              color: filter === p.id ? '#fff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: filter === p.id ? 600 : 400,
              transition: 'all 0.15s',
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      {filter === 'downloads'
        ? <HistoryPage />
        : <ActivityLogTab defaultFilter={filter} hideFilter />
      }
    </div>
  )
}
