/**
 * AutomationSettings — Settings page for automation-related configuration.
 *
 * Six sections:
 * 1. Search & Scan          – wanted search intervals and scan settings
 * 2. Upgrade Rules          – auto-upgrade thresholds and frequency
 * 3. Provider Re-ranking    – wraps ScoringTab (lazy) for scoring weights/modifiers
 * 4. Processing Pipeline    – post-download pipeline (translate, sync, cleanup)
 * 5. Sidecar & Cleanup      – sidecar file handling
 * 6. Scheduled Tasks (adv.) – read-only placeholder linking to Tasks page
 */
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, ArrowUpCircle, BarChart3, Workflow, FileX, Clock } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'

// ─── Lazy sub-tabs ───────────────────────────────────────────────────────────

const ScoringTab = lazy(() =>
  import('./EventsTab').then((m) => ({ default: m.ScoringTab })),
)

// ─── Config value helpers ─────────────────────────────────────────────────────

function strVal(config: unknown, key: string, fallback = ''): string {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  return v !== undefined && v !== null ? String(v) : fallback
}

function boolVal(config: unknown, key: string, fallback = false): boolean {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  if (v === undefined || v === null) return fallback
  return v === true || v === 'true' || v === 1
}

// ─── Shared input style ───────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: 'var(--bg-primary)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '6px',
  padding: '6px 10px',
  fontSize: '13px',
  width: '100%',
  minWidth: 0,
}

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
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="search-scan-content">
      <FormGroup
        label={t('settings.automation.searchScan.frequency', 'Wanted Search Frequency (min)')}
        hint={t(
          'settings.automation.searchScan.frequencyHint',
          'How often (in minutes) Sublarr searches for missing subtitles.',
        )}
        htmlFor="wanted-search-frequency"
        data-testid="form-group-wanted-search-frequency"
      >
        <input
          id="wanted-search-frequency"
          type="number"
          data-testid="input-wanted-search-frequency"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'wanted_search_frequency', '60')}
          onChange={(e) => save({ wanted_search_frequency: e.target.value })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="60"
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.searchScan.autoSearchOnDownload', 'Auto-Search on Download')}
        hint={t(
          'settings.automation.searchScan.autoSearchOnDownloadHint',
          'Automatically trigger a subtitle search after a new download is detected.',
        )}
        data-testid="form-group-auto-search-on-download"
      >
        <Toggle
          checked={boolVal(config, 'auto_search_on_download', true)}
          onChange={(v) => save({ auto_search_on_download: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.searchScan.scanOnStart', 'Scan on Start')}
        hint={t(
          'settings.automation.searchScan.scanOnStartHint',
          'Run a full library scan every time Sublarr starts.',
        )}
        data-testid="form-group-scan-on-start"
      >
        <Toggle
          checked={boolVal(config, 'scan_on_start', false)}
          onChange={(v) => save({ scan_on_start: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>
    </div>
  )
}

// ─── Upgrade Rules Section ────────────────────────────────────────────────────

function UpgradeRulesContent() {
  const { t } = useTranslation('common')
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
        data-testid="form-group-auto-upgrade-enabled"
      >
        <Toggle
          checked={boolVal(config, 'auto_upgrade_enabled', false)}
          onChange={(v) => save({ auto_upgrade_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.upgradeRules.threshold', 'Upgrade Score Threshold')}
        hint={t(
          'settings.automation.upgradeRules.thresholdHint',
          'Minimum score improvement required before replacing an existing subtitle.',
        )}
        htmlFor="auto-upgrade-threshold"
        data-testid="form-group-auto-upgrade-threshold"
      >
        <input
          id="auto-upgrade-threshold"
          type="number"
          data-testid="input-auto-upgrade-threshold"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'auto_upgrade_threshold', '10')}
          onChange={(e) => save({ auto_upgrade_threshold: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          placeholder="10"
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.upgradeRules.checkFrequency', 'Upgrade Check Frequency (min)')}
        hint={t(
          'settings.automation.upgradeRules.checkFrequencyHint',
          'How often (in minutes) existing subtitles are checked for upgrade candidates.',
        )}
        htmlFor="upgrade-check-frequency"
        data-testid="form-group-upgrade-check-frequency"
      >
        <input
          id="upgrade-check-frequency"
          type="number"
          data-testid="input-upgrade-check-frequency"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'upgrade_check_frequency', '360')}
          onChange={(e) => save({ upgrade_check_frequency: e.target.value })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="360"
        />
      </FormGroup>
    </div>
  )
}

// ─── Processing Pipeline Section ──────────────────────────────────────────────

function ProcessingPipelineContent() {
  const { t } = useTranslation('common')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="processing-pipeline-content">
      <FormGroup
        label={t('settings.automation.pipeline.autoTranslate', 'Auto-Translate')}
        hint={t(
          'settings.automation.pipeline.autoTranslateHint',
          'Automatically translate downloaded subtitles to the target language.',
        )}
        data-testid="form-group-auto-translate"
      >
        <Toggle
          checked={boolVal(config, 'auto_translate', false)}
          onChange={(v) => save({ auto_translate: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.pipeline.autoSync', 'Auto-Sync')}
        hint={t(
          'settings.automation.pipeline.autoSyncHint',
          'Automatically synchronise subtitles to video timing after download.',
        )}
        data-testid="form-group-auto-sync"
      >
        <Toggle
          checked={boolVal(config, 'auto_sync', false)}
          onChange={(v) => save({ auto_sync: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.pipeline.autoCleanup', 'Auto-Cleanup')}
        hint={t(
          'settings.automation.pipeline.autoCleanupHint',
          'Remove duplicate and redundant subtitle files automatically after processing.',
        )}
        data-testid="form-group-auto-cleanup"
      >
        <Toggle
          checked={boolVal(config, 'auto_cleanup', false)}
          onChange={(v) => save({ auto_cleanup: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>
    </div>
  )
}

// ─── Sidecar & Cleanup Section ────────────────────────────────────────────────

function SidecarCleanupContent() {
  const { t } = useTranslation('common')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="sidecar-cleanup-content">
      <FormGroup
        label={t('settings.automation.sidecar.keepOriginal', 'Keep Original Subtitles')}
        hint={t(
          'settings.automation.sidecar.keepOriginalHint',
          'Preserve the original subtitle file alongside the processed one.',
        )}
        data-testid="form-group-keep-original-subs"
      >
        <Toggle
          checked={boolVal(config, 'keep_original_subs', true)}
          onChange={(v) => save({ keep_original_subs: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.sidecar.format', 'Sidecar Format')}
        hint={t(
          'settings.automation.sidecar.formatHint',
          'File format used for sidecar subtitle files (e.g. srt, ass).',
        )}
        htmlFor="sidecar-format"
        data-testid="form-group-sidecar-format"
      >
        <input
          id="sidecar-format"
          type="text"
          data-testid="input-sidecar-format"
          style={{ ...inputStyle, maxWidth: '160px' }}
          value={strVal(config, 'sidecar_format', 'srt')}
          onChange={(e) => save({ sidecar_format: e.target.value })}
          disabled={updateConfig.isPending}
          placeholder="srt"
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

      {/* 3. Provider Re-ranking */}
      <div data-testid="section-provider-reranking">
        <SettingsSection
          title={t('settings.automation.providerReranking.title', 'Provider Re-ranking')}
          description={t(
            'settings.automation.providerReranking.description',
            'Tune scoring weights and per-provider modifiers used to rank subtitle results.',
          )}
          icon={<BarChart3 size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="provider-reranking-content">
            <Suspense fallback={<SectionSkeleton />}>
              <ScoringTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>

      {/* 4. Processing Pipeline */}
      <div data-testid="section-processing-pipeline">
        <SettingsSection
          title={t('settings.automation.pipeline.title', 'Processing Pipeline')}
          description={t(
            'settings.automation.pipeline.description',
            'Control post-download processing: translation, synchronisation, and cleanup.',
          )}
          icon={<Workflow size={16} style={{ color: 'var(--accent)' }} />}
        >
          <ProcessingPipelineContent />
        </SettingsSection>
      </div>

      {/* 5. Sidecar & Cleanup */}
      <div data-testid="section-sidecar-cleanup">
        <SettingsSection
          title={t('settings.automation.sidecar.title', 'Sidecar & Cleanup')}
          description={t(
            'settings.automation.sidecar.description',
            'Configure how sidecar subtitle files are stored and which originals are kept.',
          )}
          icon={<FileX size={16} style={{ color: 'var(--accent)' }} />}
        >
          <SidecarCleanupContent />
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
