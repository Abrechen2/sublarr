/**
 * StandaloneSettingsTab — Standalone file watcher configuration.
 * Configures scan interval, debounce, and extras skip behavior.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'
import { boolVal } from '@/lib/configUtils'

export function StandaloneSettingsTab() {
  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()

  const skipExtras = boolVal(config, 'standalone_skip_extras', false)
  const [localScanInterval, setLocalScanInterval] = useState<string>('24')
  const [localDebounce, setLocalDebounce] = useState<string>('30')

  useEffect(() => {
    const cfg = (config ?? {}) as Record<string, unknown>
    setLocalScanInterval(String(cfg['standalone_scan_interval_hours'] ?? '24'))
    setLocalDebounce(String(cfg['standalone_debounce_seconds'] ?? '30'))
  }, [config]) // eslint-disable-line react-hooks/exhaustive-deps

  const saveToggle = (key: string, value: boolean) => {
    updateConfig.mutate(
      { [key]: value },
      {
        onSuccess: () => toast(t('setting_saved')),
        onError: () => toast(t('setting_save_failed'), 'error'),
      },
    )
  }

  const saveField = (key: string, value: string) => {
    updateConfig.mutate(
      { [key]: value },
      {
        onSuccess: () => toast(t('setting_saved')),
        onError: () => toast(t('setting_save_failed'), 'error'),
      },
    )
  }

  return (
    <div className="space-y-3">
      <SettingRow
        label={t('standalone_tab.scan_interval')}
        description={t('standalone_tab.scan_interval_desc')}
      >
        <input
          type="number"
          min={1}
          value={localScanInterval}
          onChange={(e) => setLocalScanInterval(e.target.value)}
          onBlur={() => saveField('standalone_scan_interval_hours', localScanInterval)}
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
        label={t('standalone_tab.debounce')}
        description={t('standalone_tab.debounce_desc')}
      >
        <input
          type="number"
          min={0}
          value={localDebounce}
          onChange={(e) => setLocalDebounce(e.target.value)}
          onBlur={() => saveField('standalone_debounce_seconds', localDebounce)}
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
        label={t('standalone_tab.skip_extras')}
        description={t('standalone_tab.skip_extras_desc')}
      >
        <Toggle
          checked={skipExtras}
          onChange={(v) => saveToggle('standalone_skip_extras', v)}
          disabled={updateConfig.isPending}
        />
      </SettingRow>
    </div>
  )
}
