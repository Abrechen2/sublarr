/**
 * RemuxTab — Remux operation settings.
 * Configures trash directory, backup retention, reflink, and Arr pause behavior.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'

export function RemuxTab() {
  const { t } = useTranslation('settings')
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
        label={t('remux_tab.trash_dir')}
        description={t('remux_tab.trash_dir_desc')}
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
        label={t('remux_tab.retention_days')}
        description={t('remux_tab.retention_days_desc')}
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
        label={t('remux_tab.use_reflink')}
        description={t('remux_tab.use_reflink_desc')}
      >
        <Toggle
          checked={useReflink}
          onChange={(v) => saveToggle('remux_use_reflink', v)}
          disabled={updateConfig.isPending}
        />
      </SettingRow>

      <SettingRow
        label={t('remux_tab.arr_pause')}
        description={t('remux_tab.arr_pause_desc')}
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
