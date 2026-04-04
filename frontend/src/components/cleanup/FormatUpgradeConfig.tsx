type KeepFormat = 'any' | 'ass' | 'srt'

interface FormatUpgradeConfigProps {
  value: KeepFormat
  onChange: (format: KeepFormat) => void
}

const OPTIONS: { value: KeepFormat; label: string; desc: string }[] = [
  { value: 'any', label: 'Beide behalten', desc: 'SRT und ASS gleichzeitig' },
  { value: 'ass', label: 'ASS bevorzugen', desc: 'SRT löschen wenn ASS vorhanden' },
  { value: 'srt', label: 'SRT bevorzugen', desc: 'ASS löschen wenn SRT vorhanden' },
]

export function FormatUpgradeConfig({ value, onChange }: FormatUpgradeConfigProps) {
  return (
    <div className="flex gap-3">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="flex-1 p-3 rounded-lg text-left transition-all"
          style={{
            background: value === opt.value ? 'var(--accent-bg)' : 'var(--bg-primary)',
            border: `1px solid ${value === opt.value ? 'var(--accent)' : 'var(--border)'}`,
          }}
        >
          <div
            className="text-xs font-semibold mb-0.5"
            style={{ color: value === opt.value ? 'var(--accent)' : 'var(--text-primary)' }}
          >
            {opt.label}
          </div>
          <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {opt.desc}
          </div>
        </button>
      ))}
    </div>
  )
}
