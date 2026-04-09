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
  const { t } = useTranslation('common')
  const { t: tTranslation } = useTranslation('settings')
  const navigate = useNavigate()
  const [showDisableConfirm, setShowDisableConfirm] = useState(false)
  const disableTranslation = useDisableTranslation()
  const { data: config } = useConfig()
  const { mutate: updateConfig } = useUpdateConfig()

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
            Beta Feature
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Die KI-Übersetzungsfunktion ist experimentell und funktioniert aktuell nicht zuverlässig genug für den produktiven Einsatz. Ergebnisse können stark variieren — abhängig von Modell, Prompt und Eingabequalität. Nutzung auf eigenes Risiko.
          </span>
        </div>
      </div>

      {/* 1. Translation Backends */}
      <div data-testid="section-translation-backends">
        <SettingsSection
          title={t('settings.translation.backends.title', 'Translation Backends')}
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

      {/* 2. Prompt Presets */}
      <div data-testid="section-prompt-presets">
        <SettingsSection
          title={t('settings.translation.promptPresets.title', 'Prompt Presets')}
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

      {/* 3. Global Glossary */}
      <div data-testid="section-global-glossary">
        <SettingsSection
          title={t('settings.translation.globalGlossary.title', 'Global Glossary')}
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

      {/* 4. Context & Quality (advanced — collapsed by default) */}
      <div data-testid="section-context-quality">
        <SettingsSection
          title={t('settings.translation.contextQuality.title', 'Context & Quality')}
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
                label="Translation Workers"
                hint="Maximum parallel translation worker threads."
                htmlFor="translation-max-workers"
              >
                <input
                  id="translation-max-workers"
                  type="number"
                  data-testid="input-translation-max-workers"
                  style={{ ...settingsInputStyle, width: '100px', outline: 'none' }}
                  value={Number(strVal(config, 'translation_max_workers', '2'))}
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

      {/* 5. Sync Engine (advanced — collapsed by default) */}
      <div data-testid="section-sync-engine">
        <SettingsSection
          title={t('settings.translation.syncEngine.title', 'Sync Engine')}
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

      {/* 6. Whisper — navigates to dedicated Transcription page */}
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
          Configure →
        </Link>
      </div>
      {/* 7. Episode Context (Step 45) */}
      <div data-testid="section-translation-context-wrapper">
        <SettingsSection
          title={t('settings.translation.episodeContext.title', 'Episode Context')}
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
      {/* Danger Zone — Disable Translation */}
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
                Translation deaktivieren
              </div>
              <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                Deaktiviert die Translation-Funktion und bricht alle wartenden Jobs ab.
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
            Disable Translation
          </button>
        </div>

        {showDisableConfirm && (
          <div
            className="mt-3 pt-3 flex items-center justify-between gap-4"
            style={{ borderTop: '1px solid var(--error)' }}
          >
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              Wirklich deaktivieren? Alle wartenden Translation-Jobs werden abgebrochen.
            </span>
            <div className="flex gap-2 shrink-0">
              <button
                onClick={() => setShowDisableConfirm(false)}
                className="px-3 py-1.5 rounded-md text-sm"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              >
                Abbrechen
              </button>
              <button
                onClick={handleDisableConfirm}
                disabled={disableTranslation.isPending}
                className="px-3 py-1.5 rounded-md text-sm font-semibold"
                style={{ backgroundColor: 'var(--error)', color: '#fff' }}
              >
                {disableTranslation.isPending ? 'Deaktiviere…' : 'Bestätigen'}
              </button>
            </div>
          </div>
        )}
      </div>
    </SettingsDetailLayout>
  )
}
