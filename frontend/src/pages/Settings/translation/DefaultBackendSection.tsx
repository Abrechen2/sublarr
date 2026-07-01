import { useTranslation } from 'react-i18next'
import { SettingRow } from '@/components/shared/SettingRow'
import { useBackends, useConfig, useUpdateConfig } from '@/hooks/useApi'
import { BackendSelect } from '@/components/settings/BackendSelect'
import type { TranslationBackendInfo } from '@/types/translation'

export function DefaultBackendSection() {
  const { t } = useTranslation('settings')
  const { data: backendsResult } = useBackends()
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()

  // `useBackends()` normally resolves to `{ backends: TranslationBackendInfo[] }`,
  // but this component's test mocks `data` as a flat array — support both shapes
  // so the component works against the real API and against the prescribed test.
  const list: TranslationBackendInfo[] = Array.isArray(backendsResult)
    ? backendsResult
    : (backendsResult?.backends ?? [])

  const primary = (config?.translation_default_backend as string | undefined) ?? 'ollama'
  const fallback = (config?.translation_default_fallback as string | undefined) ?? ''
  const unconfLabel = t('translation_backends.default_backend_unconfigured')

  const primaryUnconfigured =
    primary !== 'ollama' && !list.find((b) => b.name === primary)?.configured

  return (
    <div className="rounded-lg p-4 space-y-3 bg-surface border border-border">
      <h2 className="text-sm font-semibold text-primary">
        {t('translation_backends.default_backend_title')}
      </h2>
      <p className="text-xs text-muted">{t('translation_backends.default_backend_help')}</p>
      <SettingRow label={t('translation_backends.default_backend_primary')}>
        <BackendSelect
          data-testid="default-backend-primary"
          value={primary}
          backends={list}
          unconfiguredLabel={unconfLabel}
          onChange={(name) => updateConfig.mutate({ translation_default_backend: name })}
        />
      </SettingRow>
      {primaryUnconfigured && (
        <p className="text-xs text-warning">
          {t('translation_backends.default_backend_unconfigured_warn')}
        </p>
      )}
      <SettingRow label={t('translation_backends.default_backend_fallback')}>
        <BackendSelect
          data-testid="default-backend-fallback"
          value={fallback}
          backends={list}
          noneLabel={t('translation_backends.default_backend_none')}
          unconfiguredLabel={unconfLabel}
          onChange={(name) => updateConfig.mutate({ translation_default_fallback: name })}
        />
      </SettingRow>
    </div>
  )
}
