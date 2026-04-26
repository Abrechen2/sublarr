/**
 * SubtitlesLanguagesPage — Languages & Profiles settings sub-page.
 *
 * Sections:
 * 1. Language Profiles — reusable language config per series/movie (HI, forced,
 *    target languages, translation backend). The "Standard" profile acts as the
 *    global default; use the "Als Standard" button to apply it to all items.
 */
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Users } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'

// ─── Lazy sub-tabs ────────────────────────────────────────────────────────────

const LanguageProfilesTab = lazy(() =>
  import('./AdvancedTab').then((m) => ({ default: m.LanguageProfilesTab })),
)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function SectionSkeleton() {
  return (
    <div data-testid="section-skeleton" className="animate-pulse space-y-3 py-2">
      {[...Array(3)].map((_, i) => (
        <div
          key={i}
          className="h-8 rounded"
          style={{ backgroundColor: 'var(--bg-surface-hover)', width: i === 0 ? '70%' : '100%' }}
        />
      ))}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function SubtitlesLanguagesPage() {
  const { t } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('settings.subtitles.languagesPage.title', 'Languages & Profiles')}
      subtitle={t(
        'settings.subtitles.languagesPage.subtitle',
        'Configure which subtitle languages Sublarr searches for and how multi-language setups are managed.',
      )}
    >
      {/* Language Profiles — HI/Forced preferences, target languages, translation backend */}
      <div data-testid="section-language-profiles">
        <SettingsSection
          title={t('settings.subtitles.languageProfiles.title', 'Language Profiles')}
          description={t(
            'settings.subtitles.languageProfiles.description',
            'Define reusable language and translation settings for series and movies. The default profile applies to all items without an explicit assignment.',
          )}
          icon={<Users size={16} style={{ color: 'var(--accent)' }} />}
        >
          <Suspense fallback={<SectionSkeleton />}>
            <LanguageProfilesTab />
          </Suspense>
        </SettingsSection>
      </div>
    </SettingsDetailLayout>
  )
}
