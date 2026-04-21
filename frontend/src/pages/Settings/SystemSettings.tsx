/**
 * SystemSettings — Settings page for system-level configuration.
 *
 * Seven sections:
 * 1. Security           – auth toggle, password change
 * 2. Backup & Restore   – full backup create/restore/download
 * 3. Events & Hooks     – redirect placeholder to Notifications settings
 * 4. Log Viewer         – log viewer and support bundle
 * 5. Integrations       (advanced — collapsed by default) – Bazarr migration, compatibility, diagnostics, export
 * 6. Migration          (advanced — collapsed by default) – Bazarr DB import wizard
 * 7. API Keys           (advanced — collapsed by default) – API key management
 */
import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Shield, Archive, Webhook, FileText, Puzzle, Database, Key, HardDrive, Download } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { numVal, boolVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

// ─── Lazy sub-tabs ───────────────────────────────────────────────────────────

const SecurityTab = lazy(() =>
  import('./SecurityTab').then((m) => ({ default: m.SecurityTab })),
)
const BackupTab = lazy(() =>
  import('./AdvancedTab').then((m) => ({ default: m.BackupTab })),
)
const ProtokollTab = lazy(() =>
  import('./ProtokollTab').then((m) => ({ default: m.ProtokollTab })),
)
const IntegrationsTab = lazy(() =>
  import('./IntegrationsTab').then((m) => ({ default: m.IntegrationsTab })),
)
const MigrationTab = lazy(() =>
  import('./MigrationTab').then((m) => ({ default: m.MigrationTab })),
)
const ApiKeysTab = lazy(() =>
  import('./ApiKeysTab').then((m) => ({ default: m.ApiKeysTab })),
)
const ConfigExportImportTab = lazy(() =>
  import('./ConfigExportImportTab').then((m) => ({ default: m.ConfigExportImportTab })),
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

// ─── Auto Backup Controls (Step 40) ──────────────────────────────────────────

function AutoBackupControls() {
  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const { mutate: save, isPending } = useUpdateConfig()

  return (
    <div data-testid="backup-auto-controls" className="mb-4">
      <FormGroup
        label={t('system_tab.auto_backup')}
        hint={t('system_tab.auto_backup_hint')}
        data-testid="form-group-backup-auto-enabled"
      >
        <Toggle
          checked={boolVal(config, 'backup_auto_enabled', false)}
          onChange={(v) => save({ backup_auto_enabled: String(v) })}
          disabled={isPending}
          data-testid="toggle-backup-auto-enabled"
        />
      </FormGroup>

      <FormGroup
        label={t('system_tab.backup_interval')}
        hint={t('system_tab.backup_interval_hint')}
        htmlFor="backup-auto-interval-hours"
        data-testid="form-group-backup-auto-interval-hours"
      >
        <input
          id="backup-auto-interval-hours"
          type="number"
          data-testid="input-backup-auto-interval-hours"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={numVal(config, 'backup_auto_interval_hours', 24)}
          onChange={(e) => save({ backup_auto_interval_hours: Number(e.target.value) })}
          disabled={isPending}
          min={1}
          max={720}
        />
      </FormGroup>

      <FormGroup
        label={t('system_tab.backup_on_startup')}
        hint={t('system_tab.backup_on_startup_hint')}
        data-testid="form-group-backup-auto-on-startup"
      >
        <Toggle
          checked={boolVal(config, 'backup_auto_on_startup', false)}
          onChange={(v) => save({ backup_auto_on_startup: String(v) })}
          disabled={isPending}
          data-testid="toggle-backup-auto-on-startup"
        />
      </FormGroup>

      <FormGroup
        label={t('system_tab.notify_on_failure')}
        hint={t('system_tab.notify_on_failure_hint')}
        data-testid="form-group-backup-notify-on-failure"
      >
        <Toggle
          checked={boolVal(config, 'backup_notify_on_failure', true)}
          onChange={(v) => save({ backup_notify_on_failure: String(v) })}
          disabled={isPending}
          data-testid="toggle-backup-notify-on-failure"
        />
      </FormGroup>
    </div>
  )
}

// ─── Disk Monitoring Controls (Step 41) ──────────────────────────────────────

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

// ─── SystemSettings Page ──────────────────────────────────────────────────────

export function SystemSettings() {
  const { t } = useTranslation('settings')
  const { t: tSettings } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('settings.categories.system.title', 'System')}
      subtitle={t(
        'settings.categories.system.description',
        'Security, backups, logs, and advanced system configuration',
      )}
    >
      {/* 1. Security */}
      <div data-testid="section-security">
        <SettingsSection
          title={t('settings.system.security.title', 'Security')}
          description={t(
            'settings.system.security.description',
            'Authentication settings and password management.',
          )}
          icon={<Shield size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="security-content">
            <Suspense fallback={<SectionSkeleton />}>
              <SecurityTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>

      {/* 2. Backup & Restore */}
      <div data-testid="section-backup-restore">
        <SettingsSection
          title={t('settings.system.backupRestore.title', 'Backup & Restore')}
          description={t(
            'settings.system.backupRestore.description',
            'Create, download, and restore full application backups.',
          )}
          icon={<Archive size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="backup-restore-content">
            <AutoBackupControls />
            <Suspense fallback={<SectionSkeleton />}>
              <BackupTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>

      {/* 3. Events & Hooks */}
      <div data-testid="section-events-hooks">
        <SettingsSection
          title={t('settings.system.eventsHooks.title', 'Events & Hooks')}
          description={t(
            'settings.system.eventsHooks.description',
            'Webhook triggers and notification events.',
          )}
          icon={<Webhook size={16} style={{ color: 'var(--accent)' }} />}
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-3"
            data-testid="events-hooks-redirect"
          >
            {t(
              'settings.system.eventsHooks.redirect',
              'Events and hooks are configured in the',
            )}{' '}
            <Link
              to="/settings/notifications"
              className="text-[var(--accent)] hover:underline"
              data-testid="events-hooks-link"
            >
              {t('settings.system.eventsHooks.notificationsLink', 'Notifications settings')}
            </Link>
            {'.'}
          </p>
        </SettingsSection>
      </div>

      {/* 4. Log Viewer */}
      <div data-testid="section-log-viewer">
        <SettingsSection
          title={t('settings.system.logViewer.title', 'Log Viewer')}
          description={t(
            'settings.system.logViewer.description',
            'View application logs and download support bundles.',
          )}
          icon={<FileText size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="log-viewer-content">
            <Suspense fallback={<SectionSkeleton />}>
              <ProtokollTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>

      {/* 5. Integrations (advanced — collapsed by default) */}
      <div data-testid="section-integrations">
        <SettingsSection
          title={t('settings.system.integrations.title', 'Integrations')}
          description={t(
            'settings.system.integrations.description',
            'Bazarr migration, compatibility checks, diagnostics, and data export.',
          )}
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
            {t(
              'settings.system.integrations.summary',
              'Advanced integration tools including Bazarr compatibility checks, diagnostics, and export utilities.',
            )}
          </p>
        </SettingsSection>
      </div>

      {/* 6. Migration (advanced — collapsed by default) */}
      <div data-testid="section-migration">
        <SettingsSection
          title={t('settings.system.migration.title', 'Migration')}
          description={t(
            'settings.system.migration.description',
            'Import data from Bazarr and other subtitle managers.',
          )}
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
            {t(
              'settings.system.migration.summary',
              'Migrate your existing subtitle database and settings from Bazarr or other compatible managers.',
            )}
          </p>
        </SettingsSection>
      </div>

      {/* 7. API Keys (advanced — collapsed by default) */}
      <div data-testid="section-api-keys">
        <SettingsSection
          title={t('settings.system.apiKeys.title', 'API Keys')}
          description={t(
            'settings.system.apiKeys.description',
            'Manage API keys for external access to the Sublarr API.',
          )}
          icon={<Key size={16} style={{ color: 'var(--accent)' }} />}
          advanced={
            <Suspense fallback={<SectionSkeleton />}>
              <ApiKeysTab includeOnly={['sublarr']} />
            </Suspense>
          }
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-2"
            data-testid="api-keys-summary"
          >
            {t(
              'settings.system.apiKeys.summary',
              'Create and revoke API keys used by external tools and scripts to access the Sublarr API.',
            )}
          </p>
        </SettingsSection>
      </div>
      {/* 8. AniDB — navigates to dedicated page */}
      <div
        data-testid="section-anidb"
        style={{
          padding: '14px 18px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {tSettings('metadata_page.title')}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
            {tSettings('metadata_page.subtitle')}
          </div>
        </div>
        <Link
          to="/settings/connections/metadata"
          style={{ fontSize: '12px', color: 'var(--accent)' }}
        >
          Configure →
        </Link>
      </div>

      {/* 9. Remux — navigates to dedicated page */}
      <div
        data-testid="section-remux"
        style={{
          padding: '14px 18px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {tSettings('stream_management_page.title')}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
            {tSettings('stream_management_page.subtitle')}
          </div>
        </div>
        <Link
          to="/settings/subtitles/stream-management"
          style={{ fontSize: '12px', color: 'var(--accent)' }}
        >
          Configure →
        </Link>
      </div>

      {/* 10. Disk Monitoring (Step 41) */}
      <div data-testid="section-disk-monitoring">
        <SettingsSection
          title={tSettings('system_tab.disk_monitoring_title')}
          description={tSettings('system_tab.disk_monitoring_desc')}
          icon={<HardDrive size={16} style={{ color: 'var(--accent)' }} />}
        >
          <DiskMonitoringControls />
        </SettingsSection>
      </div>

      {/* 12. Cache Management */}
      <div data-testid="section-cache-management">
        <SettingsSection
          title={tSettings('system_tab.cache_management_title')}
          description={tSettings('system_tab.cache_management_desc')}
          icon={<Database size={16} style={{ color: 'var(--accent)' }} />}
        >
          <Suspense fallback={<SectionSkeleton />}>
            <CacheTab />
          </Suspense>
        </SettingsSection>
      </div>

      {/* 13. Settings Export / Import */}
      <div data-testid="section-config-export-import">
        <SettingsSection
          title={t('settings.system.configExportImport.title', 'Settings Export / Import')}
          description={t(
            'settings.system.configExportImport.description',
            'Export all settings as JSON or import from a backup file.',
          )}
          icon={<Download size={16} style={{ color: 'var(--accent)' }} />}
        >
          <Suspense fallback={<SectionSkeleton />}>
            <ConfigExportImportTab />
          </Suspense>
        </SettingsSection>
      </div>
    </SettingsDetailLayout>
  )
}
