import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useActivity } from '@/hooks/useSystemApi'
import { parseMediaTitle, formatRelativeTime } from '@/lib/utils'
import type { ActivityEntry } from '@/api/system/activity'

const EVENT_TYPE_COLORS: Record<string, string> = {
  download: 'var(--success)',
  extract: 'var(--accent)',
  delete: 'var(--danger)',
  scan: 'var(--text-muted)',
}

const PER_PAGE = 50

function TypeBadge({ entry }: { entry: ActivityEntry }) {
  return (
    <span
      data-testid={`activity-type-${entry.id}`}
      data-type={entry.event_type}
      style={{
        display: 'inline-block',
        padding: '1px 6px',
        borderRadius: '3px',
        fontSize: '10px',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.3px',
        color: EVENT_TYPE_COLORS[entry.event_type] ?? 'var(--text-muted)',
        border: `1px solid ${EVENT_TYPE_COLORS[entry.event_type] ?? 'var(--border)'}`,
        flexShrink: 0,
        whiteSpace: 'nowrap',
      }}
    >
      {entry.event_type}
    </span>
  )
}

function ActivityRow({ entry }: { entry: ActivityEntry }) {
  const { t } = useTranslation('activity')
  const media = entry.file_path ? parseMediaTitle(entry.file_path) : null

  return (
    <div
      data-testid={`activity-row-${entry.id}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '7px 12px',
        borderBottom: '1px solid var(--border)',
        fontSize: '13px',
      }}
    >
      <TypeBadge entry={entry} />

      <span
        style={{
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          color: 'var(--text-primary)',
        }}
        title={entry.file_path ?? undefined}
      >
        {media ? (
          <>
            {media.title}
            {media.episodeCode && (
              <span style={{ color: 'var(--text-muted)', marginLeft: '5px', fontSize: '11px' }}>
                {media.episodeCode}
              </span>
            )}
          </>
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>
            {t('activity.scanEvent', 'Wanted scan')}
          </span>
        )}
      </span>

      <span style={{ fontSize: '11px', color: 'var(--text-muted)', flexShrink: 0, whiteSpace: 'nowrap' }}>
        {formatRelativeTime(entry.created_at)}
      </span>
    </div>
  )
}

const EVENT_TYPES = ['download', 'extract', 'delete', 'scan'] as const

export function ActivityLogTab({ defaultFilter }: { defaultFilter?: string }) {
  const { t } = useTranslation('activity')
  const [page, setPage] = useState(1)
  const [typeFilter, setTypeFilter] = useState<string | undefined>(defaultFilter)

  const { data, isLoading } = useActivity(page, PER_PAGE, typeFilter)
  const entries = data?.data ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1

  if (isLoading) {
    return (
      <div data-testid="activity-loading" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
        {t('activity.loading', 'Loading…')}
      </div>
    )
  }

  return (
    <div data-testid="activity-log-tab">
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '12px' }}>
        <button
          onClick={() => { setTypeFilter(undefined); setPage(1) }}
          style={{
            padding: '4px 10px',
            borderRadius: '4px',
            border: '1px solid var(--border)',
            background: typeFilter === undefined ? 'var(--accent)' : 'transparent',
            color: typeFilter === undefined ? '#fff' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontSize: '12px',
          }}
        >
          {t('activity.filterAll', 'All')}
        </button>
        {EVENT_TYPES.map((type) => (
          <button
            key={type}
            onClick={() => { setTypeFilter(type); setPage(1) }}
            style={{
              padding: '4px 10px',
              borderRadius: '4px',
              border: '1px solid var(--border)',
              background: typeFilter === type ? 'var(--accent)' : 'transparent',
              color: typeFilter === type ? '#fff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontSize: '12px',
              textTransform: 'capitalize',
            }}
          >
            {type}
          </button>
        ))}
      </div>

      {/* Table */}
      <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
        {entries.length === 0 ? (
          <div
            data-testid="activity-empty"
            style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}
          >
            {t('activity.empty', 'No activity recorded yet.')}
          </div>
        ) : (
          entries.map((entry) => <ActivityRow key={entry.id} entry={entry} />)
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '12px', alignItems: 'center' }}>
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            style={{ padding: '4px 10px', border: '1px solid var(--border)', borderRadius: '4px',
              cursor: page <= 1 ? 'not-allowed' : 'pointer', opacity: page <= 1 ? 0.4 : 1 }}
          >
            ←
          </button>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            {page} / {totalPages} ({total} {t('activity.events', 'events')})
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            style={{ padding: '4px 10px', border: '1px solid var(--border)', borderRadius: '4px',
              cursor: page >= totalPages ? 'not-allowed' : 'pointer', opacity: page >= totalPages ? 0.4 : 1 }}
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}
