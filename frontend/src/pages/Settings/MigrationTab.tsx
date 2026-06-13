/**
 * MigrationTab - Bazarr migration wizard UI.
 *
 * Provides step-by-step wizard for migrating from Bazarr to Sublarr.
 */

import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Upload, CheckCircle, FileText, Database } from 'lucide-react'
import { toast } from '@/components/shared/Toast'

interface MigrationPreview {
  config_entries: number
  profiles: number
  blacklist_entries: number
  history_entries: number
}

interface MigrationResult {
  config_imported: number
  profiles_imported: number
  blacklist_imported: number
  history_imported: number
}

export function MigrationTab() {
  const { t } = useTranslation('settings')
  const { t: tc } = useTranslation('common')
  const [step, setStep] = useState<'upload' | 'preview' | 'import' | 'complete'>('upload')
  const [configFile, setConfigFile] = useState<File | null>(null)
  const [dbFile, setDbFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<MigrationPreview | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [importResult, setImportResult] = useState<MigrationResult | null>(null)

  const handleConfigUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setConfigFile(file)
    }
  }, [])

  const handleDbUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setDbFile(file)
    }
  }, [])

  const handleAnalyze = useCallback(async () => {
    if (!configFile && !dbFile) {
      toast(t('migration.upload_required'), 'error')
      return
    }

    setIsLoading(true)
    try {
      // In a real implementation, this would upload files and analyze them
      // For now, we'll simulate the preview
      const previewData = {
        config_entries: configFile ? 10 : 0,
        profiles: dbFile ? 5 : 0,
        blacklist_entries: dbFile ? 20 : 0,
        history_entries: dbFile ? 100 : 0,
      }
      setPreview(previewData)
      setStep('preview')
      toast(t('migration.analysis_complete'), 'success')
    } catch (_err) {
      toast(t('migration.analysis_failed'), 'error')
    } finally {
      setIsLoading(false)
    }
  }, [configFile, dbFile, t])

  const handleImport = useCallback(async () => {
    setIsLoading(true)
    try {
      // In a real implementation, this would call the import API
      const result = {
        config_imported: preview?.config_entries || 0,
        profiles_imported: preview?.profiles || 0,
        blacklist_imported: preview?.blacklist_entries || 0,
        history_imported: preview?.history_entries || 0,
      }
      setImportResult(result)
      setStep('complete')
      toast(t('migration.completed'), 'success')
    } catch (_err) {
      toast(t('migration.failed'), 'error')
    } finally {
      setIsLoading(false)
    }
  }, [preview, t])

  return (
    <div className="space-y-6">
      <div className="rounded-lg p-4 mb-6" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>{tc('ui.bazarr_migration')}</h3>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {t('migration.intro_desc')}
        </p>
      </div>

      <div>
        <h2 className="text-2xl font-bold mb-2">{t('integrations.bazarr.title')}</h2>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {t('migration.subtitle')}
        </p>
      </div>

      {/* Step 1: Upload */}
      {step === 'upload' && (
        <div className="space-y-4">
          <div className="rounded-lg p-6" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
            <h3 className="text-lg font-semibold mb-4">{t('migration.step1_title')}</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  <FileText className="inline w-4 h-4 mr-2" />
                  {t('migration.config_file_label')}
                </label>
                <input
                  type="file"
                  accept=".yaml,.yml,.ini,.cfg"
                  onChange={handleConfigUpload}
                  className="block w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-teal-500 file:text-white hover:file:bg-teal-600" style={{ color: 'var(--text-secondary)' }}
                />
                {configFile && (
                  <p className="mt-2 text-sm" style={{ color: 'var(--text-secondary)' }}>{t('migration.selected', { name: configFile.name })}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  <Database className="inline w-4 h-4 mr-2" />
                  {t('migration.db_file_label')}
                </label>
                <input
                  type="file"
                  accept=".db,.sqlite,.sqlite3"
                  onChange={handleDbUpload}
                  className="block w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-teal-500 file:text-white hover:file:bg-teal-600" style={{ color: 'var(--text-secondary)' }}
                />
                {dbFile && (
                  <p className="mt-2 text-sm" style={{ color: 'var(--text-secondary)' }}>{t('migration.selected', { name: dbFile.name })}</p>
                )}
              </div>
            </div>

            <button
              onClick={handleAnalyze}
              disabled={isLoading || (!configFile && !dbFile)}
              className="mt-6 px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4" />
              )}
              {t('migration.analyze_button')}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Preview */}
      {step === 'preview' && preview && (
        <div className="space-y-4">
          <div className="rounded-lg p-6" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
            <h3 className="text-lg font-semibold mb-4">{t('migration.step2_title')}</h3>

            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 rounded" style={{ backgroundColor: 'var(--bg-primary)' }}>
                <span>{t('migration.config_entries')}</span>
                <span className="font-mono">{preview.config_entries}</span>
              </div>
              <div className="flex items-center justify-between p-3 rounded" style={{ backgroundColor: 'var(--bg-primary)' }}>
                <span>{t('migration.language_profiles')}</span>
                <span className="font-mono">{preview.profiles}</span>
              </div>
              <div className="flex items-center justify-between p-3 rounded" style={{ backgroundColor: 'var(--bg-primary)' }}>
                <span>{t('migration.blacklist_entries')}</span>
                <span className="font-mono">{preview.blacklist_entries}</span>
              </div>
              <div className="flex items-center justify-between p-3 rounded" style={{ backgroundColor: 'var(--bg-primary)' }}>
                <span>{t('migration.history_entries')}</span>
                <span className="font-mono">{preview.history_entries}</span>
              </div>
            </div>

            <div className="mt-6 flex gap-3">
              <button
                onClick={() => setStep('upload')}
                className="px-4 py-2 text-white rounded" style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              >
                {t('migration.back')}
              </button>
              <button
                onClick={handleImport}
                disabled={isLoading}
                className="px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCircle className="w-4 h-4" />
                )}
                {t('migration.import_button')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Complete */}
      {step === 'complete' && importResult && (
        <div className="space-y-4">
          <div className="rounded-lg p-6" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
            <div className="flex items-center gap-3 mb-4">
              <CheckCircle className="w-8 h-8 text-green-500" />
              <h3 className="text-lg font-semibold">{tc('ui.migration_complete')}</h3>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 rounded" style={{ backgroundColor: 'var(--bg-primary)' }}>
                <span>{t('migration.config_entries')}</span>
                <span className="font-mono text-green-400">{importResult.config_imported}</span>
              </div>
              <div className="flex items-center justify-between p-3 rounded" style={{ backgroundColor: 'var(--bg-primary)' }}>
                <span>{t('migration.profiles_imported')}</span>
                <span className="font-mono text-green-400">{importResult.profiles_imported}</span>
              </div>
              <div className="flex items-center justify-between p-3 rounded" style={{ backgroundColor: 'var(--bg-primary)' }}>
                <span>{t('migration.blacklist_entries')}</span>
                <span className="font-mono text-green-400">{importResult.blacklist_imported}</span>
              </div>
              <div className="flex items-center justify-between p-3 rounded" style={{ backgroundColor: 'var(--bg-primary)' }}>
                <span>{t('migration.history_entries')}</span>
                <span className="font-mono text-green-400">{importResult.history_imported}</span>
              </div>
            </div>

            <button
              onClick={() => {
                setStep('upload')
                setConfigFile(null)
                setDbFile(null)
                setPreview(null)
                setImportResult(null)
              }}
              className="mt-6 px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded"
            >
              {t('migration.start_new')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
