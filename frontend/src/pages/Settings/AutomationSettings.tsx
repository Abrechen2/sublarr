/**
 * AutomationSettings — Settings page for automation-related configuration.
 *
 * Five sections:
 * 1. Search & Scan          – wanted search intervals and scan settings
 * 2. Upgrade Rules          – auto-upgrade thresholds and frequency
 * 3. Webhook                – auto-trigger on Sonarr/Radarr download notifications
 * 4. Processing Pipeline    – post-download pipeline (translate, sync, cleanup)
 * 5. Scheduled Tasks (adv.) – read-only placeholder linking to Tasks page
 *
 * The per-section content components live under ./automation/ (extracted
 * during the file-size split); this file is the page shell + TOC wiring.
 */
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Search, ArrowUpCircle, Clock, Zap } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'
import { SearchScanContent, SearchScanAdvancedContent } from './automation/SearchScanSection'
import { UpgradeRulesContent, UpgradeRulesAdvancedContent } from './automation/UpgradeRulesSection'
import { WebhookContent, ScheduledTasksContent } from './automation/WebhookSection'

// Settings Template B (FormLayout). Six sections — exactly at the cap.
// post-processing + cleanup are link-tiles to dedicated sub-pages, not
// SettingsSections, but they appear in the TOC for navigation parity so
// users have a single mental map of what lives on this page.
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'search-scan',      titleKey: 'automation_page.search_scan_section',     advancedCount: 9 },
  { id: 'upgrade-rules',    titleKey: 'automation_page.upgrade_rules_section',   advancedCount: 1 },
  { id: 'webhook',          titleKey: 'automation_page.webhook_section' },
  { id: 'post-processing',  titleKey: 'post_processing_page.title' },
  { id: 'cleanup',          titleKey: 'automation_page.cleanup_section' },
  { id: 'scheduled-tasks',  titleKey: 'automation_page.scheduled_tasks_section' },
]

// ─── AutomationSettings Page ──────────────────────────────────────────────────

export function AutomationSettings() {
  const { t } = useTranslation('settings')
  const { t: tS } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('settings.categories.automation.title', 'Automation')}
      subtitle={t(
        'settings.categories.automation.description',
        'Search scheduling, upgrade rules, pipeline, and sidecar settings',
      )}
    >
      <FormLayout sections={SECTIONS}>

      {/* 1. Search & Scan */}
      <section id="search-scan" data-testid="settings.automation.section-search-scan">
      <div data-testid="section-search-scan">
        <SettingsSection
          title={t('automation_page.search_scan_section')}
          description={t(
            'settings.automation.searchScan.description',
            'Configure how often Sublarr searches for missing subtitles and scans the library.',
          )}
          icon={<Search size={16} style={{ color: 'var(--accent)' }} />}
          advanced={<SearchScanAdvancedContent />}
          advancedCount={9}
        >
          <SearchScanContent />
        </SettingsSection>
      </div>
      </section>

      {/* 2. Upgrade Rules */}
      <section id="upgrade-rules" data-testid="settings.automation.section-upgrade-rules">
      <div data-testid="section-upgrade-rules">
        <SettingsSection
          title={t('automation_page.upgrade_rules_section')}
          description={t(
            'settings.automation.upgradeRules.description',
            'Define when and how existing subtitles should be replaced with better ones.',
          )}
          icon={<ArrowUpCircle size={16} style={{ color: 'var(--accent)' }} />}
          advanced={<UpgradeRulesAdvancedContent />}
          advancedCount={1}
        >
          <UpgradeRulesContent />
        </SettingsSection>
      </div>
      </section>

      {/* 3. Webhook */}
      <section id="webhook" data-testid="settings.automation.section-webhook">
      <div data-testid="section-webhook">
        <SettingsSection
          title={tS('automation_page.webhook_section')}
          description={tS('automation_page.webhook_section_desc')}
          icon={<Zap size={16} style={{ color: 'var(--accent)' }} />}
        >
          <WebhookContent />
        </SettingsSection>
      </div>
      </section>

      {/* 4. Processing Pipeline — navigates to dedicated page */}
      <section id="post-processing" data-testid="settings.automation.section-post-processing">
      <div
        data-testid="section-processing-pipeline"
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
            {tS('post_processing_page.title')}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
            {tS('post_processing_page.subtitle')}
          </div>
        </div>
        <Link
          to="/settings/automation/post-processing"
          style={{ fontSize: '12px', color: 'var(--accent)' }}
        >
          Configure →
        </Link>
      </div>
      </section>

      {/* 5. Cleanup — navigates to dedicated cleanup page */}
      <section id="cleanup" data-testid="settings.automation.section-cleanup">
      <div
        data-testid="section-cleanup"
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
            {tS('automation_page.cleanup_section')}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
            {tS('automation_page.cleanup_section_desc')}
          </div>
        </div>
        <Link
          to="/settings/cleanup"
          style={{ fontSize: '12px', color: 'var(--accent)' }}
        >
          Configure →
        </Link>
      </div>
      </section>

      {/* 6. Scheduled Tasks (advanced — collapsed by default) */}
      <section id="scheduled-tasks" data-testid="settings.automation.section-scheduled-tasks">
      <div data-testid="section-scheduled-tasks">
        <SettingsSection
          title={t('automation_page.scheduled_tasks_section')}
          description={t(
            'settings.automation.scheduledTasks.description',
            'Overview of background tasks managed by Sublarr.',
          )}
          icon={<Clock size={16} style={{ color: 'var(--accent)' }} />}
          advanced={<ScheduledTasksContent />}
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-2"
            data-testid="scheduled-tasks-summary"
          >
            {t(
              'settings.automation.scheduledTasks.summary',
              'Background tasks such as wanted searches and upgrade checks run on configurable intervals.',
            )}
          </p>
        </SettingsSection>
      </div>
      </section>

      </FormLayout>
    </SettingsDetailLayout>
  )
}
