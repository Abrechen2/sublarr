/**
 * SubtitlesScoringPage — Scoring settings sub-page.
 *
 * Sections:
 * 1. Scoring              — weights, presets, release groups (ScoringTab)
 * 2. Per-Language Scores  — per-language minimum score thresholds
 * 3. Fansub Preferences   — credit/OP window detection (advanced, collapsed)
 */
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Star, Sliders, Heart } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'

import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal, numVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

// ─── Lazy sub-tabs ────────────────────────────────────────────────────────────

const ScoringTab = lazy(() =>
  import('./ScoringTab').then((m) => ({ default: m.ScoringTab })),
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

// ─── Page ─────────────────────────────────────────────────────────────────────

export function SubtitlesScoringPage() {
  const { t } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title={t('settings.subtitles.scoringPage.title', 'Scoring')}
      subtitle={t(
        'settings.subtitles.scoringPage.subtitle',
        'Configure how subtitles are ranked and selected — weights, presets, release groups, and per-language thresholds.',
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

      {/* 2. Per-Language Score Thresholds */}
      <div data-testid="section-per-language-scores">
        <SettingsSection
          title={t('settings.subtitles.perLanguageScores.title')}
          description={t('settings.subtitles.perLanguageScores.description')}
          icon={<Sliders size={16} style={{ color: 'var(--accent)' }} />}
        >
          <PerLanguageScoresContent />
        </SettingsSection>
      </div>

      {/* 3. Fansub Preferences (advanced — collapsed by default) */}
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
