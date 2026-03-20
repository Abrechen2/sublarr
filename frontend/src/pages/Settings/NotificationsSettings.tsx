/**
 * NotificationsSettings — Settings page for notification configuration.
 *
 * Three sections:
 * 1. Notification Channels – notification toggles, webhook channels, templates
 * 2. Events & Hooks        – event catalog, hooks, webhooks, and hook logs
 * 3. Quiet Hours (advanced – collapsed by default) – suppress notifications during time periods
 */
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell, Webhook, Moon } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'

// ─── Lazy sub-tabs ───────────────────────────────────────────────────────────

const NotificationTemplatesTab = lazy(() =>
  import('./NotificationTemplatesTab').then((m) => ({ default: m.NotificationTemplatesTab })),
)

const EventsHooksTab = lazy(() =>
  import('./EventsTab').then((m) => ({ default: m.EventsHooksTab })),
)

// ─── Skeleton ────────────────────────────────────────────────────────────────

function SectionSkeleton() {
  return (
    <div data-testid="section-skeleton" className="animate-pulse space-y-3 py-2">
      {[...Array(3)].map((_, i) => (
        <div
          key={i}
          className="h-8 rounded"
          style={{ backgroundColor: 'var(--bg-surface-hover)', width: i === 0 ? '70%' : '100%' }}
        />
      ))}
    </div>
  )
}

// ─── NotificationsSettings Page ───────────────────────────────────────────────

export function NotificationsSettings() {
  const { t } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title={t('settings.categories.notifications.title', 'Notifications')}
      subtitle={t(
        'settings.categories.notifications.description',
        'Channels, events, hooks, and quiet hours settings',
      )}
    >
      {/* 1. Notification Channels */}
      <div data-testid="section-notification-channels">
        <SettingsSection
          title={t('settings.notifications.channels.title', 'Notification Channels')}
          description={t(
            'settings.notifications.channels.description',
            'Configure notification toggles, webhook channels, and message templates.',
          )}
          icon={<Bell size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="notification-channels-content">
            <Suspense fallback={<SectionSkeleton />}>
              <NotificationTemplatesTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>

      {/* 2. Events & Hooks */}
      <div data-testid="section-events-hooks">
        <SettingsSection
          title={t('settings.notifications.eventsHooks.title', 'Events & Hooks')}
          description={t(
            'settings.notifications.eventsHooks.description',
            'Manage event catalog, hooks, webhooks, and hook execution logs.',
          )}
          icon={<Webhook size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="events-hooks-content">
            <Suspense fallback={<SectionSkeleton />}>
              <EventsHooksTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>

      {/* 3. Quiet Hours (advanced — collapsed by default) */}
      <div data-testid="section-quiet-hours">
        <SettingsSection
          title={t('settings.notifications.quietHours.title', 'Quiet Hours')}
          description={t(
            'settings.notifications.quietHours.description',
            'Suppress notifications during specific time periods.',
          )}
          icon={<Moon size={16} style={{ color: 'var(--accent)' }} />}
          advanced={
            <p
              className="text-[12px] text-[var(--text-muted)] py-2"
              data-testid="quiet-hours-advanced-content"
            >
              {t(
                'settings.notifications.quietHours.placeholder',
                'Configure quiet hours to suppress notifications during specific time periods.',
              )}
            </p>
          }
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-2"
            data-testid="quiet-hours-summary"
          >
            {t(
              'settings.notifications.quietHours.summary',
              'Define time windows during which all notification delivery is paused.',
            )}
          </p>
        </SettingsSection>
      </div>
    </SettingsDetailLayout>
  )
}
