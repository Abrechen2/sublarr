import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

const COMMON_LANGUAGES = [
  { code: 'de', flag: '🇩🇪' },
  { code: 'en', flag: '🇬🇧' },
  { code: 'ja', flag: '🇯🇵' },
  { code: 'fr', flag: '🇫🇷' },
  { code: 'es', flag: '🇪🇸' },
  { code: 'it', flag: '🇮🇹' },
  { code: 'pt', flag: '🇵🇹' },
  { code: 'ru', flag: '🇷🇺' },
  { code: 'ar', flag: '🇸🇦' },
  { code: 'zh', flag: '🇨🇳' },
  { code: 'ko', flag: '🇰🇷' },
  { code: 'pl', flag: '🇵🇱' },
]

interface LanguageFilterConfigProps {
  value: string[]
  onChange: (langs: string[]) => void
}

/** Language name in the active UI language (e.g. "Deutsch" / "German"). */
function languageLabel(code: string, uiLang: string): string {
  try {
    return new Intl.DisplayNames([uiLang], { type: 'language' }).of(code) ?? code.toUpperCase()
  } catch {
    return code.toUpperCase()
  }
}

export function LanguageFilterConfig({ value, onChange }: LanguageFilterConfigProps) {
  const { t, i18n } = useTranslation('common')
  const [localValue, setLocalValue] = useState(value)
  const [showDropdown, setShowDropdown] = useState(false)

  // Sync from server after mutations settle
  useEffect(() => {
    setLocalValue(value)
  }, [value])

  const addLang = (code: string) => {
    if (!localValue.includes(code)) {
      const next = [...localValue, code]
      setLocalValue(next)
      onChange(next)
    }
    setShowDropdown(false)
  }

  const removeLang = (code: string) => {
    const next = localValue.filter((l) => l !== code)
    setLocalValue(next)
    onChange(next)
  }

  const getLang = (code: string) => ({
    code,
    label: languageLabel(code, i18n.language),
    flag: COMMON_LANGUAGES.find((l) => l.code === code)?.flag ?? '🌐',
  })

  const available = COMMON_LANGUAGES.filter((l) => !localValue.includes(l.code)).map((l) => getLang(l.code))

  return (
    <div className="space-y-3">
      <div
        className="text-[10px] font-semibold uppercase tracking-wide"
        style={{ color: 'var(--text-muted)' }}
      >
        {t('cleanup_detail.keep')}
      </div>
      <div className="flex flex-wrap gap-2">
        {localValue.map((code) => {
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
            {t('cleanup_detail.add_language')}
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
        {t('cleanup_detail.nfo_untouched')}
      </div>
    </div>
  )
}
