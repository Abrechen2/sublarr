import { X } from 'lucide-react'
import { settingsInputStyle } from '@/styles/settingsShared'
import { useTranslation } from 'react-i18next'

interface LanguageOption {
  readonly value: string
  readonly label: string
}

interface Props {
  readonly value: string[]
  readonly options: readonly LanguageOption[]
  readonly onChange: (newValue: string[]) => void
  readonly placeholder?: string
}

export function LanguagePillSelector({
  value,
  options,
  onChange,
  placeholder = '— Add language —',
}: Props) {
  const { t: tc } = useTranslation('common')
  const available = options.filter((o) => !value.includes(o.value))

  const remove = (lang: string) => onChange(value.filter((v) => v !== lang))

  const add = (lang: string) => {
    if (lang && !value.includes(lang)) onChange([...value, lang])
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '6px',
          minHeight: '36px',
          padding: '6px 8px',
          background: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          alignItems: 'center',
        }}
      >
        {value.map((lang) => {
          const opt = options.find((o) => o.value === lang)
          return (
            <span
              key={lang}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                background: 'var(--accent-bg)',
                border: '1px solid var(--accent-dim)',
                borderRadius: '4px',
                padding: '3px 8px',
                fontSize: '12px',
                color: 'var(--accent)',
              }}
            >
              {opt?.label ?? lang}
              <button
                type="button"
                aria-label={tc('ui.remove')}
                onClick={() => remove(lang)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  padding: 0,
                  marginLeft: '2px',
                }}
              >
                <X size={11} />
              </button>
            </span>
          )
        })}
        {value.length === 0 && (
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>—</span>
        )}
      </div>

      {available.length > 0 && (
        <select
          value=""
          onChange={(e) => {
            add(e.target.value)
            e.target.value = ''
          }}
          style={{ ...settingsInputStyle, width: '220px', fontSize: '12px' }}
        >
          <option value="">{placeholder}</option>
          {available.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}
