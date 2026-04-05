import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AttentionBanner } from './AttentionBanner'
import { useHistory } from '@/hooks/useProvidersApi'
import { parseMediaTitle, formatRelativeTime } from '@/lib/utils'

const FEED_LIMIT = 20

export function ActivityFeed() {
  const { t } = useTranslation('dashboard')
  const { data: historyData } = useHistory(1, FEED_LIMIT)

  const entries = historyData?.data ?? []
  const total = historyData?.total ?? 0

  return (
    <div
      data-testid="activity-feed"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        flex: 1,
        minHeight: 0,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 14px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: '11px',
            fontWeight: 700,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.4px',
          }}
        >
          {t('feed.title')}
        </span>
        <Link
          data-testid="feed-view-all"
          to="/activity?tab=history"
          style={{ fontSize: '11px', color: 'var(--accent)', textDecoration: 'none' }}
        >
          {t('feed.viewAll')} →
        </Link>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 10px' }}>
        <AttentionBanner />

        {entries.length === 0 ? (
          <div
            data-testid="feed-empty"
            style={{
              padding: '24px 0',
              textAlign: 'center',
              fontSize: '13px',
              color: 'var(--text-muted)',
            }}
          >
            {t('feed.empty')}
          </div>
        ) : (
          <>
            {entries.map((entry) => {
              const media = parseMediaTitle(entry.file_path ?? '')
              return (
                <div
                  key={entry.id}
                  data-testid={`feed-item-${entry.id}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '5px 4px',
                    borderRadius: '4px',
                  }}
                >
                  <span
                    data-testid={`feed-dot-${entry.id}`}
                    data-status="completed"
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: 'var(--success)',
                      flexShrink: 0,
                    }}
                  />
                  <span
                    style={{
                      flex: 1,
                      fontSize: '12px',
                      color: 'var(--text-secondary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={entry.file_path}
                  >
                    {media.title}
                    {media.episodeCode && (
                      <span style={{ color: 'var(--text-muted)', marginLeft: '5px', fontSize: '11px' }}>
                        {media.episodeCode}
                      </span>
                    )}
                  </span>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)', flexShrink: 0, whiteSpace: 'nowrap' }}>
                    {entry.provider_name}
                  </span>
                  {entry.downloaded_at && (
                    <span
                      style={{
                        fontSize: '10px',
                        color: 'var(--text-muted)',
                        whiteSpace: 'nowrap',
                        flexShrink: 0,
                      }}
                    >
                      {formatRelativeTime(entry.downloaded_at)}
                    </span>
                  )}
                </div>
              )
            })}

            {total > FEED_LIMIT && (
              <div
                data-testid="feed-more-events"
                style={{
                  textAlign: 'center',
                  padding: '8px 0',
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                }}
              >
                ··· {total - FEED_LIMIT} {t('feed.moreEvents')}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
