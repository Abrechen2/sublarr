/**
 * The subtitle-health switches; they were configurable only through the API.
 */
import { useTranslation } from 'react-i18next'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { boolVal } from '@/lib/configUtils'

const SWITCHES = [
  { key: 'subtitle_health_enabled', fallback: true },
  { key: 'subtitle_health_sweep_enabled', fallback: true },
  { key: 'subtitle_health_auto_fix', fallback: false },
] as const

export function SubtitleHealthSwitches() {
  const { t } = useTranslation('library')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()

  return (
    <div data-testid="subtitle-health-switches">
      {SWITCHES.map(({ key, fallback }) => (
        <FormGroup
          key={key}
          label={t(`subtitle_health.settings.${key}`)}
          hint={t(`subtitle_health.settings.${key}_hint`)}
          htmlFor={key}
          data-testid={`form-group-${key}`}
        >
          <Toggle
            checked={boolVal(config, key, fallback)}
            onChange={(v) => updateConfig.mutate({ [key]: v })}
            disabled={updateConfig.isPending}
          />
        </FormGroup>
      ))}
    </div>
  )
}
