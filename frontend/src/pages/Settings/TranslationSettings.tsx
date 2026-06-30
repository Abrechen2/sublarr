/**
 * TranslationSettings — Settings page for translation configuration.
 *
 * Seven sections + danger zone:
 * 1. Translation Backends  – backend configuration
 * 2. Prompt Presets        – prompt preset management
 * 3. Global Glossary       – shared glossary entries
 * 4. Context & Quality (advanced) – context window, quality, memory settings
 * 5. Sync Engine (advanced)       – default sync engine and auto-sync
 * 6. Whisper (advanced)           – speech-to-text configuration
 * 7. Episode Context       – per-series context and glossary
 * Danger Zone: Disable Translation button (not a SettingsSection, styled separately)
 */
import { lazy, Suspense, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Server, MessageSquare, BookOpen, Settings2, RefreshCw, Layers, FlaskConical, AlertTriangle } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'

// Settings Template B (FormLayout). Six sections — exactly at the cap.
//
// The Whisper link-tile is rendered between Sync Engine and Episode Context
// but DELIBERATELY excluded from the TOC: it's a navigation cross-link to
// the dedicated Transcription page, not a TranslationSettings section. The
// Beta-banner (top) and Danger Zone (bottom) are page-chrome, not sections,
// so they also live outside the FormLayout grid.
//
// If a 7th real section ever needs to land here, the page MUST split into
// a sub-page (e.g. /settings/translation/quality for Context+Sync+Episode)
// — adding it inline would trip the dev-mode 6-section warn.
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'backends',        titleKey: 'translation_page.backends_section' },
  { id: 'prompts',         titleKey: 'translation_page.prompts_section' },
  { id: 'glossary',        titleKey: 'translation_page.glossary_section' },
  { id: 'context-quality', titleKey: 'translation_page.context_quality_section' },
  { id: 'sync',            titleKey: 'translation_page.sync_section' },
  { id: 'episode-context', titleKey: 'translation_page.episode_context_section' },
]
import { EpisodeContextSection } from './TranslationTab'
import { useConfig, useUpdateConfig, useDisableTranslation } from '@/hooks/useApi'
import { strVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

// ─── Lazy sub-tabs ───────────────────────────────────────────────────────────

const TranslationBackendsTab = lazy(() =>
  import('./TranslationTab').then((m) => ({ default: m.TranslationBackendsTab })),
)
const PromptPresetsTab = lazy(() =>
  import('./TranslationTab').then((m) => ({ default: m.PromptPresetsTab })),
)
const GlobalGlossaryPanel = lazy(() =>
  import('./TranslationTab').then((m) => ({ default: m.GlobalGlossaryPanel })),
)
const ContextWindowSizeRow = lazy(() =>
  import('./TranslationTab').then((m) => ({ default: m.ContextWindowSizeRow })),
)
const TranslationQualitySection = lazy(() =>
  import('./TranslationTab').then((m) => ({ default: m.TranslationQualitySection })),
)
const TranslationMemorySection = lazy(() =>
  import('./TranslationTab').then((m) => ({ default: m.TranslationMemorySection })),
)
const DefaultSyncEngineRow = lazy(() =>
  import('./TranslationTab').then((m) => ({ default: m.DefaultSyncEngineRow })),
)
const AutoSyncSection = lazy(() =>
  import('./TranslationTab').then((m) => ({ default: m.AutoSyncSection })),
)
// ─── Skeleton ─────────────────────────────────────────────────────────────────

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

// ─── TranslationSettings Page ─────────────────────────────────────────────────

export function TranslationSettings() {
  const { t } = useTranslation('settings')
  const { t: tTranslation } = useTranslation('settings')
  const { t: tc } = useTranslation('common')
  const navigate = useNavigate()
  const [showDisableConfirm, setShowDisableConfirm] = useState(false)
  const disableTranslation = useDisableTranslation()
  const { data: config } = useConfig()
  const { mutate: updateConfig } = useUpdateConfig()
  // config_entries stores this as the string 'true'/'false', so Boolean() is
  // wrong (Boolean('false') === true). Match the codebase string-bool pattern.
  const translationEnabled =
    config?.translation_enabled === true || config?.translation_enabled === 'true'

  function handleEnable() {
    updateConfig({ translation_enabled: 'true' })
  }

  function handleDisableConfirm() {
    disableTranslation.mutate(undefined, {
      onSuccess: () => navigate('/settings'),
      onError: () => setShowDisableConfirm(false),
    })
  }

  return (
    <SettingsDetailLayout
      title={t('settings.categories.translation.title', 'Translation')}
      subtitle={t(
        'settings.categories.translation.description',
        'Backends, prompts, glossary, quality, and sync settings',
      )}
    >
      {/* Beta warning banner */}
      <div
        data-testid="translation-beta-banner"
        style={{
          display: 'flex',
          gap: 12,
          padding: '12px 16px',
          borderRadius: 8,
          backgroundColor: 'var(--warning-bg, rgba(245,158,11,0.1))',
          border: '1px solid var(--warning, #f59e0b)',
          marginBottom: 8,
        }}
      >
        <FlaskConical size={18} style={{ color: 'var(--warning, #f59e0b)', flexShrink: 0, marginTop: 1 }} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--warning, #f59e0b)' }}>
            {t('translation_page.beta_title', 'Beta Feature')}
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {t('translation_page.beta_body')}
          </span>
        </div>
        {!translationEnabled && (
          <button
            onClick={handleEnable}
            data-testid="enable-translation-btn"
            className="shrink-0 self-center px-3 py-1.5 rounded-md text-sm font-semibold"
            style={{
              marginLeft: 'auto',
              backgroundColor: 'var(--warning, #f59e0b)',
              color: '#fff',
              border: 'none',
            }}
          >
            {t('translation_page.enable_button', 'Enable translation')}
          </button>
        )}
      </div>

      {!translationEnabled && (
        <div
          data-testid="translation-disabled-hint"
          className="text-xs"
          style={{ color: 'var(--text-muted)', margin: '0 2px 8px' }}
        >
          {t('translation_page.disabled_hint')}
        </div>
      )}

      <FormLayout sections={SECTIONS}>

      {/* 1. Translation Backends */}
      <section id="backends" data-testid="settings.translation.section-backends">
      <div data-testid="section-translation-backends">
        <SettingsSection
          title={t('translation_page.backends_section')}
          description={t(
            'settings.translation.backends.description',
            'Configure translation engines and providers used to translate subtitles.',
          )}
          icon={<Server size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="translation-backends-content">
            <Suspense fallback={<SectionSkeleton />}>
              <TranslationBackendsTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>
      </section>

      {/* 2. Prompt Presets */}
      <section id="prompts" data-testid="settings.translation.section-prompts">
      <div data-testid="section-prompt-presets">
        <SettingsSection
          title={t('translation_page.prompts_section')}
          description={t(
            'settings.translation.promptPresets.description',
            'Manage reusable prompt templates for translation backends.',
          )}
          icon={<MessageSquare size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="prompt-presets-content">
            <Suspense fallback={<SectionSkeleton />}>
              <PromptPresetsTab />
            </Suspense>
          </div>
        </SettingsSection>
      </div>
      </section>

      {/* 3. Global Glossary */}
      <section id="glossary" data-testid="settings.translation.section-glossary">
      <div data-testid="section-global-glossary">
        <SettingsSection
          title={t('translation_page.glossary_section')}
          description={t(
            'settings.translation.globalGlossary.description',
            'Define term pairs that are applied consistently across all translations.',
          )}
          icon={<BookOpen size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="global-glossary-content">
            <Suspense fallback={<SectionSkeleton />}>
              <GlobalGlossaryPanel />
            </Suspense>
          </div>
        </SettingsSection>
      </div>
      </section>

      {/* 4. Context & Quality (advanced — collapsed by default) */}
      <section id="context-quality" data-testid="settings.translation.section-context-quality">
      <div data-testid="section-context-quality">
        <SettingsSection
          title={t('translation_page.context_quality_section')}
          description={t(
            'settings.translation.contextQuality.description',
            'Fine-tune context window size, quality thresholds, and translation memory.',
          )}
          icon={<Settings2 size={16} style={{ color: 'var(--accent)' }} />}
          advanced={
            <Suspense fallback={<SectionSkeleton />}>
              <ContextWindowSizeRow />
              <TranslationQualitySection />
              <TranslationMemorySection />
              <FormGroup
                label={tc('ui.translation_workers')}
                hint={t('translation_page.workers_hint', 'Maximum parallel translation worker threads.')}
                htmlFor="translation-max-workers"
              >
                <input
                  id="translation-max-workers"
                  type="number"
                  data-testid="input-translation-max-workers"
                  style={{ ...settingsInputStyle, width: '100px', outline: 'none' }}
                  value={Number(strVal(config, 'translation_max_workers', '4'))}
                  onChange={(e) => updateConfig({ translation_max_workers: Number(e.target.value) })}
                  min={1}
                  max={16}
                />
              </FormGroup>
            </Suspense>
          }
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-2"
            data-testid="context-quality-summary"
          >
            {t(
              'settings.translation.contextQuality.summary',
              'Adjust how much surrounding context is used during translation and configure quality controls.',
            )}
          </p>
        </SettingsSection>
      </div>
      </section>

      {/* 5. Sync Engine (advanced — collapsed by default) */}
      <section id="sync" data-testid="settings.translation.section-sync">
      <div data-testid="section-sync-engine">
        <SettingsSection
          title={t('translation_page.sync_section')}
          description={t(
            'settings.translation.syncEngine.description',
            'Choose the default synchronisation engine and configure automatic sync behaviour.',
          )}
          icon={<RefreshCw size={16} style={{ color: 'var(--accent)' }} />}
          advanced={
            <Suspense fallback={<SectionSkeleton />}>
              <DefaultSyncEngineRow />
              <AutoSyncSection />
            </Suspense>
          }
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-2"
            data-testid="sync-engine-summary"
          >
            {t(
              'settings.translation.syncEngine.summary',
              'Controls which subtitle synchronisation engine is used and when automatic sync runs.',
            )}
          </p>
        </SettingsSection>
      </div>
      </section>

      {/* Whisper — navigation cross-link to dedicated Transcription page.
          Intentionally NOT in the FormLayout TOC: it's a cross-page link,
          not a TranslationSettings section. Rendered inside the form
          column so it sits visually between Sync Engine and Episode
          Context where it belongs. */}
      <div
        data-testid="section-whisper"
        style={{
          padding: '14px 18px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {tTranslation('transcription_page.title')}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
            {tTranslation('transcription_page.subtitle')}
          </div>
        </div>
        <Link
          to="/settings/providers/transcription"
          style={{ fontSize: '12px', color: 'var(--accent)' }}
        >
          {t('translation_page.configure_link', 'Configure →')}
        </Link>
      </div>
      {/* 6. Episode Context (Step 45) */}
      <section id="episode-context" data-testid="settings.translation.section-episode-context">
      <div data-testid="section-translation-context-wrapper">
        <SettingsSection
          title={t('translation_page.episode_context_section')}
          description={t(
            'settings.translation.episodeContext.description',
            'Use prior episode subtitles as translation context and build per-series glossaries.',
          )}
          icon={<Layers size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div data-testid="episode-context-content">
            <EpisodeContextSection />
          </div>
        </SettingsSection>
      </div>
      </section>

      </FormLayout>

      {/* Danger Zone — Disable Translation (only when enabled) */}
      {translationEnabled && (
      <div
        data-testid="section-disable-translation"
        style={{
          marginTop: 16,
          padding: '16px 20px',
          borderRadius: 8,
          border: '1px solid var(--error)',
          backgroundColor: 'var(--error-bg)',
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} style={{ color: 'var(--error)', flexShrink: 0, marginTop: 1 }} />
            <div>
              <div className="font-semibold text-sm" style={{ color: 'var(--error)' }}>
                {t('translation_page.disable_title', 'Disable translation')}
              </div>
              <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                {t('translation_page.disable_desc')}
              </div>
            </div>
          </div>
          <button
            onClick={() => setShowDisableConfirm(true)}
            className="shrink-0 px-3 py-1.5 rounded-md text-sm font-medium"
            style={{
              border: '1px solid var(--error)',
              color: 'var(--error)',
              backgroundColor: 'transparent',
            }}
          >
            {t('translation_page.disable_button', 'Disable translation')}
          </button>
        </div>

        {showDisableConfirm && (
          <div
            className="mt-3 pt-3 flex items-center justify-between gap-4"
            style={{ borderTop: '1px solid var(--error)' }}
          >
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('translation_page.disable_confirm')}
            </span>
            <div className="flex gap-2 shrink-0">
              <button
                onClick={() => setShowDisableConfirm(false)}
                className="px-3 py-1.5 rounded-md text-sm"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              >
                {t('translation_page.cancel', 'Cancel')}
              </button>
              <button
                onClick={handleDisableConfirm}
                disabled={disableTranslation.isPending}
                className="px-3 py-1.5 rounded-md text-sm font-semibold"
                style={{ backgroundColor: 'var(--error)', color: '#fff' }}
              >
                {disableTranslation.isPending ? t('translation_page.disabling', 'Disabling…') : t('translation_page.confirm', 'Confirm')}
              </button>
            </div>
          </div>
        )}
      </div>
      )}
    </SettingsDetailLayout>
  )
}
