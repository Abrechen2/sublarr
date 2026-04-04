import { useState } from 'react'
import { X } from 'lucide-react'

const COMMON_LANGUAGES = [
  { code: 'de', label: 'Deutsch', flag: '🇩🇪' },
  { code: 'en', label: 'Englisch', flag: '🇬🇧' },
  { code: 'ja', label: 'Japanisch', flag: '🇯🇵' },
  { code: 'fr', label: 'Französisch', flag: '🇫🇷' },
  { code: 'es', label: 'Spanisch', flag: '🇪🇸' },
  { code: 'it', label: 'Italienisch', flag: '🇮🇹' },
  { code: 'pt', label: 'Portugiesisch', flag: '🇵🇹' },
  { code: 'ru', label: 'Russisch', flag: '🇷🇺' },
  { code: 'ar', label: 'Arabisch', flag: '🇸🇦' },
  { code: 'zh', label: 'Chinesisch', flag: '🇨🇳' },
  { code: 'ko', label: 'Koreanisch', flag: '🇰🇷' },
  { code: 'pl', label: 'Polnisch', flag: '🇵🇱' },
]

interface LanguageFilterConfigProps {
  value: string[]
  onChange: (langs: string[]) => void
}

export function LanguageFilterConfig({ value, onChange }: LanguageFilterConfigProps) {
  const [showDropdown, setShowDropdown] = useState(false)

  const addLang = (code: string) => {
    if (!value.includes(code)) onChange([...value, code])
    setShowDropdown(false)
  }

  const removeLang = (code: string) => onChange(value.filter((l) => l !== code))

  const getLang = (code: string) =>
    COMMON_LANGUAGES.find((l) => l.code === code) ?? { code, label: code.toUpperCase(), flag: '🌐' }

  const available = COMMON_LANGUAGES.filter((l) => !value.includes(l.code))

  return (
    <div className="space-y-3">
      <div
        className="text-[10px] font-semibold uppercase tracking-wide"
        style={{ color: 'var(--text-muted)' }}
      >
        Behalten
      </div>
      <div className="flex flex-wrap gap-2">
        {value.map((code) => {
          const lang = getLang(code)
          return (
            <span
              key={code}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium"
              style={{
                background: 'var(--accent-bg)',
                border: '1px solid var(--accent)',
                color: 'var(--accent)',
              }}
            >
              <span>{lang.flag}</span>
              {lang.label} ({code})
              <button onClick={() => removeLang(code)} className="ml-0.5 opacity-70 hover:opacity-100">
                <X size={10} />
              </button>
            </span>
          )
        })}

        <div className="relative">
          <button
            onClick={() => setShowDropdown(!showDropdown)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs border border-dashed"
            style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
          >
            + Sprache hinzufügen
          </button>
          {showDropdown && available.length > 0 && (
            <div
              className="absolute top-8 left-0 z-10 rounded-lg shadow-lg py-1 min-w-[180px]"
              style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            >
              {available.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => addLang(lang.code)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:opacity-80"
                  style={{ color: 'var(--text-primary)' }}
                >
                  <span>{lang.flag}</span> {lang.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
        NFO-Dateien (.nfo) werden nie angefasst.
      </div>
    </div>
  )
}
