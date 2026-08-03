/**
 * Search & Scan section for AutomationSettings — basic + advanced content.
 * Extracted from AutomationSettings.tsx during the file-size split.
 */
import { useTranslation } from 'react-i18next'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal, boolVal } from '@/lib/configUtils'
import { inputStyle, SCAN_ENGINES, SectionSkeleton } from './shared'

export function SearchScanAdvancedContent() {
  const { t } = useTranslation('common')
  const { t: tS } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()
  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="search-scan-advanced-content">
      <FormGroup
        label={t('automation_page.ffmpeg_timeout')}
        hint="Maximale Wartezeit für ffprobe/ffmpeg-Operationen beim Scannen der Mediathek."
        htmlFor="ffmpeg-timeout"
        advanced
        data-testid="form-group-ffmpeg-timeout"
      >
        <input
          id="ffmpeg-timeout"
          type="number"
          data-testid="input-ffmpeg-timeout"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'ffmpeg_timeout', '30')}
          onChange={(e) => save({ ffmpeg_timeout: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="30"
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.metadata_engine')}
        hint="Tool für das Auslesen von Mediendatei-Metadaten. 'auto' wählt automatisch."
        htmlFor="scan-metadata-engine"
        advanced
        data-testid="form-group-scan-metadata-engine"
      >
        <select
          id="scan-metadata-engine"
          data-testid="select-scan-metadata-engine"
          style={{ ...inputStyle, maxWidth: '160px' }}
          value={strVal(config, 'scan_metadata_engine', 'auto')}
          onChange={(e) => save({ scan_metadata_engine: e.target.value })}
          disabled={updateConfig.isPending}
        >
          {SCAN_ENGINES.map((e) => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>
      </FormGroup>

      <FormGroup
        label={t('automation_page.metadata_worker')}
        hint="Anzahl paralleler Threads für den Metadaten-Scan."
        htmlFor="scan-metadata-max-workers"
        advanced
        data-testid="form-group-scan-metadata-max-workers"
      >
        <input
          id="scan-metadata-max-workers"
          type="number"
          data-testid="input-scan-metadata-max-workers"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'scan_metadata_max_workers', '2')}
          onChange={(e) => save({ scan_metadata_max_workers: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={1}
          max={32}
          placeholder="2"
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.anime_series_only')}
        hint={tS('automation_page.anime_series_only_hint')}
        advanced
        htmlFor="wanted-anime-only"
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
        advanced
        htmlFor="wanted-anime-movies-only"
        data-testid="form-group-wanted-anime-movies-only"
      >
        <Toggle
          checked={boolVal(config, 'wanted_anime_movies_only', false)}
          onChange={(v) => save({ wanted_anime_movies_only: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.max_items_per_run')}
        hint={tS('automation_page.max_items_per_run_hint')}
        htmlFor="wanted-search-max-items-per-run"
        advanced
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
        label={tS('automation_page.search_order')}
        hint={tS('automation_page.search_order_hint')}
        htmlFor="wanted-search-order"
        advanced
        data-testid="form-group-wanted-search-order"
      >
        <select
          id="wanted-search-order"
          data-testid="input-wanted-search-order"
          style={{ ...inputStyle, maxWidth: '320px' }}
          value={strVal(config, 'wanted_search_order', 'fair')}
          onChange={(e) => save({ wanted_search_order: e.target.value })}
          disabled={updateConfig.isPending}
        >
          <option value="fair">{tS('automation_page.order_fair')}</option>
          <option value="newest_first">{tS('automation_page.order_newest_first')}</option>
          <option value="weighted">{tS('automation_page.order_weighted')}</option>
        </select>
      </FormGroup>

      <FormGroup
        label={tS('automation_page.provider_budget_enabled')}
        hint={tS('automation_page.provider_budget_enabled_hint')}
        advanced
        htmlFor="provider-budget-enabled"
        data-testid="form-group-provider-budget-enabled"
      >
        <Toggle
          checked={boolVal(config, 'provider_budget_enabled', true)}
          onChange={(v) => save({ provider_budget_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      {/* Pacing only means something while the budget gate is on. */}
      {boolVal(config, 'provider_budget_enabled', true) && (
        <FormGroup
          label={tS('automation_page.stretch_mode')}
          hint={tS('automation_page.stretch_mode_hint')}
          htmlFor="provider-budget-stretch-mode"
          advanced
          data-testid="form-group-provider-budget-stretch-mode"
        >
          <select
            id="provider-budget-stretch-mode"
            data-testid="input-provider-budget-stretch-mode"
            style={{ ...inputStyle, maxWidth: '320px' }}
            value={strVal(config, 'provider_budget_stretch_mode', 'stretch')}
            onChange={(e) => save({ provider_budget_stretch_mode: e.target.value })}
            disabled={updateConfig.isPending}
          >
            <option value="stretch">{tS('automation_page.stretch_mode_stretch')}</option>
            <option value="burst">{tS('automation_page.stretch_mode_burst')}</option>
            <option value="adaptive">{tS('automation_page.stretch_mode_adaptive')}</option>
          </select>
        </FormGroup>
      )}

      {boolVal(config, 'provider_budget_enabled', true) &&
        strVal(config, 'provider_budget_stretch_mode', 'stretch') === 'burst' && (
        <FormGroup
          label={tS('automation_page.burst_window_hours')}
          hint={tS('automation_page.burst_window_hours_hint')}
          htmlFor="provider-budget-burst-window"
          advanced
          data-testid="form-group-provider-budget-burst-window-hours"
        >
          <input
            id="provider-budget-burst-window"
            type="number"
            data-testid="input-provider-budget-burst-window-hours"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(config, 'provider_budget_burst_window_hours', '6')}
            onChange={(e) => {
              const v = Number(e.target.value)
              const clamped = Math.max(1, Math.min(23, Number.isFinite(v) ? v : 6))
              save({ provider_budget_burst_window_hours: clamped })
            }}
            disabled={updateConfig.isPending}
            min={1}
            max={23}
          />
        </FormGroup>
      )}

      <FormGroup
        label={tS('automation_page.adaptive_backoff')}
        hint={tS('automation_page.adaptive_backoff_hint')}
        advanced
        htmlFor="wanted-adaptive-backoff-enabled"
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
            advanced
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
            advanced
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

export function SearchScanContent() {
  const { t } = useTranslation('settings')
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
        htmlFor="wanted-scan-on-startup"
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
        htmlFor="wanted-search-on-startup"
        data-testid="form-group-wanted-search-on-startup"
      >
        <Toggle
          checked={boolVal(config, 'wanted_search_on_startup', false)}
          onChange={(v) => save({ wanted_search_on_startup: v })}
          disabled={updateConfig.isPending}
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

    </div>
  )
}
