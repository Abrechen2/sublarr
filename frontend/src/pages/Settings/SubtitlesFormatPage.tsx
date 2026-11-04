/**
 * SubtitlesFormatPage — Format & Naming settings sub-page.
 *
 * Sections:
 * 1. Embedded Extraction — auto-extract, embedded subs usage (advanced, collapsed)
 */
import { useTranslation } from 'react-i18next'
import { Film } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { boolVal, numVal } from '@/lib/configUtils'

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
        label={t(
          'settings.subtitles.embeddedExtraction.maxAssSubtitleSize',
          'Maximum ASS/SSA subtitle size (MiB)',
        )}
        hint={t(
          'settings.subtitles.embeddedExtraction.maxAssSubtitleSizeHint',
          'Files above this size are rejected by the subtitle sanitizer. Default: 20 MiB; allowed range: 1 to 50 MiB. SRT/VTT remain capped at 5 MiB.',
        )}
        htmlFor="max-ass-subtitle-size-mb"
        data-testid="form-group-max-ass-subtitle-size-mb"
      >
        <input
          id="max-ass-subtitle-size-mb"
          type="number"
          data-testid="input-max-ass-subtitle-size-mb"
          defaultValue={numVal(config, 'max_ass_subtitle_size_mb', 20)}
          min={1}
          max={50}
          step={1}
          onBlur={(e) => {
            const value = Number(e.currentTarget.value)
            if (Number.isInteger(value) && value >= 1 && value <= 50) {
              save({ max_ass_subtitle_size_mb: value })
            }
          }}
          disabled={isPending}
          className="w-24 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)]"
        />
      </FormGroup>

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

// Settings Template B (FormLayout). Single section.
const SECTIONS: readonly FormSectionDef[] = [
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

      {/* Embedded Extraction (advanced — collapsed by default) */}
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
