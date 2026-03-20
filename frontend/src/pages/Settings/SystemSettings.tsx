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
import { Shield, Archive, Webhook, FileText, Puzzle, Database, Key } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'

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

// ─── SystemSettings Page ──────────────────────────────────────────────────────

export function SystemSettings() {
  const { t } = useTranslation('common')

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
              <ApiKeysTab />
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
    </SettingsDetailLayout>
  )
}
