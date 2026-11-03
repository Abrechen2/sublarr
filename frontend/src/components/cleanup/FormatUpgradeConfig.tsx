import { useTranslation } from 'react-i18next'

type KeepFormat = 'any' | 'ass' | 'srt'

interface FormatUpgradeConfigProps {
  value: KeepFormat
  onChange: (format: KeepFormat) => void
}

// Keys are resolved at render time so the language switch applies immediately.
const OPTIONS: { value: KeepFormat; labelKey: string; descKey: string }[] = [
  { value: 'any', labelKey: 'cleanup_detail.format.any', descKey: 'cleanup_detail.format.any_desc' },
  { value: 'ass', labelKey: 'cleanup_detail.format.ass', descKey: 'cleanup_detail.format.ass_desc' },
  { value: 'srt', labelKey: 'cleanup_detail.format.srt', descKey: 'cleanup_detail.format.srt_desc' },
]

export function FormatUpgradeConfig({ value, onChange }: FormatUpgradeConfigProps) {
  const { t } = useTranslation('common')
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
            {t(opt.labelKey)}
          </div>
          <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {t(opt.descKey)}
          </div>
        </button>
      ))}
    </div>
  )
}
