import { useTranslation } from 'react-i18next'
import { useUpdateConfig } from '@/hooks/useApi'

export function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const { mutate: updateConfig } = useUpdateConfig()
  const currentLang = i18n.language?.startsWith('de') ? 'de' : 'en'

  const toggleLanguage = () => {
    const newLang = currentLang === 'en' ? 'de' : 'en'
    i18n.changeLanguage(newLang)
    // Persisted to localStorage by the language detector; also persist the
    // interface_language setting so the toggle and Settings → General stay
    // in sync (they were previously two disconnected sources of truth).
    updateConfig({ interface_language: newLang })
  }

  return (
    <button
      data-testid="language-switcher"
      onClick={toggleLanguage}
      aria-label={`Switch language to ${currentLang === 'en' ? 'Deutsch' : 'English'}`}
      title={currentLang === 'en' ? 'Deutsch' : 'English'}
      className="flex items-center justify-center rounded-md transition-colors duration-150"
      style={{
        width: 28,
        height: 28,
        color: 'var(--text-secondary)',
        fontWeight: 600,
        fontSize: 11,
        lineHeight: 1,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = 'var(--accent)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = 'var(--text-secondary)'
      }}
    >
      {currentLang === 'en' ? 'DE' : 'EN'}
    </button>
  )
}
