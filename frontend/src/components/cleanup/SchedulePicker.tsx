import { useTranslation } from 'react-i18next'

type Schedule = 'manual' | 'daily' | 'weekly' | 'after_scan'

interface SchedulePickerProps {
  value: Schedule
  onChange: (schedule: Schedule) => void
}

// Keys are resolved at render time so the language switch applies immediately.
const OPTIONS: { value: Schedule; labelKey: string }[] = [
  { value: 'manual', labelKey: 'cleanup_detail.schedule_options.manual' },
  { value: 'daily', labelKey: 'cleanup_detail.schedule_options.daily' },
  { value: 'weekly', labelKey: 'cleanup_detail.schedule_options.weekly' },
  { value: 'after_scan', labelKey: 'cleanup_detail.schedule_options.after_scan' },
]

export function SchedulePicker({ value, onChange }: SchedulePickerProps) {
  const { t } = useTranslation('common')
  return (
    <div className="flex flex-wrap gap-2">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="px-3 py-1.5 rounded-full text-xs font-medium transition-all"
          style={{
            background: value === opt.value ? 'var(--accent-bg)' : 'var(--bg-primary)',
            border: `1px solid ${value === opt.value ? 'var(--accent)' : 'var(--border)'}`,
            color: value === opt.value ? 'var(--accent)' : 'var(--text-muted)',
          }}
        >
          {t(opt.labelKey)}
        </button>
      ))}
    </div>
  )
}
