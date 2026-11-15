import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Sparkles, ChevronDown, ChevronRight } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { useGlossaryPresets, useImportGlossaryPreset } from '@/hooks/useApi'
import type { GlossaryEntry } from '@/api/translation'

// ─── Glossary presets ───────────────────────────────────────────────────────
// Bundled term lists the user can import into the global glossary. Nothing is
// applied until the user clicks import.

export function GlossaryPresetsCard({ entries }: { entries: GlossaryEntry[] }) {
  const { t } = useTranslation('settings')
  const { data } = useGlossaryPresets()
  const importPreset = useImportGlossaryPreset()
  const [openId, setOpenId] = useState<string | null>(null)

  const presets = data?.presets ?? []
  if (presets.length === 0) return null

  const missingCount = (preset: (typeof presets)[number]) => {
    const have = new Set(
      entries
        .filter((e) => !e.target_language || e.target_language === preset.target_language)
        .map((e) => e.source_term.trim().toLowerCase()),
    )
    return preset.entries.filter((e) => !have.has(e.source_term.trim().toLowerCase())).length
  }

  const handleImport = (presetId: string) => {
    importPreset.mutate(presetId, {
      onSuccess: (res) => toast(t('glossary_presets.toast_imported', { added: res.added, skipped: res.skipped })),
      onError: () => toast(t('glossary_presets.toast_import_failed'), 'error'),
    })
  }

  return (
    <div
      className="rounded-lg p-4 space-y-3 bg-surface border border-border"
      data-testid="glossary-presets"
    >
      <div className="flex items-center gap-2">
        <Sparkles size={14} className="text-accent" />
        <h3 className="text-sm font-semibold text-foreground">
          {t('glossary_presets.title')}
        </h3>
      </div>
      <p className="text-xs text-secondary">
        {t('glossary_presets.help')}
      </p>
      {presets.map((preset) => {
        const missing = missingCount(preset)
        const open = openId === preset.id
        return (
          <div key={preset.id} className="rounded-md p-3 border border-border">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setOpenId(open ? null : preset.id)}
                className="flex items-center gap-1.5 text-sm font-medium text-left text-foreground"
                aria-expanded={open}
              >
                {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                {t(`glossary_presets.name.${preset.id}`, { defaultValue: preset.name })}
                <span className="text-xs font-normal text-muted">
                  {t('glossary_presets.term_count', { count: preset.entries.length })}
                </span>
              </button>
              <button
                type="button"
                onClick={() => handleImport(preset.id)}
                disabled={missing === 0 || importPreset.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white bg-accent disabled:opacity-50"
                data-testid={`glossary-preset-import-${preset.id}`}
              >
                {importPreset.isPending && importPreset.variables === preset.id && (
                  <Loader2 size={12} className="animate-spin" />
                )}
                {missing === 0
                  ? t('glossary_presets.all_imported')
                  : t('glossary_presets.import', { count: missing })}
              </button>
            </div>
            {open && (
              <ul className="mt-2 grid gap-x-4 gap-y-0.5 text-xs sm:grid-cols-2 text-secondary">
                {preset.entries.map((e) => (
                  <li key={e.source_term}>
                    {e.source_term} → <span className="text-foreground">{e.target_term}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}
