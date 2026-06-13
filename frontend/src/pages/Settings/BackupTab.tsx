import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useFullBackups,
  useCreateFullBackup,
  useRestoreFullBackup,
  useConfig,
  useUpdateConfig,
} from '@/hooks/useApi'
import { Loader2, Upload, Download, HardDrive, AlertTriangle, RotateCcw } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { downloadFullBackupUrl } from '@/api/client'
import type { FullBackupInfo } from '@/lib/types'
import { SettingRow } from '@/components/shared/SettingRow'

// ─── Backup Tab ──────────────────────────────────────────────────────────────

export function BackupTab() {
  const { data: backupsData, isLoading } = useFullBackups()
  const { t } = useTranslation('settings')
  const createBackup = useCreateFullBackup()
  const restoreBackup = useRestoreFullBackup()
  const [restoreFile, setRestoreFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Retention policy fields
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const cfg = (config ?? {}) as Record<string, unknown>
  const [localBackupDir, setLocalBackupDir] = useState<string>('')
  const [localRetentionDaily, setLocalRetentionDaily] = useState<string>('')
  const [localRetentionWeekly, setLocalRetentionWeekly] = useState<string>('')
  const [localRetentionMonthly, setLocalRetentionMonthly] = useState<string>('')

  useEffect(() => {
    setLocalBackupDir(String(cfg['backup_dir'] ?? ''))
    setLocalRetentionDaily(String(cfg['backup_retention_daily'] ?? '7'))
    setLocalRetentionWeekly(String(cfg['backup_retention_weekly'] ?? '4'))
    setLocalRetentionMonthly(String(cfg['backup_retention_monthly'] ?? '3'))
  }, [config]) // eslint-disable-line react-hooks/exhaustive-deps

  const saveField = (key: string, value: string) => {
    updateConfig.mutate(
      { [key]: value },
      {
        onSuccess: () => toast(t('toast.setting_saved')),
        onError: () => toast(t('toast.setting_save_failed'), 'error'),
      },
    )
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-'
    const d = new Date(dateStr)
    return d.toLocaleString()
  }

  const handleCreate = () => {
    createBackup.mutate(undefined, {
      onSuccess: (data) => {
        toast(t('backup_tab.created_toast', { filename: data.filename }))
      },
      onError: () => toast(t('backup_tab.create_failed'), 'error'),
    })
  }

  const handleRestoreFromFile = () => {
    if (!restoreFile) return
    restoreBackup.mutate(restoreFile, {
      onSuccess: (result) => {
        const imported = result.config_imported?.length || 0
        const db = result.db_restored ? t('backup_tab.db_restored') : t('backup_tab.db_skipped')
        toast(t('backup_tab.restored_toast', { count: imported, db }))
        setRestoreFile(null)
      },
      onError: () => toast(t('backup_tab.restore_failed_toast'), 'error'),
    })
  }

  const backups = backupsData?.backups || []

  return (
    <div className="space-y-4">
      {/* Create Backup */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          {t('backup_tab.create_title')}
        </h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          {t('backup_tab.create_desc')}
        </p>
        <button
          onClick={handleCreate}
          disabled={createBackup.isPending}
          className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {createBackup.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <HardDrive size={14} />
          )}
          {createBackup.isPending ? t('backup_tab.creating') : t('backup_tab.create_button')}
        </button>
      </div>

      {/* Backup List */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          {t('backup_tab.existing_title')}
        </h3>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
          </div>
        ) : backups.length === 0 ? (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            {t('backup_tab.no_backups')}
          </p>
        ) : (
          <div className="space-y-2">
            {backups.map((backup: FullBackupInfo) => (
              <div
                key={backup.filename}
                className="flex items-center justify-between px-3 py-2 rounded-md"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              >
                <div>
                  <div className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                    {backup.filename}
                  </div>
                  <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    {formatSize(backup.size_bytes)} &middot; {formatDate(backup.created_at)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href={downloadFullBackupUrl(backup.filename)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-all"
                    style={{
                      border: '1px solid var(--border)',
                      color: 'var(--text-secondary)',
                      backgroundColor: 'var(--bg-surface)',
                    }}
                  >
                    <Download size={12} />
                    {t('backup_tab.download')}
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Restore from File */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          {t('backup_tab.restore_title')}
        </h3>
        <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--warning)' }}>
          <AlertTriangle size={14} />
          <span className="text-xs">{t('backup_tab.restore_warning')}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            <Upload size={14} />
            {t('backup_tab.select_zip')}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            onChange={(e) => setRestoreFile(e.target.files?.[0] || null)}
            className="hidden"
          />
          {restoreFile && (
            <>
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {restoreFile.name}
              </span>
              <button
                onClick={handleRestoreFromFile}
                disabled={restoreBackup.isPending}
                className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {restoreBackup.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <RotateCcw size={12} />
                )}
                {t('backup_tab.restore_button')}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Retention Policy */}
      <div className="rounded-lg p-5 space-y-3" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('backup_tab.retention_title')}
        </h3>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {t('backup_tab.retention_desc')}
        </p>
        <SettingRow label={t('backup_tab.backup_dir')} description={t('backup_tab.backup_dir_desc')}>
          <input
            type="text"
            value={localBackupDir}
            onChange={(e) => setLocalBackupDir(e.target.value)}
            onBlur={() => saveField('backup_dir', localBackupDir)}
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
        <SettingRow label={t('backup_tab.daily_backups')} description={t('backup_tab.daily_backups_desc')}>
          <input
            type="number"
            min={0}
            value={localRetentionDaily}
            onChange={(e) => setLocalRetentionDaily(e.target.value)}
            onBlur={() => saveField('backup_retention_daily', localRetentionDaily)}
            className="w-24 px-3 py-2 rounded-md text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontSize: '13px',
            }}
          />
        </SettingRow>
        <SettingRow label={t('backup_tab.weekly_backups')} description={t('backup_tab.weekly_backups_desc')}>
          <input
            type="number"
            min={0}
            value={localRetentionWeekly}
            onChange={(e) => setLocalRetentionWeekly(e.target.value)}
            onBlur={() => saveField('backup_retention_weekly', localRetentionWeekly)}
            className="w-24 px-3 py-2 rounded-md text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontSize: '13px',
            }}
          />
        </SettingRow>
        <SettingRow label={t('backup_tab.monthly_backups')} description={t('backup_tab.monthly_backups_desc')}>
          <input
            type="number"
            min={0}
            value={localRetentionMonthly}
            onChange={(e) => setLocalRetentionMonthly(e.target.value)}
            onBlur={() => saveField('backup_retention_monthly', localRetentionMonthly)}
            className="w-24 px-3 py-2 rounded-md text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontSize: '13px',
            }}
          />
        </SettingRow>
      </div>
    </div>
  )
}
