/**
 * StandaloneSettingsTab — Standalone file watcher configuration.
 * Configures scan interval, debounce, and extras skip behavior.
 */
import { useState, useEffect } from 'react'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'

export function StandaloneSettingsTab() {
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const cfg = (config ?? {}) as Record<string, unknown>

  const skipExtras = cfg['standalone_skip_extras'] === 'true'
  const [localScanInterval, setLocalScanInterval] = useState<string>('24')
  const [localDebounce, setLocalDebounce] = useState<string>('30')

  useEffect(() => {
    setLocalScanInterval(String(cfg['standalone_scan_interval_hours'] ?? '24'))
    setLocalDebounce(String(cfg['standalone_debounce_seconds'] ?? '30'))
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
        label="Scan Interval (hours)"
        description="How often the standalone watcher rescans"
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
        label="Debounce (seconds)"
        description="Seconds to wait after a file event before processing"
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
        label="Skip Extras"
        description="Skip extras/specials during standalone scan"
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
