/**
 * MigrationTab - Bazarr migration wizard.
 *
 * Upload Bazarr's config and/or database → the server previews what it would
 * import → confirm sends the same files again with confirm=true. Until
 * 2026-09-27 this page simulated both steps with made-up counts.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Upload, CheckCircle, FileText, Database } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { BazarrImportPreview, WarningList } from '@/components/settings/BazarrImportPreview'
import { useBazarrMigration, useConfirmBazarrImport } from '@/hooks/useIntegrationApi'
import type { BazarrMigrationPreview, BazarrMigrationResult } from '@/lib/types'

interface ServerError {
  response?: { data?: { error?: string; warnings?: string[] } }
}

function serverError(err: unknown): { message?: string; warnings: string[] } {
  const data = (err as ServerError)?.response?.data
  return { message: data?.error, warnings: data?.warnings ?? [] }
}

const INPUT_CLASS =
  'block w-full text-sm text-secondary file:mr-4 file:rounded file:border-0 file:bg-accent file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-accent-hover'

export function MigrationTab() {
  const { t } = useTranslation('settings')
  const { t: tc } = useTranslation('common')
  const analyze = useBazarrMigration()
  const confirm = useConfirmBazarrImport()

  const [configFile, setConfigFile] = useState<File | null>(null)
  const [dbFile, setDbFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<BazarrMigrationPreview | null>(null)
  const [result, setResult] = useState<BazarrMigrationResult | null>(null)
  const [errorWarnings, setErrorWarnings] = useState<string[]>([])

  const files = [configFile, dbFile].filter((f): f is File => f !== null)

  const reset = () => {
    setConfigFile(null)
    setDbFile(null)
    setPreview(null)
    setResult(null)
    setErrorWarnings([])
  }

  const handleAnalyze = () => {
    setErrorWarnings([])
    analyze.mutate(files, {
      onSuccess: (data) => setPreview(data),
      onError: (err) => {
        const { message, warnings } = serverError(err)
        setErrorWarnings(warnings)
        toast(message ?? t('migration.analysis_failed'), 'error')
      },
    })
  }

  const handleConfirm = () => {
    confirm.mutate(files, {
      onSuccess: (data) => {
        setResult(data)
        setPreview(null)
        toast(t('migration.completed'), 'success')
      },
      onError: (err) => toast(serverError(err).message ?? t('migration.failed'), 'error'),
    })
  }

  return (
    <div className="space-y-6">
      <div className="mb-6 rounded-lg border border-border bg-surface p-4">
        <h3 className="mb-1 text-sm font-semibold text-foreground">{tc('ui.bazarr_migration')}</h3>
        <p className="text-sm text-secondary">{t('migration.intro_desc')}</p>
      </div>

      <div>
        <h2 className="mb-2 text-2xl font-bold">{t('integrations.bazarr.title')}</h2>
        <p className="text-sm text-secondary">{t('migration.subtitle')}</p>
      </div>

      {!preview && !result && (
        <div className="rounded-lg border border-border bg-surface p-6">
          <h3 className="mb-4 text-lg font-semibold">{t('migration.step1_title')}</h3>

          <div className="space-y-4">
            <FileField
              icon={<FileText className="mr-2 inline h-4 w-4" />}
              label={t('migration.config_file_label')}
              accept=".yaml,.yml,.ini,.cfg,.zip"
              file={configFile}
              onChange={setConfigFile}
              testId="bazarr-config-input"
            />
            <FileField
              icon={<Database className="mr-2 inline h-4 w-4" />}
              label={t('migration.db_file_label')}
              accept=".db,.sqlite,.sqlite3"
              file={dbFile}
              onChange={setDbFile}
              testId="bazarr-db-input"
            />
          </div>

          {errorWarnings.length > 0 && (
            <div className="mt-4">
              <WarningList title={t('migration.warnings_title')} warnings={errorWarnings} />
            </div>
          )}

          <button
            type="button"
            onClick={handleAnalyze}
            disabled={analyze.isPending || files.length === 0}
            data-testid="bazarr-analyze"
            className="mt-6 flex items-center gap-2 rounded bg-accent px-4 py-2 text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {analyze.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {t('migration.analyze_button')}
          </button>
        </div>
      )}

      {preview && (
        <div className="space-y-2">
          <h3 className="text-lg font-semibold">{t('migration.step2_title')}</h3>
          <BazarrImportPreview
            preview={preview}
            onConfirm={handleConfirm}
            onCancel={() => setPreview(null)}
            isPending={confirm.isPending}
          />
        </div>
      )}

      {result && (
        <div className="space-y-4 rounded-lg border border-border bg-surface p-6" data-testid="bazarr-result">
          <div className="flex items-center gap-3">
            <CheckCircle className="h-8 w-8 text-success" />
            <h3 className="text-lg font-semibold">{tc('ui.migration_complete')}</h3>
          </div>

          <div className="space-y-3">
            <ResultRow label={t('migration.imported_settings')} value={result.config_imported} />
            <ResultRow label={t('migration.profiles_imported')} value={result.profiles_imported} />
            <ResultRow label={t('migration.imported_blacklist')} value={result.blacklist_imported} />
          </div>

          {result.warnings.length > 0 && (
            <WarningList title={t('migration.warnings_title')} warnings={result.warnings} />
          )}

          <button
            type="button"
            onClick={reset}
            className="rounded bg-accent px-4 py-2 text-white hover:bg-accent-hover"
          >
            {t('migration.start_new')}
          </button>
        </div>
      )}
    </div>
  )
}

function FileField({
  icon,
  label,
  accept,
  file,
  onChange,
  testId,
}: {
  icon: React.ReactNode
  label: string
  accept: string
  file: File | null
  onChange: (file: File | null) => void
  testId: string
}) {
  const { t } = useTranslation('settings')
  return (
    <div>
      <label className="mb-2 block text-sm font-medium">
        {icon}
        {label}
        <input
          type="file"
          accept={accept}
          onChange={(e) => onChange(e.target.files?.[0] ?? null)}
          data-testid={testId}
          className={`mt-2 ${INPUT_CLASS}`}
        />
      </label>
      {file && <p className="mt-2 text-sm text-secondary">{t('migration.selected', { name: file.name })}</p>}
    </div>
  )
}

function ResultRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between rounded bg-page p-3">
      <span>{label}</span>
      <span className="font-mono text-success">{value}</span>
    </div>
  )
}
