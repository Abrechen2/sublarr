/**
 * SystemDiagnosticsPage — observability + maintenance sub-page split out
 * from SystemSettings on 2026-04-26 because the parent page exceeded the
 * 6-section FormLayout cap.
 *
 * Hosts the "things you do reactively when something is wrong" sections:
 *
 *   1. Log Viewer
 *   2. Disk Monitoring
 *   3. Cache Management
 *   4. Integrations  (Bazarr compat / diagnostics / data export — advanced)
 *   5. Migration     (Bazarr DB import wizard — advanced)
 *
 * All five lived on /settings/system before the split. The dead
 * "Events & Hooks" redirect placeholder was deleted as part of the same
 * refactor (the actual events live on /settings/notifications, the
 * placeholder was a leftover from a 2026-Q1 reorganization).
 */
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { FileText, HardDrive, Database, Puzzle } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { numVal, boolVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

// ─── Lazy sub-tabs ───────────────────────────────────────────────────────────

const ProtokollTab = lazy(() =>
  import('./ProtokollTab').then((m) => ({ default: m.ProtokollTab })),
)
const IntegrationsTab = lazy(() =>
  import('./IntegrationsTab').then((m) => ({ default: m.IntegrationsTab })),
)
const MigrationTab = lazy(() =>
  import('./MigrationTab').then((m) => ({ default: m.MigrationTab })),
)
const CacheTab = lazy(() =>
  import('./CacheTab').then((m) => ({ default: m.CacheTab })),
)

const inputStyle: React.CSSProperties = { ...settingsInputStyle, width: '120px', outline: 'none' }

// ─── SectionSkeleton ─────────────────────────────────────────────────────────

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

// ─── Disk Monitoring Controls ────────────────────────────────────────────────

function DiskMonitoringControls() {
  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const { mutate: save, isPending } = useUpdateConfig()

  return (
    <div data-testid="disk-monitoring-controls">
      <FormGroup
        label={t('system_tab.disk_warning_threshold')}
        hint={t('system_tab.disk_warning_threshold_hint')}
        htmlFor="disk-warning-threshold-percent"
        data-testid="form-group-disk-warning-threshold-percent"
      >
        <input
          id="disk-warning-threshold-percent"
          type="number"
          data-testid="input-disk-warning-threshold-percent"
          style={{ ...inputStyle, maxWidth: '100px' }}
          value={numVal(config, 'disk_warning_threshold_percent', 90)}
          onChange={(e) =>
            save({ disk_warning_threshold_percent: Number(e.target.value) })
          }
          disabled={isPending}
          min={50}
          max={99}
        />
      </FormGroup>

      <FormGroup
        label={t('system_tab.notify_on_warning')}
        hint={t('system_tab.notify_on_warning_hint')}
        data-testid="form-group-disk-warning-notify"
      >
        <Toggle
          checked={boolVal(config, 'disk_warning_notify', true)}
          onChange={(v) => save({ disk_warning_notify: String(v) })}
          disabled={isPending}
          data-testid="toggle-disk-warning-notify"
        />
      </FormGroup>
    </div>
  )
}

// Settings Template B (FormLayout). Five sections — at the 6-cap.
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'log-viewer',      titleKey: 'system_diagnostics_page.log_viewer_section' },
  { id: 'disk-monitoring', titleKey: 'system_diagnostics_page.disk_monitoring_section' },
  { id: 'cache',           titleKey: 'system_diagnostics_page.cache_section' },
  { id: 'integrations',    titleKey: 'system_diagnostics_page.integrations_section', advancedCount: 1 },
  { id: 'migration',       titleKey: 'system_diagnostics_page.migration_section',    advancedCount: 1 },
]

// ─── SystemDiagnosticsPage ───────────────────────────────────────────────────

export function SystemDiagnosticsPage() {
  const { t } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('system_diagnostics_page.title')}
      subtitle={t('system_diagnostics_page.subtitle')}
    >
      <FormLayout sections={SECTIONS}>

        {/* 1. Log Viewer */}
        <section id="log-viewer" data-testid="settings.system-diagnostics.section-log-viewer">
          <div data-testid="section-log-viewer">
            <SettingsSection
              title={t('system_diagnostics_page.log_viewer_section')}
              description={t('system_diagnostics_page.log_viewer_desc')}
              icon={<FileText size={16} style={{ color: 'var(--accent)' }} />}
            >
              <div data-testid="log-viewer-content">
                <Suspense fallback={<SectionSkeleton />}>
                  <ProtokollTab />
                </Suspense>
              </div>
            </SettingsSection>
          </div>
        </section>

        {/* 2. Disk Monitoring */}
        <section id="disk-monitoring" data-testid="settings.system-diagnostics.section-disk-monitoring">
          <div data-testid="section-disk-monitoring">
            <SettingsSection
              title={t('system_diagnostics_page.disk_monitoring_section')}
              description={t('system_tab.disk_monitoring_desc')}
              icon={<HardDrive size={16} style={{ color: 'var(--accent)' }} />}
            >
              <DiskMonitoringControls />
            </SettingsSection>
          </div>
        </section>

        {/* 3. Cache Management */}
        <section id="cache" data-testid="settings.system-diagnostics.section-cache">
          <div data-testid="section-cache-management">
            <SettingsSection
              title={t('system_diagnostics_page.cache_section')}
              description={t('system_tab.cache_management_desc')}
              icon={<Database size={16} style={{ color: 'var(--accent)' }} />}
            >
              <Suspense fallback={<SectionSkeleton />}>
                <CacheTab />
              </Suspense>
            </SettingsSection>
          </div>
        </section>

        {/* 4. Integrations (advanced — collapsed by default) */}
        <section id="integrations" data-testid="settings.system-diagnostics.section-integrations">
          <div data-testid="section-integrations">
            <SettingsSection
              title={t('system_diagnostics_page.integrations_section')}
              description={t('system_diagnostics_page.integrations_desc')}
              icon={<Puzzle size={16} style={{ color: 'var(--accent)' }} />}
              advanced={
                <Suspense fallback={<SectionSkeleton />}>
                  <IntegrationsTab />
                </Suspense>
              }
            >
              <p
                className="text-[12px] text-[var(--text-muted)] py-2"
                data-testid="integrations-summary"
              >
                {t('system_diagnostics_page.integrations_summary')}
              </p>
            </SettingsSection>
          </div>
        </section>

        {/* 5. Migration (advanced — collapsed by default) */}
        <section id="migration" data-testid="settings.system-diagnostics.section-migration">
          <div data-testid="section-migration">
            <SettingsSection
              title={t('system_diagnostics_page.migration_section')}
              description={t('system_diagnostics_page.migration_desc')}
              icon={<Database size={16} style={{ color: 'var(--accent)' }} />}
              advanced={
                <Suspense fallback={<SectionSkeleton />}>
                  <MigrationTab />
                </Suspense>
              }
            >
              <p
                className="text-[12px] text-[var(--text-muted)] py-2"
                data-testid="migration-summary"
              >
                {t('system_diagnostics_page.migration_summary')}
              </p>
            </SettingsSection>
          </div>
        </section>

      </FormLayout>
    </SettingsDetailLayout>
  )
}
