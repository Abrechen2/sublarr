/**
 * SubtitlesFormatPage — Format & Naming settings sub-page.
 *
 * Sections:
 * 1. Format & Tools      — subtitle tools (SubtitleToolsTab)
 * 2. Subtitle Naming     — language code format, suffix separator, hi/forced suffixes
 * 3. Scan Filters        — ignore patterns, minimum file size, ignore languages
 * 4. Embedded Extraction — auto-extract, embedded subs usage (advanced, collapsed)
 */
import { useTranslation } from 'react-i18next'
import { Tag, Filter, Film } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal, numVal, boolVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

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
  const { t } = useTranslation('settings')
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
  const { t } = useTranslation('settings')
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

// ─── Embedded Extraction Section ─────────────────────────────────────────────

function EmbeddedExtractionContent() {
  const { t } = useTranslation('settings')
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

// ─── Page ─────────────────────────────────────────────────────────────────────

// Settings Template B (FormLayout). Three sections, well under the 6-cap.
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'naming',              titleKey: 'subtitles_format_page.naming_section' },
  { id: 'scan-filters',        titleKey: 'subtitles_format_page.scan_filters_section' },
  { id: 'embedded-extraction', titleKey: 'subtitles_format_page.embedded_extraction_section' },
]

export function SubtitlesFormatPage() {
  const { t } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('settings.subtitles.formatPage.title', 'Format & Naming')}
      subtitle={t(
        'settings.subtitles.formatPage.subtitle',
        'Subtitle format preferences, file naming conventions, scan filters, and embedded track extraction.',
      )}
    >
      <FormLayout sections={SECTIONS}>

      {/* 1. Subtitle Naming */}
      <section id="naming" data-testid="settings.subtitles-format.section-naming">
      <div data-testid="section-subtitle-naming">
        <SettingsSection
          title={t('subtitles_format_page.naming_section')}
          description={t('settings.subtitles.subtitleNaming.description')}
          icon={<Tag size={16} style={{ color: 'var(--accent)' }} />}
        >
          <SubtitleNamingContent />
        </SettingsSection>
      </div>
      </section>

      {/* 2. Scan Filters */}
      <section id="scan-filters" data-testid="settings.subtitles-format.section-scan-filters">
      <div data-testid="section-scan-filters">
        <SettingsSection
          title={t('subtitles_format_page.scan_filters_section')}
          description={t('settings.subtitles.scanFilters.description')}
          icon={<Filter size={16} style={{ color: 'var(--accent)' }} />}
        >
          <ScanFiltersContent />
        </SettingsSection>
      </div>
      </section>

      {/* 3. Embedded Extraction (advanced — collapsed by default) */}
      <section id="embedded-extraction" data-testid="settings.subtitles-format.section-embedded-extraction">
      <div data-testid="section-embedded-extraction">
        <SettingsSection
          title={t('subtitles_format_page.embedded_extraction_section')}
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
      </section>

      </FormLayout>
    </SettingsDetailLayout>
  )
}
