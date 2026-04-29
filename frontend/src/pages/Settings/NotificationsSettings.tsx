/**
 * NotificationsSettings — Settings page for notification configuration.
 *
 * Three sections:
 * 1. Notification Channels – notification toggles, webhook channels, templates
 * 2. Events & Hooks        – event catalog, hooks, webhooks, and hook logs
 * 3. Quiet Hours (advanced – collapsed by default) – suppress notifications during time periods
 */
import { lazy, Suspense, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell, Webhook, Moon, History, Loader2 } from 'lucide-react'
import {
  useQuietHours,
  useCreateQuietHours,
  useUpdateQuietHours,
} from '@/hooks/useSystemApi'
import { toast } from '@/components/shared/Toast'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'

// Settings Template B (FormLayout). Four sections — well under the cap.
// Quiet Hours stays advanced-collapsed; the TOC entry still appears so the
// section is discoverable for users who want to enable it.
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'channels',     titleKey: 'notifications_page.channels_section' },
  { id: 'events-hooks', titleKey: 'notifications_page.events_hooks_section' },
  { id: 'history',      titleKey: 'notifications_page.history_section' },
  { id: 'quiet-hours',  titleKey: 'notifications_page.quiet_hours_section' },
]

// ─── Lazy sub-tabs ───────────────────────────────────────────────────────────

const NotificationTemplatesTab = lazy(() =>
  import('./NotificationTemplatesTab').then((m) => ({ default: m.NotificationTemplatesTab })),
)

const EventsHooksTab = lazy(() =>
  import('./EventsTab').then((m) => ({ default: m.EventsHooksTab })),
)

const NotificationHistoryTab = lazy(() =>
  import('./NotificationHistoryTab').then((m) => ({ default: m.NotificationHistoryTab })),
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

// ─── Shared input style for Quiet Hours ──────────────────────────────────────

const quietInputStyle: React.CSSProperties = {
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '6px',
  padding: '7px 12px',
  fontSize: '13px',
  fontFamily: 'var(--font-body)',
  width: '160px',
  outline: 'none',
}

// ─── Quiet Hours Config ───────────────────────────────────────────────────────
//
// Single-window UI that talks directly to the `/api/v1/notifications/quiet-hours`
// table CRUD (the only storage `notifier.is_quiet_hours()` actually reads).
// Earlier this stub wrote flat `quiet_hours_*` config_entries that the
// dispatcher never consumed — toggling it had no effect on notification
// delivery. The table backs multi-window configs; power users can hit the
// API directly. The UI keeps the simple "one window, on/off, start/end"
// flow most users want.

const QH_DEFAULTS = {
  start: '23:00',
  end: '07:00',
  name: 'Quiet Hours',
  days_of_week: '[0,1,2,3,4,5,6]',
  exception_events: '["error"]',
}

function QuietHoursConfigStub() {
  const { t } = useTranslation('settings')
  const { data: configs, isLoading } = useQuietHours()
  const createMut = useCreateQuietHours()
  const updateMut = useUpdateQuietHours()

  const existing = configs && configs.length > 0 ? configs[0] : null
  const existingId = existing?.id ?? null

  const [enabled, setEnabled] = useState(false)
  const [start, setStart] = useState(QH_DEFAULTS.start)
  const [end, setEnd] = useState(QH_DEFAULTS.end)

  // Hydrate local state when the server config arrives or changes.
  useEffect(() => {
    if (existing) {
      // `enabled` from the API is an integer (1/0) per the backend model.
      setEnabled(Number(existing.enabled) === 1)
      setStart(existing.start_time || QH_DEFAULTS.start)
      setEnd(existing.end_time || QH_DEFAULTS.end)
    }
  }, [existing])

  const persist = (next: { enabled?: boolean; start?: string; end?: string }) => {
    const payload = {
      name: existing?.name ?? QH_DEFAULTS.name,
      start_time: next.start ?? start,
      end_time: next.end ?? end,
      enabled: (next.enabled ?? enabled) ? 1 : 0,
      days_of_week: QH_DEFAULTS.days_of_week,
      exception_events: QH_DEFAULTS.exception_events,
    }
    if (existingId !== null) {
      updateMut.mutate(
        { id: existingId, data: payload },
        {
          onSuccess: () => toast(t('actions.saved', 'Saved')),
          onError: () => toast(t('actions.save_failed', 'Save failed'), 'error'),
        },
      )
    } else {
      createMut.mutate(payload, {
        onSuccess: () => toast(t('actions.saved', 'Saved')),
        onError: () => toast(t('actions.save_failed', 'Save failed'), 'error'),
      })
    }
  }

  const handleToggle = () => {
    const next = !enabled
    setEnabled(next)
    persist({ enabled: next })
  }

  const handleSave = () => {
    persist({})
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div data-testid="quiet-hours-config-stub" className="space-y-4">
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
            'Configure the time window during which notifications are suppressed.',
          )}
        </span>
      </div>

      <FormGroup
        label={t('settings.notifications.quietHours.enabled', 'Enable Quiet Hours')}
        hint={t(
          'settings.notifications.quietHours.enabledHint',
          'Suppress all notifications during the configured window.',
        )}
        data-testid="form-group-quiet-hours-enabled"
      >
        <div data-testid="toggle-quiet-hours-enabled">
          <button
            data-testid="quiet-hours-enabled-toggle"
            type="button"
            role="switch"
            aria-checked={enabled}
            onClick={handleToggle}
            disabled={createMut.isPending || updateMut.isPending}
            className="relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors duration-200"
            style={{ backgroundColor: enabled ? 'var(--accent)' : 'var(--border)' }}
          >
            <span
              className="inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 mt-0.5"
              style={{ transform: enabled ? 'translateX(16px)' : 'translateX(2px)' }}
            />
          </button>
        </div>
      </FormGroup>

      <FormGroup
        label={t('settings.notifications.quietHours.start', 'Start Time')}
        hint={t('settings.notifications.quietHours.startHint', 'Time when quiet hours begin (HH:MM)')}
        htmlFor="quiet-hours-start"
        data-testid="form-group-quiet-hours-start"
      >
        <input
          id="quiet-hours-start"
          data-testid="quiet-hours-start-input"
          type="time"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          placeholder="23:00"
          style={{ ...quietInputStyle, width: '120px' }}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.notifications.quietHours.end', 'End Time')}
        hint={t('settings.notifications.quietHours.endHint', 'Time when quiet hours end (HH:MM)')}
        htmlFor="quiet-hours-end"
        data-testid="form-group-quiet-hours-end"
      >
        <input
          id="quiet-hours-end"
          data-testid="quiet-hours-end-input"
          type="time"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
          placeholder="07:00"
          style={{ ...quietInputStyle, width: '120px' }}
        />
      </FormGroup>

      <div className="flex justify-end pt-1">
        <button
          data-testid="quiet-hours-save-btn"
          type="button"
          onClick={handleSave}
          disabled={createMut.isPending || updateMut.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {createMut.isPending || updateMut.isPending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : null}
          {t('actions.save', 'Save')}
        </button>
      </div>
    </div>
  )
}

