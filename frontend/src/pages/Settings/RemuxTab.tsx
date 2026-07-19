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
import { boolVal } from '@/lib/configUtils'
import { cleanupRemuxBackups } from '@/api/library'

export function RemuxTab() {
  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()

  const useReflink = boolVal(config, 'remux_use_reflink', false)
  const arrPauseEnabled = boolVal(config, 'remux_arr_pause_enabled', false)
  const [localTrashDir, setLocalTrashDir] = useState<string>('')
  const [localRetentionDays, setLocalRetentionDays] = useState<string>('7')
  // Manual backup cleanup: preview (dry-run count) then confirm the real delete.
  const [cleanupBusy, setCleanupBusy] = useState(false)
  const [cleanupPreview, setCleanupPreview] = useState<number | null>(null)

  const previewCleanup = async () => {
    setCleanupBusy(true)
    try {
      const r = await cleanupRemuxBackups(true)
      setCleanupPreview(r.count ?? r.would_delete?.length ?? 0)
    } catch {
      toast(t('remux_tab.cleanup_failed'), 'error')
    } finally {
      setCleanupBusy(false)
    }
  }

  const runCleanup = async () => {
    setCleanupBusy(true)
    try {
      const r = await cleanupRemuxBackups(false)
      toast(t('remux_tab.cleanup_done', { count: r.deleted?.length ?? 0 }))
      setCleanupPreview(null)
    } catch {
      toast(t('remux_tab.cleanup_failed'), 'error')
    } finally {
      setCleanupBusy(false)
    }
  }

  useEffect(() => {
    const cfg = (config ?? {}) as Record<string, unknown>
    setLocalTrashDir(String(cfg['remux_trash_dir'] ?? ''))
    setLocalRetentionDays(String(cfg['remux_backup_retention_days'] ?? '7'))
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

      <SettingRow
        label={t('remux_tab.cleanup')}
        description={t('remux_tab.cleanup_desc')}
      >
        <div className="flex items-center gap-3 flex-wrap">
          {cleanupPreview === null ? (
            <button
              type="button"
              onClick={previewCleanup}
              disabled={cleanupBusy}
              className="px-3 py-1.5 rounded-md text-xs font-medium border border-border bg-surface text-primary disabled:opacity-40"
            >
              {cleanupBusy ? t('remux_tab.cleanup_checking') : t('remux_tab.cleanup_preview')}
            </button>
          ) : cleanupPreview === 0 ? (
            <span className="text-xs text-muted">{t('remux_tab.cleanup_none')}</span>
          ) : (
            <>
              <span className="text-xs text-warning">
                {t('remux_tab.cleanup_would_delete', { count: cleanupPreview })}
              </span>
              <button
                type="button"
                onClick={runCleanup}
                disabled={cleanupBusy}
                className="px-3 py-1.5 rounded-md text-xs font-medium border border-error text-error bg-surface disabled:opacity-40"
              >
                {t('remux_tab.cleanup_confirm')}
              </button>
              <button
                type="button"
                onClick={() => setCleanupPreview(null)}
                disabled={cleanupBusy}
                className="px-3 py-1.5 rounded-md text-xs text-muted disabled:opacity-40"
              >
                {t('remux_tab.cleanup_cancel')}
              </button>
            </>
          )}
        </div>
      </SettingRow>
    </div>
  )
}
