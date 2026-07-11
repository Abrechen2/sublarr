/**
 * SystemSettings — main system-config page (the "setup" half of /settings/system).
 *
 * On 2026-04-26 the page was split: observability + maintenance sections
 * (Log Viewer, Disk Monitoring, Cache Management, Integrations, Migration)
 * moved to /settings/system/diagnostics — see SystemDiagnosticsPage.tsx.
 * The dead "Events & Hooks" redirect placeholder was deleted in the same
 * refactor (the actual events live on /settings/notifications).
 *
 * Four real sections + two link-tiles + one cross-link to Diagnostics:
 *
 *   1. Security                – auth toggle, password management
 *   2. Backup & Restore        – auto-backup config + manual backup ops
 *   3. API Keys (advanced)     – external-API-access keys
 *   4. Settings Export/Import  – JSON-based config export/import
 *   – AniDB / Remux            – navigation tiles to per-domain pages
 *   – Diagnostics              – cross-link to /settings/system/diagnostics
 */
import { lazy, Suspense, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { SubtitleRepairPanel } from '@/components/repair/SubtitleRepairPanel'
import {
  Shield, Archive, Key, Download, Activity, ExternalLink, Wrench,
} from 'lucide-react'
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

const SecurityTab = lazy(() =>
  import('./SecurityTab').then((m) => ({ default: m.SecurityTab })),
)
const BackupTab = lazy(() =>
  import('./AdvancedTab').then((m) => ({ default: m.BackupTab })),
)
const ApiKeysTab = lazy(() =>
  import('./ApiKeysTab').then((m) => ({ default: m.ApiKeysTab })),
)
const ConfigExportImportTab = lazy(() =>
  import('./ConfigExportImportTab').then((m) => ({ default: m.ConfigExportImportTab })),
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

// ─── Auto Backup Controls ────────────────────────────────────────────────────

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

// Settings Template B (FormLayout). Four real sections — well under the cap.
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'security',          titleKey: 'system_setup_page.security_section' },
  { id: 'backup-restore',    titleKey: 'system_setup_page.backup_restore_section' },
  { id: 'api-keys',          titleKey: 'system_setup_page.api_keys_section', advancedCount: 1 },
  { id: 'config-export',     titleKey: 'system_setup_page.config_export_section' },
  { id: 'subtitle-repair',   titleKey: 'system_setup_page.subtitle_repair_section' },
]

// ─── SystemSettings Page ──────────────────────────────────────────────────────

export function SystemSettings() {
  const { t } = useTranslation('settings')
  const { t: tSettings } = useTranslation('settings')
  const { hash } = useLocation()

  // The data-loss notice links straight here with #subtitle-repair. React Router
  // does not act on the fragment, so bring the section into view ourselves —
  // otherwise the one-click jump lands at the top of a long page.
  useEffect(() => {
    if (!hash) return
    const el = document.getElementById(hash.slice(1))
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [hash])

  return (
    <SettingsDetailLayout
      title={t('settings.categories.system.title', 'System')}
      subtitle={t(
        'settings.categories.system.description',
        'Security, backups, logs, and advanced system configuration',
      )}
    >
      <FormLayout sections={SECTIONS}>

        {/* 1. Security */}
        <section id="security" data-testid="settings.system.section-security">
          <div data-testid="section-security">
            <SettingsSection
              title={t('system_setup_page.security_section')}
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
        </section>

        {/* 2. Backup & Restore */}
        <section id="backup-restore" data-testid="settings.system.section-backup-restore">
          <div data-testid="section-backup-restore">
            <SettingsSection
              title={t('system_setup_page.backup_restore_section')}
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
        </section>

        {/* 3. API Keys (advanced — collapsed by default) */}
        <section id="api-keys" data-testid="settings.system.section-api-keys">
          <div data-testid="section-api-keys">
            <SettingsSection
              title={t('system_setup_page.api_keys_section')}
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
        </section>

        {/* 4. Settings Export / Import */}
        <section id="config-export" data-testid="settings.system.section-config-export">
          <div data-testid="section-config-export-import">
            <SettingsSection
              title={t('system_setup_page.config_export_section')}
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
        </section>


        {/* 5. Subtitle repair — restore what the pre-1.6.6 pipeline damaged */}
        <section id="subtitle-repair" data-testid="settings.system.section-subtitle-repair">
          <div data-testid="section-subtitle-repair">
            <SettingsSection
              title={t('system_setup_page.subtitle_repair_section')}
              description={t(
                'settings.system.subtitle_repair.description',
                'Restore subtitles damaged by the HI-removal bug in versions before 1.6.6.',
              )}
              icon={<Wrench size={16} style={{ color: 'var(--accent)' }} />}
            >
              <SubtitleRepairPanel />
            </SettingsSection>
          </div>
        </section>

      </FormLayout>

      {/* Cross-link to Diagnostics sub-page */}
      <div
        data-testid="section-diagnostics-link"
        style={{
          padding: '14px 18px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Activity size={16} style={{ color: 'var(--accent)' }} />
          <div>
            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {tSettings('system_diagnostics_page.title')}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
              {tSettings('system_diagnostics_page.subtitle')}
            </div>
          </div>
        </div>
        <Link
          to="/settings/system/diagnostics"
          style={{ fontSize: '12px', color: 'var(--accent)', display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          Open <ExternalLink size={11} />
        </Link>
      </div>

      {/* AniDB nav tile */}
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
          marginTop: '8px',
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

      {/* Remux nav tile */}
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
          marginTop: '8px',
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
    </SettingsDetailLayout>
  )
}
