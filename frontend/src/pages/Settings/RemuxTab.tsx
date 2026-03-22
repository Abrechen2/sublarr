/**
 * RemuxTab — Remux operation settings.
 * Configures trash directory, backup retention, reflink, and Arr pause behavior.
 */
import { useState, useEffect } from 'react'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'

export function RemuxTab() {
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const cfg = (config ?? {}) as Record<string, unknown>

  const useReflink = cfg['remux_use_reflink'] === 'true'
  const arrPauseEnabled = cfg['remux_arr_pause_enabled'] === 'true'
  const [localTrashDir, setLocalTrashDir] = useState<string>('')
  const [localRetentionDays, setLocalRetentionDays] = useState<string>('7')

  useEffect(() => {
    setLocalTrashDir(String(cfg['remux_trash_dir'] ?? ''))
    setLocalRetentionDays(String(cfg['remux_backup_retention_days'] ?? '7'))
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
        label="Trash Directory"
        description="Path for remux trash/originals"
      >
        <input
          type="text"
          value={localTrashDir}
          onChange={(e) => setLocalTrashDir(e.target.value)}
          onBlur={() => saveField('remux_trash_dir', localTrashDir)}
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
        label="Backup Retention (days)"
        description="Days to keep remux backups"
      >
        <input
          type="number"
          min={0}
          value={localRetentionDays}
          onChange={(e) => setLocalRetentionDays(e.target.value)}
          onBlur={() => saveField('remux_backup_retention_days', localRetentionDays)}
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
        label="Use Reflink"
        description="Use CoW reflink copies instead of full copies"
      >
        <Toggle
          checked={useReflink}
          onChange={(v) => saveToggle('remux_use_reflink', v)}
          disabled={updateConfig.isPending}
        />
      </SettingRow>

      <SettingRow
        label="Pause Arr on Remux"
        description="Pause Sonarr/Radarr during remux operations"
      >
        <Toggle
          checked={arrPauseEnabled}
          onChange={(v) => saveToggle('remux_arr_pause_enabled', v)}
          disabled={updateConfig.isPending}
        />
      </SettingRow>
    </div>
  )
}
