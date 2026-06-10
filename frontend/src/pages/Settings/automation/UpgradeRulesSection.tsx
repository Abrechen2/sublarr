/**
 * Upgrade Rules section for AutomationSettings — basic + advanced content.
 * Extracted from AutomationSettings.tsx during the file-size split.
 */
import { useTranslation } from 'react-i18next'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal, boolVal } from '@/lib/configUtils'
import { inputStyle, SectionSkeleton } from './shared'

export function UpgradeRulesAdvancedContent() {
  const { t } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()
  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="upgrade-rules-advanced-content">
      <FormGroup
        label={t('settings.automation.upgradeRules.checkInterval', 'Upgrade Scan Interval (hours)')}
        hint={t(
          'settings.automation.upgradeRules.checkIntervalHint',
          'How often (in hours) existing subtitles are checked for upgrade candidates.',
        )}
        htmlFor="upgrade-scan-interval-hours"
        advanced
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
    </div>
  )
}

export function UpgradeRulesContent() {
  const { t } = useTranslation('settings')
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
        htmlFor="upgrade-enabled"
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
        htmlFor="upgrade-prefer-ass"
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
