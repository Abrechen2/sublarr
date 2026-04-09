/**
 * SubtitlesLanguagesPage — Languages & Profiles settings sub-page.
 *
 * Sections:
 * 1. Language Profiles — reusable language config per series/movie
 * 2. Default Languages — primary/target language, HI & forced preferences
 */
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Users, Globe } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

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

const inputStyle: React.CSSProperties = { ...settingsInputStyle, width: '120px', outline: 'none' }

// ─── Language options ─────────────────────────────────────────────────────────

const LANGUAGE_OPTIONS = [
  { value: 'de', label: 'Deutsch' },
  { value: 'en', label: 'English' },
  { value: 'fr', label: 'Français' },
  { value: 'ja', label: 'Japanese' },
  { value: 'es', label: 'Español' },
  { value: 'it', label: 'Italiano' },
  { value: 'pt', label: 'Português' },
  { value: 'nl', label: 'Nederlands' },
  { value: 'pl', label: 'Polski' },
  { value: 'ru', label: 'Русский' },
  { value: 'ko', label: '한국어' },
  { value: 'zh', label: '中文' },
  { value: 'ar', label: 'العربية' },
  { value: 'tr', label: 'Türkçe' },
  { value: 'sv', label: 'Svenska' },
  { value: 'da', label: 'Dansk' },
  { value: 'fi', label: 'Suomi' },
  { value: 'no', label: 'Norsk' },
  { value: 'cs', label: 'Čeština' },
  { value: 'hu', label: 'Magyar' },
] as const

// ─── Default Languages Section ────────────────────────────────────────────────

function DefaultLanguagesContent() {
  const { t } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const { mutate: updateConfig, isPending } = useUpdateConfig()
  const save = (patch: Record<string, unknown>) => updateConfig(patch)

  const hiOptions = [
    { value: 'include', label: t('general_page.hi_include') },
    { value: 'prefer',  label: t('general_page.hi_prefer') },
    { value: 'exclude', label: t('general_page.hi_exclude') },
    { value: 'only',    label: t('general_page.hi_only') },
  ]
  const forcedOptions = [
    { value: 'include', label: t('general_page.forced_include') },
    { value: 'prefer',  label: t('general_page.forced_prefer') },
    { value: 'exclude', label: t('general_page.forced_exclude') },
    { value: 'only',    label: t('general_page.forced_only') },
  ]

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="default-languages-content">
      <FormGroup
        label={t('general_page.source_language')}
        hint={t('general_page.source_language_hint')}
        htmlFor="source-language"
        data-testid="form-group-source-language"
      >
        <input
          id="source-language"
          type="text"
          data-testid="input-source-language"
          style={{ ...inputStyle, width: '120px' }}
          value={strVal(config, 'source_language', 'en')}
          onChange={(e) => save({ source_language: e.target.value })}
          disabled={isPending}
          placeholder="en"
        />
      </FormGroup>

      <FormGroup
        label={t('general_page.target_language')}
        hint={t('general_page.target_language_hint')}
        htmlFor="target-language"
        data-testid="form-group-target-language"
      >
        <select
          id="target-language"
          data-testid="select-target-language"
          style={{ ...inputStyle, width: '120px' }}
          value={strVal(config, 'target_language', 'de')}
          onChange={(e) => save({ target_language: e.target.value })}
          disabled={isPending}
        >
          {LANGUAGE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </FormGroup>

      <FormGroup
        label={t('general_page.hi_preference')}
        hint={t('general_page.hi_preference_hint')}
        htmlFor="hi-preference"
        data-testid="form-group-hi-preference"
      >
        <select
          id="hi-preference"
          data-testid="select-hi-preference"
          style={{ ...inputStyle, width: '120px' }}
          value={strVal(config, 'hi_preference', 'include')}
          onChange={(e) => save({ hi_preference: e.target.value })}
          disabled={isPending}
        >
          {hiOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </FormGroup>

      <FormGroup
        label={t('general_page.forced_preference')}
        hint={t('general_page.forced_preference_hint')}
        htmlFor="forced-preference"
        data-testid="form-group-forced-preference"
      >
        <select
          id="forced-preference"
          data-testid="select-forced-preference"
          style={{ ...inputStyle, width: '120px' }}
          value={strVal(config, 'forced_preference', 'include')}
          onChange={(e) => save({ forced_preference: e.target.value })}
          disabled={isPending}
        >
          {forcedOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </FormGroup>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function SubtitlesLanguagesPage() {
  const { t } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title={t('settings.subtitles.languagesPage.title', 'Languages & Profiles')}
      subtitle={t(
        'settings.subtitles.languagesPage.subtitle',
        'Configure which subtitle languages Sublarr searches for and how multi-language setups are managed.',
      )}
    >
      {/* 1. Language Profiles */}
      <div data-testid="section-language-profiles">
        <SettingsSection
          title={t('settings.subtitles.languageProfiles.title', 'Language Profiles')}
          description={t(
            'settings.subtitles.languageProfiles.description',
            'Define reusable language and translation settings for series and movies.',
          )}
          icon={<Users size={16} style={{ color: 'var(--accent)' }} />}
        >
          <Suspense fallback={<SectionSkeleton />}>
            <LanguageProfilesTab />
          </Suspense>
        </SettingsSection>
      </div>

      {/* 2. Default Languages */}
      <div data-testid="section-default-languages">
        <SettingsSection
          title={t('settings.subtitles.defaultLanguages.title', 'Default Languages')}
          description={t(
            'settings.subtitles.defaultLanguages.description',
            'Primary search language, source language for translation, and HI/forced subtitle preferences.',
          )}
          icon={<Globe size={16} style={{ color: 'var(--accent)' }} />}
        >
          <DefaultLanguagesContent />
        </SettingsSection>
      </div>
    </SettingsDetailLayout>
  )
}
