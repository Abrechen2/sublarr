import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CronExpressionParser } from 'cron-parser'
import type { TriggerCron } from '@/lib/types'

type Mode = 'daily' | 'weekly' | 'advanced'

const DAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']

export function CronEditor({
  value,
  onChange,
}: {
  value: TriggerCron
  onChange: (v: TriggerCron) => void
}) {
  const { t } = useTranslation('settings')
  const [mode, setMode] = useState<Mode>(
    value.day_of_week ? 'weekly' : 'daily',
  )
  const [hour, setHour] = useState(Number(value.hour ?? '3'))
  const [minute, setMinute] = useState(Number(value.minute ?? '0'))
  const [days, setDays] = useState<string[]>(
    (value.day_of_week ?? '').split(',').filter(Boolean),
  )
  const [expression, setExpression] = useState('0 3 * * *')

  useEffect(() => {
    if (mode === 'daily') {
      onChange({ type: 'cron', hour: String(hour), minute: String(minute) })
    } else if (mode === 'weekly') {
      onChange({
        type: 'cron',
        hour: String(hour),
        minute: String(minute),
        day_of_week: days.join(',') || 'mon',
      })
    } else {
      // Advanced mode: parse expression at save time; emit as-is for now
      // (parent modal passes expression through; backend validates)
      const parts = expression.trim().split(/\s+/)
      if (parts.length === 5) {
        const [min, hr, , , dow] = parts
        onChange({
          type: 'cron',
          minute: min,
          hour: hr,
          day_of_week: dow === '*' ? undefined : dow,
        })
      } else {
        onChange({ type: 'cron' })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, hour, minute, days, expression])

  const nextFires = useMemo(() => {
    try {
      const expr =
        mode === 'advanced'
          ? expression
          : mode === 'daily'
            ? `${minute} ${hour} * * *`
            : `${minute} ${hour} * * ${days.join(',') || '*'}`
      const interval = CronExpressionParser.parse(expr, { tz: 'UTC' })
      return [0, 1, 2].map(() => interval.next().toDate().toISOString())
    } catch {
      return []
    }
  }, [mode, hour, minute, days, expression])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        {(['daily', 'weekly', 'advanced'] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded-md px-3 py-1 text-sm ${
              mode === m ? 'bg-accent text-white' : 'border border-border'
            }`}
          >
            {t(`scheduler.cron_mode_${m}`)}
          </button>
        ))}
      </div>

      {mode !== 'advanced' && (
        <div className="flex items-center gap-2 text-sm">
          <input
            type="number"
            min={0}
            max={23}
            value={hour}
            onChange={(e) =>
              setHour(Math.min(23, Math.max(0, Number(e.target.value))))
            }
            className="w-16 rounded-md border border-border bg-surface px-2 py-1"
          />
          <span>:</span>
          <input
            type="number"
            min={0}
            max={59}
            value={minute}
            onChange={(e) =>
              setMinute(Math.min(59, Math.max(0, Number(e.target.value))))
            }
            className="w-16 rounded-md border border-border bg-surface px-2 py-1"
          />
          <span className="text-muted">UTC</span>
        </div>
      )}

      {mode === 'weekly' && (
        <div className="flex flex-wrap gap-1">
          {DAYS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() =>
                setDays((prev) =>
                  prev.includes(d)
                    ? prev.filter((x) => x !== d)
                    : [...prev, d],
                )
              }
              className={`rounded-full px-3 py-1 text-xs ${
                days.includes(d)
                  ? 'bg-accent text-white'
                  : 'border border-border'
              }`}
            >
              {t(`scheduler.dow_${d}`)}
            </button>
          ))}
        </div>
      )}

      {mode === 'advanced' && (
        <input
          type="text"
          value={expression}
          onChange={(e) => setExpression(e.target.value)}
          className="w-full rounded-md border border-border bg-surface px-2 py-1 font-mono text-sm"
          placeholder="0 3 * * *"
        />
      )}

      <div className="rounded-md bg-elevated p-2 text-xs text-muted">
        <div className="mb-1">{t('scheduler.next_fires')}</div>
        {nextFires.length === 0 ? (
          <div className="text-error">{t('scheduler.cron_invalid')}</div>
        ) : (
          <ul className="list-inside list-disc">
            {nextFires.map((ts) => (
              <li key={ts} className="font-mono">
                {new Date(ts).toLocaleString()}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
