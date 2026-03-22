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
import { useTranslation } from 'react-i18next'
import { Search, ArrowUpCircle, Workflow, Clock, Zap } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'

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
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '6px',
  padding: '7px 12px',
  fontSize: '13px',
  fontFamily: 'var(--font-body)',
  width: '220px',
  outline: 'none',
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
        Bibliotheks-Scan
      </p>

      <FormGroup
        label="Scan-Intervall (Stunden)"
        hint="Wie oft (in Stunden) Sublarr die Bibliothek auf neue Dateien scannt. 0 = nur event-gesteuert."
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
        label="Scan beim Start"
        hint="Bibliothek beim Start von Sublarr automatisch scannen."
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
        Untertitel-Suche
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
        label="Max Items per Run"
        hint="Maximum number of wanted items processed in a single search run."
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
        label="Max Search Attempts"
        hint="How many times Sublarr retries a failed subtitle search before giving up."
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
        label="Auto-Extract Embedded"
        hint="Automatically extract embedded subtitles during wanted scans."
        data-testid="form-group-wanted-auto-extract"
      >
        <Toggle
          checked={boolVal(config, 'wanted_auto_extract', false)}
          onChange={(v) => save({ wanted_auto_extract: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Anime Series Only"
        hint="Only search subtitles for anime series (skip live-action)."
        data-testid="form-group-wanted-anime-only"
      >
        <Toggle
          checked={boolVal(config, 'wanted_anime_only', false)}
          onChange={(v) => save({ wanted_anime_only: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Anime Movies Only"
        hint="Only search subtitles for anime movies."
        data-testid="form-group-wanted-anime-movies-only"
      >
        <Toggle
          checked={boolVal(config, 'wanted_anime_movies_only', false)}
          onChange={(v) => save({ wanted_anime_movies_only: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Skip SRT When No ASS Found"
        hint="Skip SRT subtitle downloads if no ASS subtitle was found for the episode."
        data-testid="form-group-wanted-skip-srt-on-no-ass"
      >
        <Toggle
          checked={boolVal(config, 'wanted_skip_srt_on_no_ass', false)}
          onChange={(v) => save({ wanted_skip_srt_on_no_ass: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Adaptive Backoff"
        hint="Increase retry delay exponentially for items that repeatedly fail."
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
            label="Backoff Base (hours)"
            hint="Initial retry delay in hours when backoff is active."
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
            label="Backoff Cap (hours)"
            hint="Maximum retry delay in hours. Delay will not exceed this value."
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
        label="Upgrade Window (days)"
        hint="Only upgrade subtitles downloaded within this many days."
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
        label="Prefer ASS over SRT"
        hint="Always upgrade from SRT to ASS format when a better ASS subtitle is available."
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
        data-testid="form-group-wanted-auto-translate"
      >
        <Toggle
          checked={boolVal(config, 'wanted_auto_translate', false)}
          onChange={(v) => save({ wanted_auto_translate: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.pipeline.autoSync', 'Auto-Sync')}
        hint={t(
          'settings.automation.pipeline.autoSyncHint',
          'Automatically synchronise subtitles to video timing after download.',
        )}
        data-testid="form-group-auto-sync-after-download"
      >
        <Toggle
          checked={boolVal(config, 'auto_sync_after_download', false)}
          onChange={(v) => save({ auto_sync_after_download: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.pipeline.autoCleanup', 'Auto-Cleanup')}
        hint={t(
          'settings.automation.pipeline.autoCleanupHint',
          'Remove duplicate and redundant subtitle files automatically after extract.',
        )}
        data-testid="form-group-auto-cleanup-after-extract"
      >
        <Toggle
          checked={boolVal(config, 'auto_cleanup_after_extract', false)}
          onChange={(v) => save({ auto_cleanup_after_extract: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Auto Common Fixes"
        hint="Apply common subtitle formatting fixes automatically after download."
        data-testid="form-group-auto-process-common-fixes"
      >
        <Toggle
          checked={boolVal(config, 'auto_process_common_fixes', false)}
          onChange={(v) => save({ auto_process_common_fixes: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Auto HI Removal"
        hint="Remove hearing-impaired tags from subtitles automatically after download."
        data-testid="form-group-auto-process-hi-removal"
      >
        <Toggle
          checked={boolVal(config, 'auto_process_hi_removal', false)}
          onChange={(v) => save({ auto_process_hi_removal: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Auto Credit Removal"
        hint="Remove credit lines (translator notes, group ads) from subtitles automatically."
        data-testid="form-group-auto-process-credit-removal"
      >
        <Toggle
          checked={boolVal(config, 'auto_process_credit_removal', false)}
          onChange={(v) => save({ auto_process_credit_removal: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Auto-Sync Score Threshold"
        hint="Minimum subtitle score required to trigger auto-sync after download."
        htmlFor="auto-process-sync-threshold"
        data-testid="form-group-auto-process-sync-threshold"
      >
        <input
          id="auto-process-sync-threshold"
          type="number"
          data-testid="input-auto-process-sync-threshold"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'auto_process_sync_threshold', '80')}
          onChange={(e) => save({ auto_process_sync_threshold: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          max={100}
          placeholder="80"
        />
      </FormGroup>

      <FormGroup
        label="Sync Fallback Engine"
        hint="Synchronisation engine used when the primary sync attempt fails. ffsubsync is audio-based; alass is AI-based."
        htmlFor="auto-process-sync-fallback-engine"
        data-testid="form-group-auto-process-sync-fallback-engine"
      >
        <select
          id="auto-process-sync-fallback-engine"
          data-testid="select-auto-process-sync-fallback-engine"
          style={{
            ...inputStyle,
            maxWidth: '160px',
            cursor: 'pointer',
          }}
          value={strVal(config, 'auto_process_sync_fallback_engine', 'ffsubsync')}
          onChange={(e) => save({ auto_process_sync_fallback_engine: e.target.value })}
          disabled={updateConfig.isPending}
        >
          <option value="ffsubsync">ffsubsync</option>
          <option value="alass">alass</option>
        </select>
      </FormGroup>

      <FormGroup
        label="Export NFO Sidecar"
        hint="Write an NFO metadata sidecar file alongside each downloaded subtitle."
        data-testid="form-group-auto-nfo-export"
      >
        <Toggle
          checked={boolVal(config, 'auto_nfo_export', false)}
          onChange={(v) => save({ auto_nfo_export: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Translate on Jellyfin Playback"
        hint="Automatically translate subtitles when Jellyfin starts playback of a new episode."
        data-testid="form-group-jellyfin-play-translate-enabled"
      >
        <Toggle
          checked={boolVal(config, 'jellyfin_play_translate_enabled', false)}
          onChange={(v) => save({ jellyfin_play_translate_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Streaming aktiviert"
        hint="Subtitle-Streaming-Modus aktivieren (experimentell). Erlaubt Live-Übertragung von Untertiteln an kompatible Player."
        data-testid="form-group-streaming-enabled"
      >
        <Toggle
          checked={boolVal(config, 'streaming_enabled', false)}
          onChange={(v) => save({ streaming_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>
    </div>
  )
}

// ─── Webhook Section ──────────────────────────────────────────────────────────

function WebhookContent() {
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="webhook-content">
      <FormGroup
        label="Webhook Delay (minutes)"
        hint="Wait this many minutes after a Sonarr/Radarr webhook before searching. Allows time for the file to appear."
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
        label="Auto-Scan on Webhook"
        hint="Trigger a library scan automatically when a Sonarr/Radarr webhook is received."
        data-testid="form-group-webhook-auto-scan"
      >
        <Toggle
          checked={boolVal(config, 'webhook_auto_scan', false)}
          onChange={(v) => save({ webhook_auto_scan: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Auto-Search on Webhook"
        hint="Trigger a subtitle search automatically when a download webhook is received."
        data-testid="form-group-webhook-auto-search"
      >
        <Toggle
          checked={boolVal(config, 'webhook_auto_search', true)}
          onChange={(v) => save({ webhook_auto_search: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Auto-Translate on Webhook"
        hint="Automatically translate subtitles found via a webhook-triggered search."
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
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="cleanup-content">
      <FormGroup
        label="Keep Languages"
        hint="Comma-separated language codes to keep when cleaning up duplicates (e.g. de,en)."
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
        label="Keep Formats"
        hint="Comma-separated subtitle formats to keep during cleanup (e.g. ass,srt)."
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
        label="Trash Retention (days)"
        hint="Keep deleted subtitles in trash for this many days before permanent removal."
        htmlFor="subtitle-trash-retention-days"
        data-testid="form-group-subtitle-trash-retention-days"
      >
        <input
          id="subtitle-trash-retention-days"
          type="number"
          data-testid="input-subtitle-trash-retention-days"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'subtitle_trash_retention_days', '7')}
          onChange={(e) => save({ subtitle_trash_retention_days: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          placeholder="7"
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

      {/* 3. Webhook */}
      <div data-testid="section-webhook">
        <SettingsSection
          title="Webhook"
          description="Control what happens automatically when Sonarr/Radarr sends a download notification."
          icon={<Zap size={16} style={{ color: 'var(--accent)' }} />}
        >
          <WebhookContent />
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

      {/* 5. Cleanup */}
      <div data-testid="section-cleanup">
        <SettingsSection
          title="Subtitle Cleanup"
          description="Control which subtitles are kept during cleanup and how long deleted files are retained."
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
