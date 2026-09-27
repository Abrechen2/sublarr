/**
 * BazarrImportPreview — what a Bazarr import would write, before it writes it.
 *
 * Shared by the migration wizard (System → Migration) and the "Bazarr
 * Migration" button in API Keys. Values come from the server preview; secrets
 * arrive masked on both sides ("abcd***").
 */

import { useTranslation } from 'react-i18next'
import { Check, Loader2, X } from 'lucide-react'
import type { BazarrMigrationPreview } from '@/lib/types'

interface Props {
  preview: BazarrMigrationPreview
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}

export function BazarrImportPreview({ preview, onConfirm, onCancel, isPending }: Props) {
  const { t } = useTranslation('settings')
  const overwrites = preview.config_entries.some((e) => e.current_value)

  return (
    <div className="space-y-4 rounded-lg border border-accent-dim bg-page p-4" data-testid="bazarr-preview">
      <div className="text-sm font-semibold text-foreground">{t('apiKeys.bazarr_preview_title')}</div>

      {preview.warnings.length > 0 && <WarningList title={t('migration.warnings_title')} warnings={preview.warnings} />}

      <section className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">{t('migration.settings_title')}</h4>
        {preview.config_entries.length === 0 ? (
          <p className="text-xs text-muted">{t('migration.no_settings')}</p>
        ) : (
          <ul className="max-h-56 space-y-1 overflow-auto rounded border border-border bg-surface px-3 py-2 font-mono text-xs text-secondary">
            {preview.config_entries.map((entry) => (
              <li key={entry.key} className="flex flex-wrap items-center gap-x-2 py-0.5" data-testid={`bazarr-entry-${entry.key}`}>
                <span className="text-accent">{entry.key}</span>
                <span className="text-muted">=</span>
                <span className="break-all">{entry.value}</span>
                {entry.current_value && (
                  <span className="text-[10px] text-warning">
                    ({t('migration.current_value', { value: entry.current_value })})
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {overwrites && <p className="text-xs text-muted">{t('migration.overwrite_hint')}</p>}
      </section>

      {preview.profiles.length > 0 && (
        <section className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">
            {t('migration.language_profiles')} ({preview.profiles.length})
          </h4>
          <ul className="space-y-1 text-xs text-secondary">
            {preview.profiles.map((p, i) => (
              <li key={`${p.name}-${i}`}>
                <span className="text-foreground">{p.name}</span>
                {p.languages.length > 0 && <span className="font-mono text-muted"> — {p.languages.join(', ')}</span>}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">{t('migration.profiles_hint')}</p>
        </section>
      )}

      {preview.blacklist_count > 0 && (
        <div className="flex items-center justify-between rounded bg-surface px-3 py-2 text-xs">
          <span className="text-secondary">{t('migration.blacklist_entries')}</span>
          <span className="font-mono text-foreground">{preview.blacklist_count}</span>
        </div>
      )}

      <p className="text-xs text-muted">{t('migration.not_imported')}</p>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={isPending}
          data-testid="bazarr-confirm"
          className="flex items-center gap-1.5 rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
          {t('apiKeys.confirm_import')}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={isPending}
          className="flex items-center gap-1 rounded px-3 py-1.5 text-xs text-muted hover:text-foreground"
        >
          <X size={12} />
          {t('migration.cancel')}
        </button>
      </div>
    </div>
  )
}

export function WarningList({ title, warnings }: { title: string; warnings: string[] }) {
  return (
    <div className="space-y-1" data-testid="bazarr-warnings">
      <div className="text-xs font-semibold text-warning">{title}</div>
      {warnings.map((w, i) => (
        <div key={i} className="rounded bg-warning-bg px-2 py-1 text-xs text-warning">
          {w}
        </div>
      ))}
    </div>
  )
}
