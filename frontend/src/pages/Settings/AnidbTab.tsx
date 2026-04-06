/**
 * AnidbTab — AniDB integration settings.
 * Provides toggle, cache TTL, custom field name, and fallback mapping config.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'

export function AnidbTab() {
  const { data: config } = useConfig()
  const { t } = useTranslation('settings')
  const updateConfig = useUpdateConfig()
  const cfg = (config ?? {}) as Record<string, unknown>

  const anidbEnabled = cfg['anidb_enabled'] === 'true'
  const anidbFallback = cfg['anidb_fallback_to_mapping'] === 'true'
  const [localCacheTtl, setLocalCacheTtl] = useState<string>('7')
  const [localCustomField, setLocalCustomField] = useState<string>('')

  useEffect(() => {
    setLocalCacheTtl(String(cfg['anidb_cache_ttl_days'] ?? '7'))
    setLocalCustomField(String(cfg['anidb_custom_field_name'] ?? ''))
  }, [config]) // eslint-disable-line react-hooks/exhaustive-deps

  const saveToggle = (key: string, value: boolean) => {
    updateConfig.mutate(
      { [key]: String(value) },
      {
        onSuccess: () => toast('Setting saved'),
        onError: () => toast('Failed to save setting', 'error'),
      },
    )
  }

  const saveField = (key: string, value: string) => {
    updateConfig.mutate(
      { [key]: value },
      {
        onSuccess: () => toast('Setting saved'),
        onError: () => toast('Failed to save setting', 'error'),
      },
    )
  }

  return (
    <div className="space-y-3">
      <SettingRow
        label={t('anidb_tab.enable')}
        description={t('anidb_tab.enable_desc')}
      >
        <Toggle
          checked={anidbEnabled}
          onChange={(v) => saveToggle('anidb_enabled', v)}
          disabled={updateConfig.isPending}
        />
      </SettingRow>

      <SettingRow
        label={t('anidb_tab.cache_ttl')}
        description={t('anidb_tab.cache_ttl_desc')}
      >
        <input
          type="number"
          min={0}
          value={localCacheTtl}
          onChange={(e) => setLocalCacheTtl(e.target.value)}
          onBlur={() => saveField('anidb_cache_ttl_days', localCacheTtl)}
          className="w-24 px-3 py-2 rounded-md text-sm"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontSize: '13px',
          }}
        />
      </SettingRow>

      <SettingRow
        label={t('anidb_tab.custom_field')}
        description={t('anidb_tab.custom_field_desc')}
      >
        <input
          type="text"
          value={localCustomField}
          onChange={(e) => setLocalCustomField(e.target.value)}
          onBlur={() => saveField('anidb_custom_field_name', localCustomField)}
          className="w-full px-3 py-2 rounded-md text-sm"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
          }}
        />
      </SettingRow>

      <SettingRow
        label={t('anidb_tab.fallback_mapping')}
        description={t('anidb_tab.fallback_mapping_desc')}
      >
        <Toggle
          checked={anidbFallback}
          onChange={(v) => saveToggle('anidb_fallback_to_mapping', v)}
          disabled={updateConfig.isPending}
        />
      </SettingRow>
    </div>
  )
}
