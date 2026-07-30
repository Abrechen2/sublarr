import { useTranslation } from 'react-i18next'
import { Sparkles } from 'lucide-react'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'

const inputStyle = {
  backgroundColor: 'var(--bg-primary)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '0.375rem',
  padding: '0.375rem 0.75rem',
  fontSize: '0.8125rem',
  outline: 'none',
  width: '220px',
}

/**
 * AIQualitySettings — advisory AI subtitle-quality badge (experimental).
 * Maps to ai_quality_enabled, ai_quality_model, ai_quality_max_cues.
 * The verdict is display-only: it never modifies files and never feeds
 * into scoring or upgrades (ROADMAP "AI direction" guardrails).
 */
export function AIQualitySettings() {
  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const cfg = config as Record<string, unknown> | undefined

  const enabled = String(cfg?.ai_quality_enabled ?? 'false') === 'true'
  const model = String(cfg?.ai_quality_model ?? '')
  const maxCues = Number(cfg?.ai_quality_max_cues ?? 30)

  return (
    <SettingsSection
      title={t('ai_quality_page.title', 'AI Quality Check')}
      description={t(
        'ai_quality_page.description',
        'Experimental: after each download, a local LLM samples a few lines and rates machine-translation likelihood, OCR artifacts and grammar. Shown as a badge in History — advisory only, never changes files or scores.',
      )}
      icon={<Sparkles size={16} style={{ color: 'var(--accent)' }} />}
    >
      <SettingRow
        label={t('ai_quality_page.enabled_label', 'AI quality badge')}
        description={t(
          'ai_quality_page.enabled_desc',
          'Analyze new downloads in the background using the configured Ollama instance. Requires a reachable Ollama server (Settings → Translation).',
        )}
      >
        <div data-testid="toggle-ai-quality">
          <Toggle
            checked={enabled}
            onChange={(v) => updateConfig.mutate({ ai_quality_enabled: String(v) })}
          />
        </div>
      </SettingRow>

      <SettingRow
        label={t('ai_quality_page.model_label', 'Model override')}
        description={t(
          'ai_quality_page.model_desc',
          'Ollama model used for the check. Leave empty to reuse the translation model.',
        )}
      >
        <input
          type="text"
          defaultValue={model}
          placeholder={t('ai_quality_page.model_placeholder', 'empty = translation model')}
          style={inputStyle}
          onBlur={(e) => {
            const v = e.target.value.trim()
            if (v !== model) updateConfig.mutate({ ai_quality_model: v })
          }}
        />
      </SettingRow>

      <SettingRow
        label={t('ai_quality_page.max_cues_label', 'Sampled lines')}
        description={t(
          'ai_quality_page.max_cues_desc',
          'How many lines are sampled per file (10–60). More lines = better judgement, slower check.',
        )}
      >
        <input
          type="number"
          min={10}
          max={60}
          defaultValue={maxCues}
          style={{ ...inputStyle, width: '90px' }}
          onBlur={(e) => {
            const n = Math.round(Number(e.target.value))
            if (!Number.isFinite(n)) return
            const v = Math.min(60, Math.max(10, n))
            if (v !== maxCues) updateConfig.mutate({ ai_quality_max_cues: v })
          }}
        />
      </SettingRow>
    </SettingsSection>
  )
}

export default AIQualitySettings
