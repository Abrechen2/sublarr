import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export interface SeriesOverrideSettingsProps {
  readonly seriesId: number
  readonly initial: {
    priority_override: string | null
    min_attempts_per_day: number
    subtitle_format_requirement?: string | null
  }
  readonly onSave: (payload: {
    priority_override: string | null
    min_attempts_per_day: number
    subtitle_format_requirement: string | null
  }) => void
}

/**
 * Per-series scheduler override panel.
 *
 * Lets a power user override the global priority tier (premium/standard/backlog)
 * and enforce a minimum number of search attempts per day for a single series.
 * Inherit (empty string) maps back to `null` so the backend falls through to
 * the global defaults. The save button stays disabled until at least one field
 * differs from `initial` to prevent accidental no-op saves.
 */
export default function SeriesOverrideSettings({
  seriesId,
  initial,
  onSave,
}: SeriesOverrideSettingsProps) {
  const { t } = useTranslation('settings')
  const [priority, setPriority] = useState<string>(initial.priority_override ?? '')
  const [min, setMin] = useState<number>(initial.min_attempts_per_day)
  const [formatReq, setFormatReq] = useState<string>(initial.subtitle_format_requirement ?? '')

  const dirty =
    priority !== (initial.priority_override ?? '') ||
    min !== initial.min_attempts_per_day ||
    formatReq !== (initial.subtitle_format_requirement ?? '')

  const handleSave = () => {
    onSave({
      priority_override: priority === '' ? null : priority,
      min_attempts_per_day: min,
      subtitle_format_requirement: formatReq === '' ? null : formatReq,
    })
  }

  return (
    <section data-testid={`series-override-${seriesId}`} className="space-y-3">
      <h4 className="text-sm font-semibold text-foreground">{t('series_override.title')}</h4>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label={t('series_override.priority')}>
          <select
            data-testid="priority-override-select"
            className={INPUT}
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="">{t('series_override.inherit')}</option>
            <option value="premium">{t('series_override.premium')}</option>
            <option value="standard">{t('series_override.standard')}</option>
            <option value="backlog">{t('series_override.backlog')}</option>
          </select>
        </Field>
        <Field label={t('series_override.min_attempts')}>
          <input
            type="number"
            data-testid="min-attempts-input"
            className={INPUT}
            min={0}
            max={50}
            value={min}
            onChange={(e) => {
              const v = Number(e.target.value)
              const clamped = Math.max(0, Math.min(50, Number.isFinite(v) ? v : 0))
              setMin(clamped)
            }}
          />
        </Field>
        <Field label={t('series_override.format_requirement')}>
          <select
            data-testid="format-requirement-select"
            className={INPUT}
            value={formatReq}
            onChange={(e) => setFormatReq(e.target.value)}
          >
            <option value="">{t('series_override.format_inherit')}</option>
            <option value="require_ass">{t('series_override.format_require_ass')}</option>
          </select>
        </Field>
      </div>
      <div className="flex justify-end">
        <button
          type="button"
          data-testid="save-override"
          disabled={!dirty}
          onClick={handleSave}
          className="rounded bg-accent px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t('series_override.save')}
        </button>
      </div>
    </section>
  )
}

const INPUT =
  'w-full rounded border border-border bg-page px-2.5 py-1.5 text-sm text-foreground focus:outline-none'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-secondary">{label}</span>
      {children}
    </label>
  )
}
