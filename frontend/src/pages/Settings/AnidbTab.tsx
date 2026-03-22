/**
 * AnidbTab — AniDB integration settings.
 * Provides toggle, cache TTL, custom field name, and fallback mapping config.
 */
import { useState, useEffect } from 'react'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'

export function AnidbTab() {
  const { data: config } = useConfig()
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
        label="Enable AniDB"
        description="Use AniDB for anime metadata lookups"
      >
        <Toggle
          checked={anidbEnabled}
          onChange={(v) => saveToggle('anidb_enabled', v)}
          disabled={updateConfig.isPending}
        />
      </SettingRow>

      <SettingRow
        label="Cache TTL (days)"
        description="Days to cache AniDB responses"
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
        label="Custom Field Name"
        description="Custom metadata field name for AniDB ID"
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
        label="Fallback to Mapping"
        description="Use AniDB-to-Sonarr mapping when direct lookup fails"
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
