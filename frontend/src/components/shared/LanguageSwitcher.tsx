import { useTranslation } from 'react-i18next'

export function LanguageSwitcher() {
  const { i18n } = useTranslation()

  const currentLang = i18n.language?.startsWith('de') ? 'de' : 'en'

  const toggleLanguage = () => {
    const newLang = currentLang === 'en' ? 'de' : 'en'
    i18n.changeLanguage(newLang)
    // Automatically persisted to localStorage by language detector
  }

  return (
    <button
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
