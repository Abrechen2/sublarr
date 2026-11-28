/**
 * Sonarr/Radarr exclusions (Forgejo #83): keep series or movies out of the
 * Wanted list by tag, series type or monitored state, like Bazarr's
 * Sonarr/Radarr options. Everything is off by default.
 */
import { useTranslation } from 'react-i18next'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { boolVal, strVal } from '@/lib/configUtils'
import { inputStyle } from './shared'

const SERIES_TYPES = ['standard', 'anime', 'daily'] as const

interface Props {
  readonly config: unknown
  readonly save: (patch: Record<string, unknown>) => void
  readonly disabled: boolean
}

function parseList(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean)
}

function TagsInput({
  id,
  configKey,
  config,
  save,
  disabled,
}: Props & { readonly id: string; readonly configKey: string }) {
  const current = strVal(config, configKey, '')
  return (
    <input
      // Remount when the saved value changes so the field shows it.
      key={current}
      id={id}
      type="text"
      data-testid={`input-${id}`}
      style={{ ...inputStyle, maxWidth: '320px' }}
      defaultValue={current}
      placeholder="no-subs, kids"
      disabled={disabled}
      onBlur={(e) => {
        const next = parseList(e.target.value).join(', ')
        if (next !== current) save({ [configKey]: next })
      }}
    />
  )
}

export function ArrExclusionsFields({ config, save, disabled }: Props) {
  const { t } = useTranslation('settings')
  const excludedTypes = parseList(strVal(config, 'sonarr_exclude_series_types', ''))

  const toggleType = (type: string, on: boolean) => {
    const next = on
      ? [...new Set([...excludedTypes, type])]
      : excludedTypes.filter((entry) => entry !== type)
    save({ sonarr_exclude_series_types: SERIES_TYPES.filter((s) => next.includes(s)).join(',') })
  }

  return (
    <>
      <FormGroup
        label={t('automation_page.sonarr_exclude_tags')}
        hint={t('automation_page.sonarr_exclude_tags_hint')}
        htmlFor="sonarr-exclude-tags"
        data-testid="form-group-sonarr-exclude-tags"
      >
        <TagsInput
          id="sonarr-exclude-tags"
          configKey="sonarr_exclude_tags"
          config={config}
          save={save}
          disabled={disabled}
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.sonarr_exclude_series_types')}
        hint={t('automation_page.sonarr_exclude_series_types_hint')}
        data-testid="form-group-sonarr-exclude-series-types"
      >
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {SERIES_TYPES.map((type) => (
            <label key={type} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input
                type="checkbox"
                data-testid={`checkbox-exclude-series-type-${type}`}
                checked={excludedTypes.includes(type)}
                disabled={disabled}
                onChange={(e) => toggleType(type, e.target.checked)}
              />
              {t(`automation_page.series_type_${type}`)}
            </label>
          ))}
        </div>
      </FormGroup>

      <FormGroup
        label={t('automation_page.sonarr_only_monitored')}
        hint={t('automation_page.sonarr_only_monitored_hint')}
        data-testid="form-group-sonarr-only-monitored"
      >
        <Toggle
          checked={boolVal(config, 'sonarr_only_monitored', false)}
          onChange={(v) => save({ sonarr_only_monitored: v })}
          disabled={disabled}
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.radarr_exclude_tags')}
        hint={t('automation_page.radarr_exclude_tags_hint')}
        htmlFor="radarr-exclude-tags"
        data-testid="form-group-radarr-exclude-tags"
      >
        <TagsInput
          id="radarr-exclude-tags"
          configKey="radarr_exclude_tags"
          config={config}
          save={save}
          disabled={disabled}
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.radarr_only_monitored')}
        hint={t('automation_page.radarr_only_monitored_hint')}
        data-testid="form-group-radarr-only-monitored"
      >
        <Toggle
          checked={boolVal(config, 'radarr_only_monitored', false)}
          onChange={(v) => save({ radarr_only_monitored: v })}
          disabled={disabled}
        />
      </FormGroup>
    </>
  )
}
