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
import { Star, FileType, Trash2, Film, Users, Heart } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'

// ─── Lazy sub-tabs ───────────────────────────────────────────────────────────

const ScoringTab = lazy(() =>
  import('./EventsTab').then((m) => ({ default: m.ScoringTab })),
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

// ─── Config value helpers ─────────────────────────────────────────────────────

function numVal(config: unknown, key: string, fallback = 0): number {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  if (v === undefined || v === null) return fallback
  const n = Number(v)
  return isNaN(n) ? fallback : n
}

function boolVal(config: unknown, key: string, fallback = false): boolean {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  if (v === undefined || v === null) return fallback
  return String(v) === 'true'
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
    </SettingsDetailLayout>
  )
}
