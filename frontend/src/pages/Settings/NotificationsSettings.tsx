/**
 * NotificationsSettings — Settings page for notification configuration.
 *
 * Three sections:
 * 1. Notification Channels – notification toggles, webhook channels, templates
 * 2. Events & Hooks        – event catalog, hooks, webhooks, and hook logs
 * 3. Quiet Hours (advanced – collapsed by default) – suppress notifications during time periods
 */
import { lazy, Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell, Webhook, Moon } from 'lucide-react'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
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

// ─── Quiet Hours Config Stub ─────────────────────────────────────────────────

function QuietHoursConfigStub() {
  const { t } = useTranslation('common')
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()

  const cfg = configData as Record<string, unknown> | undefined

  const [enabled, setEnabled] = useState(
    () => String(cfg?.quiet_hours_enabled ?? 'false') === 'true'
  )
  const [start, setStart]       = useState(() => String(cfg?.quiet_hours_start ?? ''))
  const [end, setEnd]           = useState(() => String(cfg?.quiet_hours_end ?? ''))
  const [timezone, setTimezone] = useState(() => String(cfg?.quiet_hours_timezone ?? ''))

  const handleSave = () => {
    updateConfig.mutate({
      quiet_hours_enabled:  String(enabled),
      quiet_hours_start:    start,
      quiet_hours_end:      end,
      quiet_hours_timezone: timezone,
    })
  }

  return (
    <div
      data-testid="quiet-hours-config-stub"
      className="space-y-4"
    >
      {/* Info banner */}
      <div
        data-testid="quiet-hours-stub-banner"
        className="flex items-start gap-2 px-3 py-2 rounded-md text-[12px]"
        style={{
          backgroundColor: 'var(--accent-bg)',
          border: '1px solid var(--accent-dim)',
          color: 'var(--text-secondary)',
        }}
      >
        <span style={{ color: 'var(--accent)', flexShrink: 0 }}>i</span>
        <span>
          {t(
            'settings.notifications.quietHours.stubBanner',
            'Diese Felder werden nach dem nächsten Backend-Update aktiv.',
          )}
        </span>
      </div>

      {/* quiet_hours_enabled — Toggle */}
      <div
        className="flex items-center justify-between py-2"
        style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}
      >
        <div className="flex flex-col gap-0.5">
          <span className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
            {t('settings.notifications.quietHours.enabled', 'Quiet Hours Enabled')}
          </span>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {t(
              'settings.notifications.quietHours.enabledHint',
              'Suppress all notifications during the configured window.',
            )}
          </span>
        </div>
        <button
          data-testid="quiet-hours-enabled-toggle"
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => setEnabled((v) => !v)}
          className="relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors duration-200"
          style={{ backgroundColor: enabled ? 'var(--accent)' : 'var(--border)' }}
        >
          <span
            className="inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 mt-0.5"
            style={{ transform: enabled ? 'translateX(16px)' : 'translateX(2px)' }}
          />
        </button>
      </div>

      {/* quiet_hours_start */}
      <div
        className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 py-2"
        style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}
      >
        <label
          htmlFor="quiet-hours-start"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {t('settings.notifications.quietHours.start', 'Start Time')}
        </label>
        <input
          id="quiet-hours-start"
          data-testid="quiet-hours-start-input"
          type="text"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          placeholder="23:00"
          className="px-2.5 py-1.5 rounded text-xs focus:outline-none"
          style={{
            width: '120px',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        />
      </div>

      {/* quiet_hours_end */}
      <div
        className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 py-2"
        style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}
      >
        <label
          htmlFor="quiet-hours-end"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {t('settings.notifications.quietHours.end', 'End Time')}
        </label>
        <input
          id="quiet-hours-end"
          data-testid="quiet-hours-end-input"
          type="text"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
          placeholder="07:00"
          className="px-2.5 py-1.5 rounded text-xs focus:outline-none"
          style={{
            width: '120px',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        />
      </div>

      {/* quiet_hours_timezone */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 py-2">
        <label
          htmlFor="quiet-hours-timezone"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {t('settings.notifications.quietHours.timezone', 'Timezone')}
        </label>
        <input
          id="quiet-hours-timezone"
          data-testid="quiet-hours-timezone-input"
          type="text"
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          placeholder="UTC"
          className="px-2.5 py-1.5 rounded text-xs focus:outline-none"
          style={{
            width: '160px',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        />
      </div>

      {/* Save */}
      <div className="flex justify-end pt-1">
        <button
          data-testid="quiet-hours-save-btn"
          type="button"
          onClick={handleSave}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {t('actions.save', 'Save')}
        </button>
      </div>
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
          advanced={<QuietHoursConfigStub />}
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
