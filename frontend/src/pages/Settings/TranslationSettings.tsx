/**
 * TranslationSettings — Settings page for translation configuration.
 *
 * Six sections:
 * 1. Translation Backends  – backend configuration
 * 2. Prompt Presets        – prompt preset management
 * 3. Global Glossary       – shared glossary entries
 * 4. Context & Quality (advanced) – context window, quality, memory settings
 * 5. Sync Engine (advanced)       – default sync engine and auto-sync
 * 6. Whisper (advanced)           – speech-to-text configuration
 */
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Server, MessageSquare, BookOpen, Settings2, RefreshCw, Mic } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'

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
const WhisperTab = lazy(() =>
  import('./WhisperTab').then((m) => ({ default: m.WhisperTab })),
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

  return (
    <SettingsDetailLayout
      title={t('settings.categories.translation.title', 'Translation')}
      subtitle={t(
        'settings.categories.translation.description',
        'Backends, prompts, glossary, quality, and sync settings',
      )}
    >
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

      {/* 6. Whisper (Speech-to-Text) (advanced — collapsed by default) */}
      <div data-testid="section-whisper">
        <SettingsSection
          title={t('settings.translation.whisper.title', 'Whisper (Speech-to-Text)')}
          description={t(
            'settings.translation.whisper.description',
            'Configure the Whisper speech-to-text engine for generating subtitles from audio.',
          )}
          icon={<Mic size={16} style={{ color: 'var(--accent)' }} />}
          advanced={
            <Suspense fallback={<SectionSkeleton />}>
              <WhisperTab />
            </Suspense>
          }
        >
          <p
            className="text-[12px] text-[var(--text-muted)] py-2"
            data-testid="whisper-summary"
          >
            {t(
              'settings.translation.whisper.summary',
              'Generate subtitles directly from audio tracks using the OpenAI Whisper speech recognition model.',
            )}
          </p>
        </SettingsSection>
      </div>
    </SettingsDetailLayout>
  )
}
