/**
 * SubtitlesSettings — Settings page for subtitle management.
 *
 * Six sections:
 * 1. Scoring          – min score threshold, weights, provider modifiers, presets
 * 2. Format & Tools   – default format, conversion, subtitle tools
 * 3. Cleanup          – auto-dedup, orphaned subtitle cleanup
 * 4. Embedded Extraction (advanced) – auto-extract toggle, language selection
 * 5. Language Profiles (advanced)   – profile CRUD
 * 6. Fansub Preferences (advanced)  – global fansub group preferences
 */
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Star, FileType, Film, Users, Heart, Tag, Filter, Sliders, Globe } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal, numVal, boolVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

// ─── Lazy sub-tabs ───────────────────────────────────────────────────────────

const ScoringTab = lazy(() =>
  import('./ScoringTab').then((m) => ({ default: m.ScoringTab })),
)
const LanguageProfilesTab = lazy(() =>
  import('./AdvancedTab').then((m) => ({ default: m.LanguageProfilesTab })),
)
const SubtitleToolsTab = lazy(() =>
  import('./AdvancedTab').then((m) => ({ default: m.SubtitleToolsTab })),
)
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

// ─── Embedded Extraction Section ─────────────────────────────────────────────

const inputStyle: React.CSSProperties = { ...settingsInputStyle, width: '120px', outline: 'none' }

// ─── Subtitle Naming Constants ────────────────────────────────────────────────

const LANG_CODE_FORMATS = [
  { value: 'iso_639_1', label: 'ISO 639-1 (2-letter: de, en)' },
  { value: 'iso_639_2', label: 'ISO 639-2 (3-letter: deu, eng)' },
] as const
const SUFFIX_SEPARATORS = [
  { value: 'dot', label: 'Dot  (movie.de.ass)' },
  { value: 'dash', label: 'Dash  (movie-de.ass)' },
  { value: 'underscore', label: 'Underscore  (movie_de.ass)' },
] as const

// ─── Subtitle Naming Section ──────────────────────────────────────────────────

function SubtitleNamingContent() {
  const { t } = useTranslation('common')
  const { data: config, isLoading } = useConfig()
  const { mutate: updateConfig, isPending } = useUpdateConfig()
  const save = (patch: Record<string, unknown>) => updateConfig(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="subtitle-naming-content">
      <FormGroup
        label={t('settings.subtitles.subtitleNaming.langCodeFormat')}
        hint={t('settings.subtitles.subtitleNaming.langCodeFormatHint')}
        htmlFor="subtitle-language-code-format"
        data-testid="form-group-subtitle-language-code-format"
      >
        <select
          id="subtitle-language-code-format"
          data-testid="select-subtitle-language-code-format"
          style={inputStyle}
          value={strVal(config, 'subtitle_language_code_format', 'iso_639_1')}
          onChange={(e) => save({ subtitle_language_code_format: e.target.value })}
          disabled={isPending}
        >
          {LANG_CODE_FORMATS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </FormGroup>

      <FormGroup
        label={t('settings.subtitles.subtitleNaming.suffixSeparator')}
        hint={t('settings.subtitles.subtitleNaming.suffixSeparatorHint')}
        htmlFor="subtitle-suffix-separator"
        data-testid="form-group-subtitle-suffix-separator"
      >
        <select
          id="subtitle-suffix-separator"
          data-testid="select-subtitle-suffix-separator"
          style={inputStyle}
          value={strVal(config, 'subtitle_suffix_separator', 'dot')}
          onChange={(e) => save({ subtitle_suffix_separator: e.target.value })}
          disabled={isPending}
        >
          {SUFFIX_SEPARATORS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </FormGroup>

      <FormGroup
        label={t('settings.subtitles.subtitleNaming.hiSuffix')}
        hint={t('settings.subtitles.subtitleNaming.hiSuffixHint')}
        htmlFor="subtitle-hi-suffix"
        data-testid="form-group-subtitle-hi-suffix"
      >
        <input
          id="subtitle-hi-suffix"
          type="text"
          data-testid="input-subtitle-hi-suffix"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'subtitle_hi_suffix', 'hi')}
          onChange={(e) => save({ subtitle_hi_suffix: e.target.value })}
          disabled={isPending}
          placeholder="hi"
        />
      </FormGroup>

      <FormGroup
        label={t('settings.subtitles.subtitleNaming.forcedSuffix')}
        hint={t('settings.subtitles.subtitleNaming.forcedSuffixHint')}
        htmlFor="subtitle-forced-suffix"
        data-testid="form-group-subtitle-forced-suffix"
      >
        <input
          id="subtitle-forced-suffix"
          type="text"
          data-testid="input-subtitle-forced-suffix"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'subtitle_forced_suffix', 'forced')}
          onChange={(e) => save({ subtitle_forced_suffix: e.target.value })}
          disabled={isPending}
          placeholder="forced"
        />
      </FormGroup>
    </div>
  )
}

