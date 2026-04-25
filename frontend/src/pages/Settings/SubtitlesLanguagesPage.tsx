/**
 * SubtitlesLanguagesPage — Languages settings sub-page.
 *
 * Language Profiles have moved to /settings/profiles (ProfilesOverridesPage).
 * This page is retained for the /settings/subtitles/languages route slot;
 * it currently renders empty but will host default-language controls in a
 * future task.
 */
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'

export function SubtitlesLanguagesPage() {
  const { t } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('settings.subtitles.languagesPage.title', 'Languages')}
      subtitle={t(
        'settings.subtitles.languagesPage.subtitle',
        'Configure which subtitle languages Sublarr searches for.',
      )}
    />
  )
}
