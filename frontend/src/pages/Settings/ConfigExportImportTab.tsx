import { useState, useRef } from 'react'
import { Upload, Download } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SettingRow } from '@/components/shared/SettingRow'
import { toast } from '@/components/shared/Toast'
import { useExportConfig, useImportConfig } from '@/hooks/useSystemApi'

// ─── ConfigExportImportTab ────────────────────────────────────────────────────

export function ConfigExportImportTab() {
  const { t } = useTranslation('settings')
  const { t: tC } = useTranslation('common')
  const exportMut = useExportConfig()
  const importMut = useImportConfig()

  // Import flow state
  const [importData, setImportData] = useState<Record<string, unknown> | null>(null)
  const [importKeyCount, setImportKeyCount] = useState(0)
  const [showConfirm, setShowConfirm] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleExport = () => {
    exportMut.mutate(undefined, {
      onSuccess: (data) => {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'sublarr-config.json'
        a.click()
        URL.revokeObjectURL(url)
      },
      onError: () => toast(t('config_export_import.export_failed'), 'error'),
    })
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target?.result as string) as Record<string, unknown>
        setImportData(parsed)
        setImportKeyCount(Object.keys(parsed).length)
        setShowConfirm(true)
      } catch {
        toast(t('config_export_import.invalid_json'), 'error')
      }
      // Reset file input so same file can be selected again
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
    reader.readAsText(file)
  }

  const handleConfirmImport = () => {
    if (!importData) return
    importMut.mutate(importData, {
      onSuccess: (result) => {
        toast(t('config_export_import.imported', { count: result.imported_keys.length }))
        setShowConfirm(false)
        setImportData(null)
      },
      onError: () => {
        toast(t('config_export_import.export_failed'), 'error')
        setShowConfirm(false)
        setImportData(null)
      },
    })
  }

  const handleCancelImport = () => {
    setShowConfirm(false)
    setImportData(null)
  }

  return (
    <div>
      {/* Export row */}
      <SettingRow
        label={t('config_export_import.export_label')}
        description={t('config_export_import.export_desc')}
      >
        <button
          className="btn-secondary flex items-center gap-1.5"
          onClick={handleExport}
          disabled={exportMut.isPending}
          data-testid="export-config-btn"
        >
          <Download size={14} />
          {exportMut.isPending ? t('config_export_import.exporting') : t('config_export_import.export_btn')}
        </button>
      </SettingRow>

      {/* Import row */}
      <SettingRow
        label={t('config_export_import.import_label')}
        description={t('config_export_import.import_desc')}
      >
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            onChange={handleFileChange}
            className="hidden"
            data-testid="import-file-input"
            id="import-config-file"
          />
          <label
            htmlFor="import-config-file"
            className="btn-secondary flex items-center gap-1.5 cursor-pointer"
            style={{ userSelect: 'none' }}
          >
            <Upload size={14} />
            {t('config_export_import.choose_file')}
          </label>
        </div>
      </SettingRow>

      {/* Confirm dialog */}
      {showConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-sm mx-4 rounded-xl p-5 space-y-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
              {t('config_export_import.import_confirm_title', { count: importKeyCount })}
            </h3>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {t('config_export_import.import_confirm_body')}
            </p>
            <div className="flex gap-2 justify-end">
              <button
                className="btn-secondary text-sm"
                onClick={handleCancelImport}
                data-testid="import-cancel-btn"
              >
                {tC('actions.cancel')}
              </button>
              <button
                className="btn-primary text-sm"
                onClick={handleConfirmImport}
                disabled={importMut.isPending}
                data-testid="import-confirm-btn"
              >
                {importMut.isPending ? t('config_export_import.importing') : t('config_export_import.import_btn')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
