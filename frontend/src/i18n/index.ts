import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

// Static imports -- no HTTP backend needed for 2 languages
import enCommon from './locales/en/common.json'
import deCommon from './locales/de/common.json'
import enDashboard from './locales/en/dashboard.json'
import deDashboard from './locales/de/dashboard.json'
import enSettings from './locales/en/settings.json'
import deSettings from './locales/de/settings.json'
import enLibrary from './locales/en/library.json'
import deLibrary from './locales/de/library.json'
import enLogs from './locales/en/logs.json'
import deLogs from './locales/de/logs.json'
import enStatistics from './locales/en/statistics.json'
import deStatistics from './locales/de/statistics.json'
import enActivity from './locales/en/activity.json'
import deActivity from './locales/de/activity.json'
import enOnboarding from './locales/en/onboarding.json'
import deOnboarding from './locales/de/onboarding.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        common: enCommon,
        dashboard: enDashboard,
        settings: enSettings,
        library: enLibrary,
        logs: enLogs,
        statistics: enStatistics,
        activity: enActivity,
        onboarding: enOnboarding,
      },
      de: {
        common: deCommon,
        dashboard: deDashboard,
        settings: deSettings,
        library: deLibrary,
        logs: deLogs,
        statistics: deStatistics,
        activity: deActivity,
        onboarding: deOnboarding,
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