// ─── Scan Filters Section ─────────────────────────────────────────────────────

function ScanFiltersContent() {
  const { t } = useTranslation('common')
  const { data: config, isLoading } = useConfig()
  const { mutate: updateConfig, isPending } = useUpdateConfig()
  const save = (patch: Record<string, unknown>) => updateConfig(patch)

  if (isLoading) return <SectionSkeleton />

  const textareaStyle: React.CSSProperties = {
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    borderRadius: '6px',
    padding: '7px 12px',
    fontSize: '13px',
    fontFamily: 'var(--font-body)',
    width: '100%',
    outline: 'none',
    resize: 'vertical',
  }

  return (
    <div data-testid="scan-filters-content">
      <FormGroup
        label={t('settings.subtitles.scanFilters.ignorePatterns')}
        hint={t('settings.subtitles.scanFilters.ignorePatternsHint')}
        data-testid="form-group-scan-ignore-patterns"
      >
        <textarea
          data-testid="textarea-scan-ignore-patterns"
          style={textareaStyle}
          rows={3}
          defaultValue={strVal(config, 'scan_ignore_patterns', '[]')}
          onBlur={(e) => save({ scan_ignore_patterns: e.target.value })}
          disabled={isPending}
          placeholder='["*.sample.*", "*.extras.*"]'
        />
      </FormGroup>

      <FormGroup
        label={t('settings.subtitles.scanFilters.minFileSize')}
        hint={t('settings.subtitles.scanFilters.minFileSizeHint')}
        htmlFor="scan-min-file-size-mb"
        data-testid="form-group-scan-min-file-size-mb"
      >
        <input
          id="scan-min-file-size-mb"
          type="number"
          data-testid="input-scan-min-file-size-mb"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={numVal(config, 'scan_min_file_size_mb', 0)}
          onChange={(e) => save({ scan_min_file_size_mb: Number(e.target.value) })}
          disabled={isPending}
          min={0}
          step={0.1}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.subtitles.scanFilters.ignoreLanguages')}
        hint={t('settings.subtitles.scanFilters.ignoreLanguagesHint')}
        data-testid="form-group-scan-ignore-languages"
      >
        <textarea
          data-testid="textarea-scan-ignore-languages"
          style={textareaStyle}
          rows={2}
          defaultValue={strVal(config, 'scan_ignore_languages', '[]')}
          onBlur={(e) => save({ scan_ignore_languages: e.target.value })}
          disabled={isPending}
          placeholder='["fr", "es"]'
        />
      </FormGroup>
    </div>
  )
}

// ─── Per-Language Score Thresholds Section ────────────────────────────────────

function PerLanguageScoresContent() {
  const { t } = useTranslation('common')
  const { data: config, isLoading } = useConfig()
  const { mutate: updateConfig, isPending } = useUpdateConfig()
  const save = (patch: Record<string, unknown>) => updateConfig(patch)

  if (isLoading) return <SectionSkeleton />

  const textareaStyle: React.CSSProperties = {
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    borderRadius: '6px',
    padding: '7px 12px',
    fontSize: '13px',
    fontFamily: 'var(--font-body)',
    width: '100%',
    outline: 'none',
    resize: 'vertical',
  }

  return (
    <div data-testid="per-language-scores-content">
      <FormGroup
        label={t('settings.subtitles.perLanguageScores.label')}
        hint={t('settings.subtitles.perLanguageScores.hint')}
        data-testid="form-group-score-threshold-per-language"
      >
        <textarea
          data-testid="textarea-score-threshold-per-language"
          style={textareaStyle}
          rows={4}
          defaultValue={strVal(config, 'score_threshold_per_language', '{}')}
          onBlur={(e) => save({ score_threshold_per_language: e.target.value })}
          disabled={isPending}
          placeholder='{"de": 80, "fr": 70}'
        />
      </FormGroup>
      <p style={{ color: 'var(--text-muted)', fontSize: '11px', marginTop: '6px' }}>
        {t('settings.subtitles.perLanguageScores.example')}
        <br />
        {t('settings.subtitles.perLanguageScores.fallback')}
      </p>
    </div>
  )
}

// ─── Default Languages Section ───────────────────────────────────────────────

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

// ─── Embedded Extraction Section ─────────────────────────────────────────────

