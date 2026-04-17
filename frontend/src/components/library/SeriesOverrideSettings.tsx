import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface SeriesOverrideSettingsProps {
  readonly seriesId: number
  readonly initial: { priority_override: string | null; min_attempts_per_day: number }
  readonly onSave: (payload: {
    priority_override: string | null
    min_attempts_per_day: number
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

  const dirty =
    priority !== (initial.priority_override ?? '') ||
    min !== initial.min_attempts_per_day

  const handleSave = () => {
    onSave({
      priority_override: priority === '' ? null : priority,
      min_attempts_per_day: min,
    })
  }

  return (
    <section data-testid={`series-override-${seriesId}`}>
      <h4 style={{ margin: 0 }}>{t('series_override.title')}</h4>
      <label>
        {t('series_override.priority')}
        <select
          data-testid="priority-override-select"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
        >
          <option value="">{t('series_override.inherit')}</option>
          <option value="premium">{t('series_override.premium')}</option>
          <option value="standard">{t('series_override.standard')}</option>
          <option value="backlog">{t('series_override.backlog')}</option>
        </select>
      </label>
      <label>
        {t('series_override.min_attempts')}
        <input
          type="number"
          data-testid="min-attempts-input"
          min={0}
          max={50}
          value={min}
          onChange={(e) => {
            const v = Number(e.target.value)
            const clamped = Math.max(0, Math.min(50, Number.isFinite(v) ? v : 0))
            setMin(clamped)
          }}
        />
      </label>
      <button data-testid="save-override" disabled={!dirty} onClick={handleSave}>
        {t('series_override.save')}
      </button>
    </section>
  )
}
