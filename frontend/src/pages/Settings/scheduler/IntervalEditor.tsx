import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TriggerInterval } from '@/lib/types'

type Unit = 'seconds' | 'minutes' | 'hours'

export function IntervalEditor({
  value,
  onChange,
}: {
  value: TriggerInterval
  onChange: (v: TriggerInterval) => void
}) {
  const { t } = useTranslation('settings')
  const initialUnit: Unit = value.hours
    ? 'hours'
    : value.minutes
      ? 'minutes'
      : 'seconds'
  const initialN = value.hours ?? value.minutes ?? value.seconds ?? 1
  const [unit, setUnit] = useState<Unit>(initialUnit)
  const [n, setN] = useState(initialN)

  useEffect(() => {
    const base: TriggerInterval = { type: 'interval' }
    base[unit] = Math.max(1, n)
    onChange(base)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n, unit])

  return (
    <div className="flex items-end gap-2">
      <label className="flex flex-col text-sm">
        <span className="mb-1 text-muted">{t('scheduler.interval_n')}</span>
        <input
          type="number"
          min={1}
          value={n}
          onChange={(e) => setN(Math.max(1, Number(e.target.value) || 1))}
          className="w-24 rounded-md border border-border bg-surface px-2 py-1"
        />
      </label>
      <label className="flex flex-col text-sm">
        <span className="mb-1 text-muted">{t('scheduler.interval_unit')}</span>
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value as Unit)}
          className="rounded-md border border-border bg-surface px-2 py-1"
        >
          <option value="seconds">{t('scheduler.unit_seconds')}</option>
          <option value="minutes">{t('scheduler.unit_minutes')}</option>
          <option value="hours">{t('scheduler.unit_hours')}</option>
        </select>
      </label>
    </div>
  )
}
