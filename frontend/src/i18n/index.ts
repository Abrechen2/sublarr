import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

// Static imports -- no HTTP backend needed for 2 languages
import enCommon from './locales/en/common.json'
import deCommon from './locales/de/common.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        common: enCommon,
      },
      de: {
        common: deCommon,
      },
    },
    fallbackLng: 'en',
    defaultNS: 'common',
    ns: ['common', 'dashboard', 'settings', 'library', 'activity', 'logs', 'statistics', 'onboarding'],
    interpolation: {
      escapeValue: false, // React already escapes
    },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'sublarr-language',
      caches: ['localStorage'],
    },
  })

export default i18n
