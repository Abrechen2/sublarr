import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Layers } from 'lucide-react'
import { combineEpisodeSubtitles } from '@/api/library'
import type { CombineSubtitlesPayload } from '@/api/library'
import { LanguagePillSelector } from '@/components/settings/LanguagePillSelector'
import { LANGUAGE_OPTIONS } from '@/styles/settingsShared'
import { toast } from '@/components/shared/Toast'

interface CombineDialogProps {
  open: boolean
  episodeId: number
  episodeTitle: string
  /** Languages that already exist as sidecars for this episode. */
  availableLanguages: string[]
  /** Profile target languages (offered as combine candidates even if not present). */
  targetLanguages: string[]
  seriesId: number
  onClose: () => void
}

function labelFor(code: string): string {
  return LANGUAGE_OPTIONS.find((o) => o.value === code)?.label ?? code
}

export function CombineDialog({
  open,
  episodeId,
  episodeTitle,
  availableLanguages,
  targetLanguages,
  seriesId,
  onClose,
}: CombineDialogProps) {
  const { t } = useTranslation('library')
  const queryClient = useQueryClient()

  // Candidate languages = everything present or targeted, present ones first.
  const candidates = useMemo(() => {
    const seen = new Set<string>()
    const ordered = [...availableLanguages, ...targetLanguages].filter((l) => {
      if (!l || seen.has(l)) return false
      seen.add(l)
      return true
    })
    return ordered
  }, [availableLanguages, targetLanguages])

  const [languages, setLanguages] = useState<string[]>(() =>
    availableLanguages.slice(0, 3).length >= 2
      ? availableLanguages.slice(0, 3)
      : candidates.slice(0, 2),
  )
  const [format, setFormat] = useState<'ass' | 'srt'>('ass')
  const [translateMissing, setTranslateMissing] = useState(false)

  const missing = languages.filter((l) => !availableLanguages.includes(l))

  const mutation = useMutation({
    mutationFn: (payload: CombineSubtitlesPayload) => combineEpisodeSubtitles(episodeId, payload),
    onSuccess: () => {
      toast(t('combine_dialog.success'))
      void queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
      onClose()
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { error?: string } } })?.response?.data?.error ??
        t('combine_dialog.failed')
      toast(msg, 'error')
    },
  })

  if (!open) return null

  const canSubmit = languages.length >= 2 && !mutation.isPending

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="combine-dialog-title"
        className="w-full max-w-md rounded-lg"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div
          className="flex items-center gap-2 px-4 py-3"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <Layers size={15} style={{ color: 'var(--accent)' }} />
          <h2
            id="combine-dialog-title"
            className="font-semibold text-sm"
            style={{ color: 'var(--text-primary)' }}
          >
            {t('combine_dialog.title')}
          </h2>
        </div>

        <div className="px-4 py-3 space-y-3">
          <p className="text-[11px] text-muted truncate">{episodeTitle}</p>

          {/* Languages */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-secondary">
              {t('combine_dialog.languages_label')}
            </label>
            <LanguagePillSelector
              value={languages}
              options={candidates.map((l) => ({ value: l, label: labelFor(l) }))}
              onChange={setLanguages}
            />
            <p className="text-[11px] text-muted">{t('combine_dialog.languages_help')}</p>
          </div>

          {/* Format */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-secondary">
              {t('combine_dialog.format_label')}
            </label>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value as 'ass' | 'srt')}
              className="w-full px-2.5 py-1.5 rounded text-xs"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            >
              <option value="ass">ASS</option>
              <option value="srt">SRT</option>
            </select>
          </div>

          {/* Translate missing */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={translateMissing}
              onChange={(e) => setTranslateMissing(e.target.checked)}
              style={{ accentColor: 'var(--accent)' }}
            />
            <span className="text-xs text-secondary">{t('combine_dialog.translate_missing')}</span>
          </label>
          {missing.length > 0 && !translateMissing && (
            <p className="text-[11px]" style={{ color: 'var(--warning)' }}>
              {t('combine_dialog.missing_warn', { languages: missing.map(labelFor).join(', ') })}
            </p>
          )}
        </div>

        <div
          className="flex justify-end gap-2 px-4 py-3"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <button
            onClick={onClose}
            className="rounded px-3 py-1.5 text-xs"
            style={{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
          >
            {t('combine_dialog.cancel')}
          </button>
          <button
            onClick={() =>
              mutation.mutate({ languages, format, translate_missing: translateMissing })
            }
            disabled={!canSubmit}
            className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium text-white"
            style={{ backgroundColor: 'var(--accent)', opacity: canSubmit ? 1 : 0.5 }}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Layers size={12} />}
            {t('combine_dialog.combine')}
          </button>
        </div>
      </div>
    </div>
  )
}