function EmbeddedExtractionContent() {
  const { t } = useTranslation('common')
  const { data: config, isLoading } = useConfig()
  const { mutate: updateConfig, isPending } = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => {
    updateConfig(patch, {
      onSuccess: () => toast(t('settings.subtitles.embeddedExtraction.saved', 'Setting saved')),
      onError: () =>
        toast(t('settings.subtitles.embeddedExtraction.saveFailed', 'Failed to save'), 'error'),
    })
  }

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="embedded-extraction-content">
      <FormGroup
        label={t('settings.subtitles.embeddedExtraction.autoExtract', 'Auto-Extract Embedded Subtitles')}
        hint={t(
          'settings.subtitles.embeddedExtraction.autoExtractHint',
          'Automatically extract embedded subtitle tracks during the wanted scan.',
        )}
        data-testid="form-group-wanted-auto-extract"
      >
        <Toggle
          checked={boolVal(config, 'wanted_auto_extract')}
          onChange={(v) => save({ wanted_auto_extract: String(v) })}
          disabled={isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.subtitles.embeddedExtraction.useEmbeddedSubs', 'Use Embedded Subtitles')}
        hint={t(
          'settings.subtitles.embeddedExtraction.useEmbeddedSubsHint',
          'Check for embedded subtitle streams in MKV files before searching providers.',
        )}
        data-testid="form-group-use-embedded-subs"
      >
        <Toggle
          checked={boolVal(config, 'use_embedded_subs', true)}
          onChange={(v) => save({ use_embedded_subs: String(v) })}
          disabled={isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.subtitles.embeddedExtraction.hiRemoval', 'HI Removal on Extraction')}
        hint={t(
          'settings.subtitles.embeddedExtraction.hiRemovalHint',
          'Strip hearing-impaired tags from extracted subtitle tracks.',
        )}
        data-testid="form-group-hi-removal-enabled"
      >
        <Toggle
          checked={boolVal(config, 'hi_removal_enabled')}
          onChange={(v) => save({ hi_removal_enabled: String(v) })}
          disabled={isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.subtitles.embeddedExtraction.skipSrtOnNoAss', 'Skip SRT if No ASS Found')}
        hint={t(
          'settings.subtitles.embeddedExtraction.skipSrtOnNoAssHint',
          'Skip SRT extraction steps if no ASS/SSA track was found in the first two steps.',
        )}
        data-testid="form-group-wanted-skip-srt-on-no-ass"
      >
        <Toggle
          checked={boolVal(config, 'wanted_skip_srt_on_no_ass', true)}
          onChange={(v) => save({ wanted_skip_srt_on_no_ass: String(v) })}
          disabled={isPending}
        />
      </FormGroup>
    </div>
  )
}

// ─── Fansub Preferences Section ───────────────────────────────────────────────

function FansubPreferencesContent() {
  const { t } = useTranslation('common')
  const { data: config, isLoading } = useConfig()
  const { mutate: updateConfig, isPending } = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="fansub-preferences-content">
      <p className="text-[12px] text-[var(--text-muted)] pb-3">
        {t(
          'settings.subtitles.fansubPreferences.hint',
          'Global fansub group preferences apply to all library items. Per-series overrides can be set on each series detail page.',
        )}
      </p>

      <FormGroup
        label={t('settings.subtitles.fansubPreferences.creditThreshold', 'Credit Threshold (seconds)')}
        hint={t(
          'settings.subtitles.fansubPreferences.creditThresholdHint',
          'Duration in seconds used to detect credit/OP/ED segments during subtitle processing.',
        )}
        data-testid="form-group-credit-threshold-sec"
      >
        <input
          id="credit-threshold-sec"
          type="number"
          data-testid="input-credit-threshold-sec"
          style={inputStyle}
          value={numVal(config, 'credit_threshold_sec', 90)}
          onChange={(e) => save({ credit_threshold_sec: Number(e.target.value) })}
          disabled={isPending}
          min={0}
          max={600}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.subtitles.fansubPreferences.opWindow', 'OP/ED Window (seconds)')}
        hint={t(
          'settings.subtitles.fansubPreferences.opWindowHint',
          'Seconds from the start/end of the file considered as the opening/ending window.',
        )}
        data-testid="form-group-op-window-sec"
      >
        <input
          id="op-window-sec"
          type="number"
          data-testid="input-op-window-sec"
          style={inputStyle}
          value={numVal(config, 'op_window_sec', 300)}
          onChange={(e) => save({ op_window_sec: Number(e.target.value) })}
          disabled={isPending}
          min={0}
          max={3600}
        />
      </FormGroup>
    </div>
  )
}

// ─── SubtitlesSettings Page ───────────────────────────────────────────────────

export function SubtitlesSettings() {
  const { t } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title={t('settings.categories.subtitles.title')}
      subtitle={t('settings.categories.subtitles.description')}
    >
      {/* 1. Language Profiles */}
      <div data-testid="section-language-profiles">
        <SettingsSection
          title={t('settings.subtitles.languageProfiles.title', 'Sprachprofile')}
          description={t(
            'settings.subtitles.languageProfiles.description',
            'Lege fest, welche Untertitelsprachen pro Serie/Film gesucht werden.',
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
          title={t('settings.subtitles.defaultLanguages.title', 'Standardsprachen')}
          description={t(
            'settings.subtitles.defaultLanguages.description',
            'Standard-Quell- und Zielsprache sowie Präferenzen für HI- und erzwungene Untertitel.',
          )}
          icon={<Globe size={16} style={{ color: 'var(--accent)' }} />}
        >
          <DefaultLanguagesContent />
        </SettingsSection>
      </div>

      {/* 3. Scoring */}
      <div data-testid="section-scoring">
        <SettingsSection
          title={t('settings.subtitles.scoring.title', 'Scoring')}
          description={t(
            'settings.subtitles.scoring.description',
            'Configure how subtitles are ranked and selected from providers.',
          )}
          icon={<Star size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="scoring-content">
            <Suspense fallback={<SectionSkeleton />}>
              <ScoringTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>

      {/* 4. Format & Tools */}
      <div data-testid="section-format-tools">
        <SettingsSection
          title={t('settings.subtitles.formatTools.title', 'Format & Tools')}
          description={t(
            'settings.subtitles.formatTools.description',
            'Subtitle file format preferences and manual subtitle tools.',
          )}
          icon={<FileType size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="format-tools-content">
            <Suspense fallback={<SectionSkeleton />}>
              <SubtitleToolsTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>

      {/* 4. Embedded Extraction (advanced — collapsed by default) */}
      <div data-testid="section-embedded-extraction">
        <SettingsSection
          title={t('settings.subtitles.embeddedExtraction.title', 'Embedded Extraction')}
          description={t(
            'settings.subtitles.embeddedExtraction.description',
            'Extract subtitle tracks embedded directly in video files.',
          )}
          icon={<Film size={16} style={{ color: 'var(--accent)' }} />}
          advanced={<EmbeddedExtractionContent />}
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-2"
            data-testid="embedded-extraction-summary"
          >
            {t(
              'settings.subtitles.embeddedExtraction.summary',
              'Configure automatic embedded subtitle extraction triggered by webhook events.',
            )}
          </p>
        </SettingsSection>
      </div>

      {/* 6. Fansub Preferences (advanced — collapsed by default) */}
      <div data-testid="section-fansub-preferences">
        <SettingsSection
          title={t('settings.subtitles.fansubPreferences.title', 'Fansub Preferences')}
          description={t(
            'settings.subtitles.fansubPreferences.description',
            'Set global fansub group preferences applied across all library items.',
          )}
          icon={<Heart size={16} style={{ color: 'var(--accent)' }} />}
          advanced={<FansubPreferencesContent />}
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-2"
            data-testid="fansub-preferences-summary"
          >
            {t(
              'settings.subtitles.fansubPreferences.summary',
              'Preferred and excluded fansub groups for subtitle selection. Per-series overrides take priority.',
            )}
          </p>
        </SettingsSection>
      </div>

      {/* 7. Subtitle Naming (Step 38) */}
      <div data-testid="section-subtitle-naming">
        <SettingsSection
          title={t('settings.subtitles.subtitleNaming.title')}
          description={t('settings.subtitles.subtitleNaming.description')}
          icon={<Tag size={16} style={{ color: 'var(--accent)' }} />}
        >
          <SubtitleNamingContent />
        </SettingsSection>
      </div>

      {/* 8. Scan Filters (Step 42) */}
      <div data-testid="section-scan-filters">
        <SettingsSection
          title={t('settings.subtitles.scanFilters.title')}
          description={t('settings.subtitles.scanFilters.description')}
          icon={<Filter size={16} style={{ color: 'var(--accent)' }} />}
        >
          <ScanFiltersContent />
        </SettingsSection>
      </div>

      {/* 9. Per-Language Score Thresholds (Step 43) */}
      <div data-testid="section-per-language-scores">
        <SettingsSection
          title={t('settings.subtitles.perLanguageScores.title')}
          description={t('settings.subtitles.perLanguageScores.description')}
          icon={<Sliders size={16} style={{ color: 'var(--accent)' }} />}
        >
          <PerLanguageScoresContent />
        </SettingsSection>
      </div>
    </SettingsDetailLayout>
  )
}
