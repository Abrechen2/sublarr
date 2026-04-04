type Schedule = 'manual' | 'daily' | 'weekly' | 'after_scan'

interface SchedulePickerProps {
  value: Schedule
  onChange: (schedule: Schedule) => void
}

const OPTIONS: { value: Schedule; label: string }[] = [
  { value: 'manual', label: 'Manuell' },
  { value: 'daily', label: 'Täglich (03:00)' },
  { value: 'weekly', label: 'Wöchentlich' },
  { value: 'after_scan', label: 'Nach jedem Scan' },
]

export function SchedulePicker({ value, onChange }: SchedulePickerProps) {
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
          {opt.label}
        </button>
      ))}
    </div>
  )
}
