import { useTranslation } from 'react-i18next'
import { useEventCatalog } from '@/hooks/useApi'
import { ToggleLeft, ToggleRight, Clock } from 'lucide-react'
import type { QuietHoursConfig as QuietHoursConfigType } from '@/lib/types'

const DAYS = [
  { value: 0, label: 'Mon' },
  { value: 1, label: 'Tue' },
  { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' },
  { value: 4, label: 'Fri' },
  { value: 5, label: 'Sat' },
  { value: 6, label: 'Sun' },
]

interface QuietHoursEditorProps {
  config: Partial<QuietHoursConfigType>
  onChange: (update: Partial<QuietHoursConfigType>) => void
}

function TimelineBar({ startTime, endTime }: { startTime: string; endTime: string }) {
  const parseMinutes = (t: string) => {
    const [h, m] = t.split(':').map(Number)
    return (h ?? 0) * 60 + (m ?? 0)
  }
  const start = parseMinutes(startTime || '22:00')
  const end = parseMinutes(endTime || '08:00')
  const total = 24 * 60

  // Handle overnight ranges
  const isOvernight = start > end

  return (
    <div className="relative h-6 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {isOvernight ? (
        <>
          <div
            className="absolute top-0 bottom-0 rounded-l-full"
            style={{
              left: 0,
              width: `${(end / total) * 100}%`,
              backgroundColor: 'var(--accent)',
              opacity: 0.3,
            }}
          />
          <div
            className="absolute top-0 bottom-0 rounded-r-full"
            style={{
              left: `${(start / total) * 100}%`,
              right: 0,
              backgroundColor: 'var(--accent)',
              opacity: 0.3,
            }}
          />
        </>
      ) : (
        <div
          className="absolute top-0 bottom-0"
          style={{
            left: `${(start / total) * 100}%`,
            width: `${((end - start) / total) * 100}%`,
            backgroundColor: 'var(--accent)',
            opacity: 0.3,
          }}
        />
      )}
      {/* Hour markers */}
      {[0, 6, 12, 18].map((h) => (
        <div
          key={h}
          className="absolute top-0 bottom-0 w-px"
          style={{ left: `${(h / 24) * 100}%`, backgroundColor: 'var(--border)' }}
        />
      ))}
      {/* Labels */}
      <div className="absolute inset-0 flex items-center justify-between px-2 text-[9px] font-medium" style={{ color: 'var(--text-muted)' }}>
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>24:00</span>
      </div>
    </div>
  )
}

export function QuietHoursEditor({ config, onChange }: QuietHoursEditorProps) {
  const { t } = useTranslation('settings')
  const { data: catalogData } = useEventCatalog()

  const eventTypes = catalogData?.events
    ? (catalogData.events as { name: string; label: string }[])
    : []

  const toggleDay = (day: number) => {
    const current = config.days_of_week ?? []
    const updated = current.includes(day)
      ? current.filter((d) => d !== day)
      : [...current, day].sort()
    onChange({ days_of_week: updated })
  }

  const toggleException = (eventName: string) => {
    const current = config.exception_events ?? []
    const updated = current.includes(eventName)
      ? current.filter((e) => e !== eventName)
      : [...current, eventName]
    onChange({ exception_events: updated })
  }

  return (
    <div className="space-y-3">
      {/* Name */}
      <div className="space-y-1">
        <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {t('notifications.quietHours.name', 'Name')}
        </label>
        <input
          type="text"
          value={config.name ?? ''}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder="e.g. Nighttime"
          className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        />
      </div>

      {/* Time Range */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="flex items-center gap-1.5 text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            <Clock size={12} />
            {t('notifications.quietHours.startTime', 'Start Time')}
          </label>
          <input
            type="time"
            value={config.start_time ?? '22:00'}
            onChange={(e) => onChange({ start_time: e.target.value })}
            className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </div>
        <div className="space-y-1">
          <label className="flex items-center gap-1.5 text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            <Clock size={12} />
            {t('notifications.quietHours.endTime', 'End Time')}
          </label>
          <input
            type="time"
            value={config.end_time ?? '08:00'}
            onChange={(e) => onChange({ end_time: e.target.value })}
            className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </div>
      </div>

      {/* Timeline Visualization */}
      <TimelineBar startTime={config.start_time ?? '22:00'} endTime={config.end_time ?? '08:00'} />

      {/* Days of Week */}
      <div className="space-y-1">
        <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {t('notifications.quietHours.days', 'Active Days')}
        </label>
        <div className="flex gap-1.5">
          {DAYS.map((day) => {
            const active = (config.days_of_week ?? []).includes(day.value)
            return (
              <button
                key={day.value}
                onClick={() => toggleDay(day.value)}
                className="px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
                style={{
                  backgroundColor: active ? 'var(--accent)' : 'var(--bg-primary)',
                  color: active ? 'white' : 'var(--text-muted)',
                  border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                }}
              >
                {day.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Exception Events */}
      {eventTypes.length > 0 && (
        <div className="space-y-1">
          <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            {t('notifications.quietHours.exceptions', 'Exception Events (always send)')}
          </label>
          <div className="flex flex-wrap gap-1.5">
            {eventTypes.slice(0, 10).map((evt) => {
              const active = (config.exception_events ?? []).includes(evt.name)
              return (
                <button
                  key={evt.name}
                  onClick={() => toggleException(evt.name)}
                  className="px-2 py-1 rounded text-[10px] font-medium transition-all duration-150"
                  style={{
                    backgroundColor: active ? 'var(--warning-bg, rgba(234,179,8,0.15))' : 'var(--bg-primary)',
                    color: active ? 'var(--warning)' : 'var(--text-muted)',
                    border: `1px solid ${active ? 'var(--warning)' : 'var(--border)'}`,
                  }}
                >
                  {evt.label || evt.name}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Enabled Toggle */}
      <div className="flex items-center gap-2">
        <button onClick={() => onChange({ enabled: !config.enabled })} className="flex items-center gap-1.5">
          {config.enabled !== false ? (
            <ToggleRight size={20} style={{ color: 'var(--accent)' }} />
          ) : (
            <ToggleLeft size={20} style={{ color: 'var(--text-muted)' }} />
          )}
        </button>
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {config.enabled !== false ? 'Enabled' : 'Disabled'}
        </span>
      </div>
    </div>
  )
}
