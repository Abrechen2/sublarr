/**
 * AutomationSettings — Settings page for automation-related configuration.
 *
 * Five sections:
 * 1. Search & Scan          – wanted search intervals and scan settings
 * 2. Upgrade Rules          – auto-upgrade thresholds and frequency
 * 3. Webhook                – auto-trigger on Sonarr/Radarr download notifications
 * 4. Processing Pipeline    – post-download pipeline (translate, sync, cleanup)
 * 5. Scheduled Tasks (adv.) – read-only placeholder linking to Tasks page
 */
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Search, ArrowUpCircle, Workflow, Clock, Zap } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal, boolVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

const inputStyle: React.CSSProperties = { ...settingsInputStyle, width: '220px', outline: 'none' }

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

// ─── Search & Scan Section ────────────────────────────────────────────────────

function SearchScanContent() {
  const { t } = useTranslation('common')
  const { t: tS } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="search-scan-content">
      {/* ─── Bibliotheks-Scan sub-group ─── */}
      <p
        data-testid="search-scan-subheading-scan"
        style={{
          fontSize: '11px',
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: 'var(--text-muted)',
          margin: '4px 0 10px',
        }}
      >
        {tS('automation_page.subheading_library_scan')}
      </p>

      <FormGroup
        label={tS('automation_page.scan_interval')}
        hint={tS('automation_page.scan_interval_hint')}
        htmlFor="wanted-scan-interval-hours"
        data-testid="form-group-wanted-scan-interval-hours"
      >
        <input
          id="wanted-scan-interval-hours"
          type="number"
          data-testid="input-wanted-scan-interval-hours"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'wanted_scan_interval_hours', '0')}
          onChange={(e) => save({ wanted_scan_interval_hours: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          placeholder="0"
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.scan_on_startup')}
        hint={tS('automation_page.scan_on_startup_hint')}
        data-testid="form-group-wanted-scan-on-startup"
      >
        <Toggle
          checked={boolVal(config, 'wanted_scan_on_startup', false)}
          onChange={(v) => save({ wanted_scan_on_startup: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      {/* ─── Untertitel-Suche sub-group ─── */}
      <p
        data-testid="search-scan-subheading-search"
        style={{
          fontSize: '11px',
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: 'var(--text-muted)',
          margin: '16px 0 10px',
        }}
      >
        {tS('automation_page.subheading_subtitle_search')}
      </p>

      <FormGroup
        label={t('settings.automation.searchScan.interval', 'Wanted Search Interval (hours)')}
        hint={t(
          'settings.automation.searchScan.intervalHint',
          'How often (in hours) Sublarr searches for missing subtitles.',
        )}
        htmlFor="wanted-search-interval-hours"
        data-testid="form-group-wanted-search-interval-hours"
      >
        <input
          id="wanted-search-interval-hours"
          type="number"
          data-testid="input-wanted-search-interval-hours"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'wanted_search_interval_hours', '6')}
          onChange={(e) => save({ wanted_search_interval_hours: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="6"
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.searchScan.searchOnStartup', 'Search on Startup')}
        hint={t(
          'settings.automation.searchScan.searchOnStartupHint',
          'Run a wanted search every time Sublarr starts.',
        )}
        data-testid="form-group-wanted-search-on-startup"
      >
        <Toggle
          checked={boolVal(config, 'wanted_search_on_startup', false)}
          onChange={(v) => save({ wanted_search_on_startup: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.max_items_per_run')}
        hint={tS('automation_page.max_items_per_run_hint')}
        htmlFor="wanted-search-max-items-per-run"
        data-testid="form-group-wanted-search-max-items-per-run"
      >
        <input
          id="wanted-search-max-items-per-run"
          type="number"
          data-testid="input-wanted-search-max-items-per-run"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'wanted_search_max_items_per_run', '50')}
          onChange={(e) => save({ wanted_search_max_items_per_run: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="50"
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.max_search_attempts')}
        hint={tS('automation_page.max_search_attempts_hint')}
        htmlFor="wanted-max-search-attempts"
        data-testid="form-group-wanted-max-search-attempts"
      >
        <input
          id="wanted-max-search-attempts"
          type="number"
          data-testid="input-wanted-max-search-attempts"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'wanted_max_search_attempts', '3')}
          onChange={(e) => save({ wanted_max_search_attempts: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="3"
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.auto_extract')}
        hint={tS('automation_page.auto_extract_hint')}
        data-testid="form-group-wanted-auto-extract"
      >
        <Toggle
          checked={boolVal(config, 'wanted_auto_extract', false)}
          onChange={(v) => save({ wanted_auto_extract: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.anime_series_only')}
        hint={tS('automation_page.anime_series_only_hint')}
        data-testid="form-group-wanted-anime-only"
      >
        <Toggle
          checked={boolVal(config, 'wanted_anime_only', false)}
          onChange={(v) => save({ wanted_anime_only: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.anime_movies_only')}
        hint={tS('automation_page.anime_movies_only_hint')}
        data-testid="form-group-wanted-anime-movies-only"
      >
        <Toggle
          checked={boolVal(config, 'wanted_anime_movies_only', false)}
          onChange={(v) => save({ wanted_anime_movies_only: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.skip_srt_no_ass')}
        hint={tS('automation_page.skip_srt_no_ass_hint')}
        data-testid="form-group-wanted-skip-srt-on-no-ass"
      >
        <Toggle
          checked={boolVal(config, 'wanted_skip_srt_on_no_ass', false)}
          onChange={(v) => save({ wanted_skip_srt_on_no_ass: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.adaptive_backoff')}
        hint={tS('automation_page.adaptive_backoff_hint')}
        data-testid="form-group-wanted-adaptive-backoff-enabled"
      >
        <Toggle
          checked={boolVal(config, 'wanted_adaptive_backoff_enabled', false)}
          onChange={(v) => save({ wanted_adaptive_backoff_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      {boolVal(config, 'wanted_adaptive_backoff_enabled', false) && (
        <>
          <FormGroup
            label={tS('automation_page.backoff_base')}
            hint={tS('automation_page.backoff_base_hint')}
            htmlFor="wanted-backoff-base-hours"
            data-testid="form-group-wanted-backoff-base-hours"
          >
            <input
              id="wanted-backoff-base-hours"
              type="number"
              data-testid="input-wanted-backoff-base-hours"
              style={{ ...inputStyle, maxWidth: '120px' }}
              value={strVal(config, 'wanted_backoff_base_hours', '1')}
              onChange={(e) => save({ wanted_backoff_base_hours: Number(e.target.value) })}
              disabled={updateConfig.isPending}
              min={1}
              placeholder="1"
            />
          </FormGroup>

          <FormGroup
            label={tS('automation_page.backoff_cap')}
            hint={tS('automation_page.backoff_cap_hint')}
            htmlFor="wanted-backoff-cap-hours"
            data-testid="form-group-wanted-backoff-cap-hours"
          >
            <input
              id="wanted-backoff-cap-hours"
              type="number"
              data-testid="input-wanted-backoff-cap-hours"
              style={{ ...inputStyle, maxWidth: '120px' }}
              value={strVal(config, 'wanted_backoff_cap_hours', '24')}
              onChange={(e) => save({ wanted_backoff_cap_hours: Number(e.target.value) })}
              disabled={updateConfig.isPending}
              min={1}
              placeholder="24"
            />
          </FormGroup>
        </>
      )}
    </div>
  )
}

// ─── Upgrade Rules Section ────────────────────────────────────────────────────

function UpgradeRulesContent() {
  const { t } = useTranslation('common')
  const { t: tS } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="upgrade-rules-content">
      <FormGroup
        label={t('settings.automation.upgradeRules.enabled', 'Auto-Upgrade Enabled')}
        hint={t(
          'settings.automation.upgradeRules.enabledHint',
          'Automatically replace existing subtitles when a higher-scoring one is found.',
        )}
        data-testid="form-group-upgrade-enabled"
      >
        <Toggle
          checked={boolVal(config, 'upgrade_enabled', false)}
          onChange={(v) => save({ upgrade_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.upgradeRules.threshold', 'Minimum Score Delta')}
        hint={t(
          'settings.automation.upgradeRules.thresholdHint',
          'Minimum score improvement required before replacing an existing subtitle.',
        )}
        htmlFor="upgrade-min-score-delta"
        data-testid="form-group-upgrade-min-score-delta"
      >
        <input
          id="upgrade-min-score-delta"
          type="number"
          data-testid="input-upgrade-min-score-delta"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'upgrade_min_score_delta', '10')}
          onChange={(e) => save({ upgrade_min_score_delta: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          placeholder="10"
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.upgradeRules.checkInterval', 'Upgrade Scan Interval (hours)')}
        hint={t(
          'settings.automation.upgradeRules.checkIntervalHint',
          'How often (in hours) existing subtitles are checked for upgrade candidates.',
        )}
        htmlFor="upgrade-scan-interval-hours"
        data-testid="form-group-upgrade-scan-interval-hours"
      >
        <input
          id="upgrade-scan-interval-hours"
          type="number"
          data-testid="input-upgrade-scan-interval-hours"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'upgrade_scan_interval_hours', '24')}
          onChange={(e) => save({ upgrade_scan_interval_hours: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="24"
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.upgrade_window')}
        hint={tS('automation_page.upgrade_window_hint')}
        htmlFor="upgrade-window-days"
        data-testid="form-group-upgrade-window-days"
      >
        <input
          id="upgrade-window-days"
          type="number"
          data-testid="input-upgrade-window-days"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'upgrade_window_days', '30')}
          onChange={(e) => save({ upgrade_window_days: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="30"
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.prefer_ass')}
        hint={tS('automation_page.prefer_ass_hint')}
        data-testid="form-group-upgrade-prefer-ass"
      >
        <Toggle
          checked={boolVal(config, 'upgrade_prefer_ass', false)}
          onChange={(v) => save({ upgrade_prefer_ass: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>
    </div>
  )
}

// ─── Webhook Section ──────────────────────────────────────────────────────────

function WebhookContent() {
  const { t } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="webhook-content">
      <FormGroup
        label={t('automation_page.webhook_delay')}
        hint={t('automation_page.webhook_delay_hint')}
        htmlFor="webhook-delay-minutes"
        data-testid="form-group-webhook-delay-minutes"
      >
        <input
          id="webhook-delay-minutes"
          type="number"
          data-testid="input-webhook-delay-minutes"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'webhook_delay_minutes', '5')}
          onChange={(e) => save({ webhook_delay_minutes: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          placeholder="5"
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.webhook_auto_scan')}
        hint={t('automation_page.webhook_auto_scan_hint')}
        data-testid="form-group-webhook-auto-scan"
      >
        <Toggle
          checked={boolVal(config, 'webhook_auto_scan', false)}
          onChange={(v) => save({ webhook_auto_scan: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.webhook_auto_search')}
        hint={t('automation_page.webhook_auto_search_hint')}
        data-testid="form-group-webhook-auto-search"
      >
        <Toggle
          checked={boolVal(config, 'webhook_auto_search', true)}
          onChange={(v) => save({ webhook_auto_search: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.webhook_auto_translate')}
        hint={t('automation_page.webhook_auto_translate_hint')}
        data-testid="form-group-webhook-auto-translate"
      >
        <Toggle
          checked={boolVal(config, 'webhook_auto_translate', false)}
          onChange={(v) => save({ webhook_auto_translate: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>
    </div>
  )
}

// ─── Cleanup Section ──────────────────────────────────────────────────────────

function CleanupContent() {
  const { t } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="cleanup-content">
      <FormGroup
        label={t('automation_page.keep_languages')}
        hint={t('automation_page.keep_languages_hint')}
        htmlFor="auto-cleanup-keep-languages"
        data-testid="form-group-auto-cleanup-keep-languages"
      >
        <input
          id="auto-cleanup-keep-languages"
          type="text"
          data-testid="input-auto-cleanup-keep-languages"
          style={inputStyle}
          value={strVal(config, 'auto_cleanup_keep_languages', '')}
          onChange={(e) => save({ auto_cleanup_keep_languages: e.target.value })}
          disabled={updateConfig.isPending}
          placeholder="de,en"
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.keep_formats')}
        hint={t('automation_page.keep_formats_hint')}
        htmlFor="auto-cleanup-keep-formats"
        data-testid="form-group-auto-cleanup-keep-formats"
      >
        <input
          id="auto-cleanup-keep-formats"
          type="text"
          data-testid="input-auto-cleanup-keep-formats"
          style={inputStyle}
          value={strVal(config, 'auto_cleanup_keep_formats', '')}
          onChange={(e) => save({ auto_cleanup_keep_formats: e.target.value })}
          disabled={updateConfig.isPending}
          placeholder="ass,srt"
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.trash_retention')}
        hint={t('automation_page.trash_retention_hint')}
        htmlFor="subtitle-trash-retention-days"
        data-testid="form-group-subtitle-trash-retention-days"
      >
        <input
          id="subtitle-trash-retention-days"
          type="number"
          data-testid="input-subtitle-trash-retention-days"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'subtitle_trash_retention_days', '30')}
          onChange={(e) => save({ subtitle_trash_retention_days: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          placeholder="30"
        />
      </FormGroup>
    </div>
  )
}

// ─── Scheduled Tasks Section (advanced placeholder) ───────────────────────────

function ScheduledTasksContent() {
  const { t } = useTranslation('common')

  return (
    <div data-testid="scheduled-tasks-content">
      <p className="text-[12px] text-[var(--text-muted)] py-3">
        {t(
          'settings.automation.scheduledTasks.hint',
          'Scheduled task details and run history can be viewed on the Tasks page.',
        )}
      </p>
    </div>
  )
}

// ─── AutomationSettings Page ──────────────────────────────────────────────────

export function AutomationSettings() {
  const { t } = useTranslation('common')
  const { t: tS } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('settings.categories.automation.title', 'Automation')}
      subtitle={t(
        'settings.categories.automation.description',
        'Search scheduling, upgrade rules, pipeline, and sidecar settings',
      )}
    >
      {/* 1. Search & Scan */}
      <div data-testid="section-search-scan">
        <SettingsSection
          title={t('settings.automation.searchScan.title', 'Search & Scan')}
          description={t(
            'settings.automation.searchScan.description',
            'Configure how often Sublarr searches for missing subtitles and scans the library.',
          )}
          icon={<Search size={16} style={{ color: 'var(--accent)' }} />}
        >
          <SearchScanContent />
        </SettingsSection>
      </div>

      {/* 2. Upgrade Rules */}
      <div data-testid="section-upgrade-rules">
        <SettingsSection
          title={t('settings.automation.upgradeRules.title', 'Upgrade Rules')}
          description={t(
            'settings.automation.upgradeRules.description',
            'Define when and how existing subtitles should be replaced with better ones.',
          )}
          icon={<ArrowUpCircle size={16} style={{ color: 'var(--accent)' }} />}
        >
          <UpgradeRulesContent />
        </SettingsSection>
      </div>

      {/* 3. Webhook */}
      <div data-testid="section-webhook">
        <SettingsSection
          title={tS('automation_page.webhook_section')}
          description={tS('automation_page.webhook_section_desc')}
          icon={<Zap size={16} style={{ color: 'var(--accent)' }} />}
        >
          <WebhookContent />
        </SettingsSection>
      </div>

      {/* 4. Processing Pipeline — navigates to dedicated page */}
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

      {/* 5. Cleanup */}
      <div data-testid="section-cleanup">
        <SettingsSection
          title={tS('automation_page.cleanup_section')}
          description={tS('automation_page.cleanup_section_desc')}
          icon={<Workflow size={16} style={{ color: 'var(--accent)' }} />}
        >
          <CleanupContent />
        </SettingsSection>
      </div>

      {/* 6. Scheduled Tasks (advanced — collapsed by default) */}
      <div data-testid="section-scheduled-tasks">
        <SettingsSection
          title={t('settings.automation.scheduledTasks.title', 'Scheduled Tasks')}
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
    </SettingsDetailLayout>
  )
}
