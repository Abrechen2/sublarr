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
import { Star, FileType, Trash2, Film, Users, Heart, Tag, Filter, Sliders } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal, numVal, boolVal } from '@/lib/configUtils'

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
const CleanupTab = lazy(() =>
  import('./CleanupTab').then((m) => ({ default: m.CleanupTab })),
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

// ─── Shared input style ───────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '6px',
  padding: '7px 12px',
  fontSize: '13px',
  fontFamily: 'var(--font-body)',
  width: '120px',
  outline: 'none',
}


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
  const { data: config, isLoading } = useConfig()
  const { mutate: updateConfig, isPending } = useUpdateConfig()
  const save = (patch: Record<string, unknown>) => updateConfig(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="subtitle-naming-content">
      <FormGroup
        label="Language Code Format"
        hint="Format used for the language suffix in subtitle filenames"
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
        label="Suffix Separator"
        hint="Character between the base filename and the language suffix"
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
        label="HI Subtitle Suffix"
        hint="Suffix appended to hearing-impaired subtitle filenames"
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
        label="Forced Subtitle Suffix"
        hint="Suffix appended to forced subtitle filenames"
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
        label="Ignore Patterns"
        hint='JSON array of glob patterns to skip during scan'
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
        label="Minimum File Size (MB)"
        hint="Skip media files smaller than this size during scan"
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
        label="Ignore Languages"
        hint='JSON array of ISO-639-1 codes to exclude from scan'
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
        label="Score Thresholds (JSON)"
        hint='JSON object mapping ISO-639-1 code to minimum score. Empty object uses global threshold for all languages.'
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
        {`Example: {"de": 80, "fr": 70} — German subtitles require score ≥ 80, French ≥ 70.`}
        <br />
        Leave as {'{}'} to use the global threshold for all languages.
      </p>
    </div>
  )
}

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
      title={t('settings.categories.subtitles.title', 'Subtitles')}
      subtitle={t(
        'settings.categories.subtitles.description',
        'Scoring, format, cleanup, and extraction settings',
      )}
    >
      {/* 1. Scoring */}
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

      {/* 2. Format & Tools */}
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

      {/* 3. Cleanup */}
      <div data-testid="section-cleanup">
        <SettingsSection
          title={t('settings.subtitles.cleanup.title', 'Cleanup')}
          description={t(
            'settings.subtitles.cleanup.description',
            'Remove duplicate and orphaned subtitle files from your library.',
          )}
          icon={<Trash2 size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="cleanup-content">
            <Suspense fallback={<SectionSkeleton />}>
              <CleanupTab />
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

      {/* 5. Language Profiles (advanced — collapsed by default) */}
      <div data-testid="section-language-profiles">
        <SettingsSection
          title={t('settings.subtitles.languageProfiles.title', 'Language Profiles')}
          description={t(
            'settings.subtitles.languageProfiles.description',
            'Define reusable language and translation settings for series and movies.',
          )}
          icon={<Users size={16} style={{ color: 'var(--accent)' }} />}
          advanced={
            <Suspense fallback={<SectionSkeleton />}>
              <LanguageProfilesTab />
            </Suspense>
          }
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-2"
            data-testid="language-profiles-summary"
          >
            {t(
              'settings.subtitles.languageProfiles.summary',
              'Create and manage language profiles that can be assigned to individual series or movies.',
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
          title="Subtitle Naming"
          description="Language code format and suffix conventions for saved subtitle files."
          icon={<Tag size={16} style={{ color: 'var(--accent)' }} />}
        >
          <SubtitleNamingContent />
        </SettingsSection>
      </div>

      {/* 8. Scan Filters (Step 42) */}
      <div data-testid="section-scan-filters">
        <SettingsSection
          title="Scan Filters"
          description="Exclude files and languages from subtitle scans."
          icon={<Filter size={16} style={{ color: 'var(--accent)' }} />}
        >
          <ScanFiltersContent />
        </SettingsSection>
      </div>

      {/* 9. Per-Language Score Thresholds (Step 43) */}
      <div data-testid="section-per-language-scores">
        <SettingsSection
          title="Per-Language Score Thresholds"
          description="Override the global minimum score for specific languages."
          icon={<Sliders size={16} style={{ color: 'var(--accent)' }} />}
        >
          <PerLanguageScoresContent />
        </SettingsSection>
      </div>
    </SettingsDetailLayout>
  )
}
