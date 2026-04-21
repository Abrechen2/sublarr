import { useTranslation } from 'react-i18next'

import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'
import { useConfig, useUpdateConfig } from '@/hooks/useSystemApi'
import { useAutomationStatus, useRunAutomationNow } from '@/hooks/useWantedApi'

// 0.71.0 — one settings page, one master toggle, three granular sub-toggles,
// plus a live status card. Uses the existing grouped ScanningSettings view so
// reads/writes go through /api/v1/config without per-key plumbing.

type AutomationKeys =
  | 'subtitle_automation_enabled'
  | 'subtitle_automation_queue_enabled'
  | 'subtitle_automation_drain_interval_minutes'
  | 'embedded_allow_sdh'
  | 'embedded_sdh_penalty'
  | 'cleanup_foreign_tracks_default'
  | 'cleanup_foreign_tracks_keep_und'

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export function SubtitleAutomationPage() {
  const { t } = useTranslation('settings')
  const { t: tc } = useTranslation('common')
  const { data: config } = useConfig()
  const update = useUpdateConfig()
  const status = useAutomationStatus()
  const runNow = useRunAutomationNow()

  const cfg = (config ?? {}) as Partial<Record<AutomationKeys, unknown>>

  const set = (key: AutomationKeys, value: unknown) => {
    update.mutate(
      { [key]: value },
      {
        onError: () => toast(tc('errors.save_failed', 'Failed to save'), 'error'),
      }
    )
  }

  return (
    <SettingsDetailLayout
      title={t('subtitle_automation_page.title', 'Subtitle Automation')}
      subtitle={t(
        'subtitle_automation_page.subtitle',
        'One-click pipeline for embedded extract, SDH handling, and foreign-track cleanup'
      )}
    >
      {/* Master toggle */}
      <SettingsSection
        title={t('subtitle_automation_page.master.title', 'Automation')}
        description={t(
          'subtitle_automation_page.master.description',
          'Master switch for the entire pipeline. When off, the sub-toggles below are honored individually.'
        )}
      >
        <SettingRow
          label={t('subtitle_automation_page.master.label', 'Enable full automation')}
          description={t(
            'subtitle_automation_page.master.help',
            'On: embedded subs auto-extract, SDH is a valid fallback, and foreign-language tracks can be cleaned from containers.'
          )}
        >
          <Toggle
            checked={Boolean(cfg.subtitle_automation_enabled)}
            onChange={(v) => set('subtitle_automation_enabled', v)}
          />
        </SettingRow>
      </SettingsSection>

      {/* Queue drain */}
      <SettingsSection
        title={t('subtitle_automation_page.queue.title', 'Auto-Extract Queue')}
        description={t(
          'subtitle_automation_page.queue.description',
          'Drain worker that runs until every pending embedded extract has landed on disk.'
        )}
      >
        <SettingRow
          label={t('subtitle_automation_page.queue.enabled', 'Drain worker')}
          description={t(
            'subtitle_automation_page.queue.enabled_help',
            'Processes new library items automatically. Falls back to the legacy "Auto-Extract on scan" behavior when off.'
          )}
        >
          <Toggle
            checked={Boolean(cfg.subtitle_automation_queue_enabled ?? true)}
            onChange={(v) => set('subtitle_automation_queue_enabled', v)}
          />
        </SettingRow>
        <SettingRow
          label={t('subtitle_automation_page.queue.interval', 'Drain interval (minutes)')}
          description={t(
            'subtitle_automation_page.queue.interval_help',
            'Scheduler cadence. Lower = more responsive, higher = lower CPU.'
          )}
        >
          <input
            type="number"
            min={1}
            max={60}
            value={(cfg.subtitle_automation_drain_interval_minutes as number) ?? 2}
            onChange={(e) =>
              set(
                'subtitle_automation_drain_interval_minutes',
                Math.max(1, Math.min(60, Number(e.target.value) || 2))
              )
            }
            className="w-20 px-2 py-1 rounded text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </SettingRow>
      </SettingsSection>

      {/* SDH */}
      <SettingsSection
        title={t('subtitle_automation_page.sdh.title', 'SDH Tolerance')}
        description={t(
          'subtitle_automation_page.sdh.description',
          'Whether SDH/CC tracks (Subtitles for Deaf / Hard-of-Hearing) are acceptable sources.'
        )}
      >
        <SettingRow
          label={t('subtitle_automation_page.sdh.allow', 'Allow SDH as source')}
          description={t(
            'subtitle_automation_page.sdh.allow_help',
            'Many Disney/Marvel rips only ship English as SDH. Keep this on unless you truly never want SDH extracted.'
          )}
        >
          <Toggle
            checked={Boolean(cfg.embedded_allow_sdh ?? true)}
            onChange={(v) => set('embedded_allow_sdh', v)}
          />
        </SettingRow>
        <SettingRow
          label={t('subtitle_automation_page.sdh.penalty', 'SDH score penalty')}
          description={t(
            'subtitle_automation_page.sdh.penalty_help',
            'Points subtracted from SDH tracks so a non-SDH track wins a tie.'
          )}
        >
          <input
            type="number"
            min={0}
            max={50}
            value={(cfg.embedded_sdh_penalty as number) ?? 5}
            onChange={(e) =>
              set(
                'embedded_sdh_penalty',
                Math.max(0, Math.min(50, Number(e.target.value) || 0))
              )
            }
            className="w-20 px-2 py-1 rounded text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </SettingRow>
      </SettingsSection>

      {/* Foreign track cleanup */}
      <SettingsSection
        title={t('subtitle_automation_page.cleanup.title', 'Foreign-Track Cleanup')}
        description={t(
          'subtitle_automation_page.cleanup.description',
          'After extraction succeeds, remove non-target-language subtitle tracks from the container. Backups go to the trash folder — nothing is permanently deleted.'
        )}
      >
        <SettingRow
          label={t('subtitle_automation_page.cleanup.default', 'Strip by default')}
          description={t(
            'subtitle_automation_page.cleanup.default_help',
            'Global default; per-series overrides live on the series settings panel.'
          )}
        >
          <Toggle
            checked={Boolean(cfg.cleanup_foreign_tracks_default)}
            onChange={(v) => set('cleanup_foreign_tracks_default', v)}
          />
        </SettingRow>
        <SettingRow
          label={t('subtitle_automation_page.cleanup.keep_und', 'Keep undetermined (und)')}
          description={t(
            'subtitle_automation_page.cleanup.keep_und_help',
            'Preserve tracks where the language tag is "und". Leave off unless your library has unlabelled subs you want to keep.'
          )}
        >
          <Toggle
            checked={Boolean(cfg.cleanup_foreign_tracks_keep_und)}
            onChange={(v) => set('cleanup_foreign_tracks_keep_und', v)}
          />
        </SettingRow>
      </SettingsSection>

      {/* Live status card */}
      <SettingsSection
        title={t('subtitle_automation_page.status.title', 'Live Status')}
        description={t(
          'subtitle_automation_page.status.description',
          'Queue counts refresh every 5 seconds.'
        )}
      >
        {status.isLoading ? (
          <div className="text-sm text-muted">{tc('ui.loading', 'Loading…')}</div>
        ) : status.data ? (
          <div className="space-y-2 text-sm">
            <div className="flex gap-4 flex-wrap">
              <div>
                <span className="text-muted mr-1">
                  {t('subtitle_automation_page.status.pending', 'Pending')}:
                </span>
                <strong>{status.data.queue.pending}</strong>
              </div>
              <div>
                <span className="text-muted mr-1">
                  {t('subtitle_automation_page.status.running', 'Running')}:
                </span>
                <strong>{status.data.queue.running}</strong>
              </div>
              <div>
                <span className="text-muted mr-1">
                  {t('subtitle_automation_page.status.failed', 'Failed')}:
                </span>
                <strong style={{ color: 'var(--error)' }}>{status.data.queue.failed}</strong>
              </div>
              <div>
                <span className="text-muted mr-1">
                  {t('subtitle_automation_page.status.done', 'Done')}:
                </span>
                <strong>{status.data.queue.done}</strong>
              </div>
            </div>
            <div>
              <span className="text-muted mr-1">
                {t('subtitle_automation_page.status.last_run', 'Last run')}:
              </span>
              {formatDate(status.data.last_run_at)}
            </div>
            {status.data.last_error && (
              <div style={{ color: 'var(--error)' }}>
                {t('subtitle_automation_page.status.last_error', 'Last error')}:{' '}
                {status.data.last_error}
              </div>
            )}
            <div className="pt-2">
              <button
                className="px-3 py-1.5 rounded text-sm font-medium"
                style={{
                  backgroundColor: 'var(--accent)',
                  color: 'white',
                  border: 'none',
                  cursor: 'pointer',
                }}
                disabled={runNow.isPending || !status.data.enabled}
                onClick={() => {
                  runNow.mutate(undefined, {
                    onSuccess: (r) => {
                      toast(
                        t(
                          'subtitle_automation_page.status.run_started',
                          'Drain triggered ({{n}} processed).',
                          { n: r.processed ?? 0 }
                        ),
                        r.status === 'disabled' ? 'error' : 'success'
                      )
                    },
                  })
                }}
              >
                {t('subtitle_automation_page.status.run_now', 'Run now')}
              </button>
            </div>
          </div>
        ) : null}
      </SettingsSection>
    </SettingsDetailLayout>
  )
}