// ─── NotificationsSettings Page ───────────────────────────────────────────────

export function NotificationsSettings() {
  const { t } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('settings.categories.notifications.title', 'Notifications')}
      subtitle={t(
        'settings.categories.notifications.description',
        'Channels, events, hooks, and quiet hours settings',
      )}
    >
      <FormLayout sections={SECTIONS}>

      {/* 1. Notification Channels */}
      <section id="channels" data-testid="settings.notifications.section-channels">
      <div data-testid="section-notification-channels">
        <SettingsSection
          title={t('notifications_page.channels_section')}
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
      </section>

      {/* 2. Events & Hooks */}
      <section id="events-hooks" data-testid="settings.notifications.section-events-hooks">
      <div data-testid="section-events-hooks">
        <SettingsSection
          title={t('notifications_page.events_hooks_section')}
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
      </section>

      {/* 3. Notification History */}
      <section id="history" data-testid="settings.notifications.section-history">
      <div data-testid="section-notification-history">
        <SettingsSection
          title={t('notifications_page.history_section')}
          description={t(
            'settings.notifications.history.description',
            'Recent notifications sent, with resend capability.',
          )}
          icon={<History size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="notification-history-content">
            <Suspense fallback={<SectionSkeleton />}>
              <NotificationHistoryTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>
      </section>

      {/* 4. Quiet Hours (advanced — collapsed by default) */}
      <section id="quiet-hours" data-testid="settings.notifications.section-quiet-hours">
      <div data-testid="section-quiet-hours">
        <SettingsSection
          title={t('notifications_page.quiet_hours_section')}
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
      </section>

      </FormLayout>
    </SettingsDetailLayout>
  )
}
