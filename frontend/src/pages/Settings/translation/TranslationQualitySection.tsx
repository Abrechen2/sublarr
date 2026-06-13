import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'

// ─── Translation Quality Section ─────────────────────────────────────────────

export function TranslationQualitySection() {
  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()

  const enabled = config
    ? (config as Record<string, unknown>)['translation_quality_enabled'] !== 'false'
    : true

  const threshold = config
    ? Number((config as Record<string, unknown>)['translation_quality_threshold'] ?? 50)
    : 50

  const maxRetries = config
    ? Number((config as Record<string, unknown>)['translation_quality_max_retries'] ?? 2)
    : 2

  const temperature = config
    ? Number((config as Record<string, unknown>)['temperature'] ?? 0.3)
    : 0.3

  const batchSize = config
    ? Number((config as Record<string, unknown>)['batch_size'] ?? 15)
    : 15

  const [localThreshold, setLocalThreshold] = useState<number>(threshold)
  const [localMaxRetries, setLocalMaxRetries] = useState<number>(maxRetries)
  const [localTemperature, setLocalTemperature] = useState<number>(temperature)
  const [localBatchSize, setLocalBatchSize] = useState<number>(batchSize)

  useEffect(() => { setLocalThreshold(threshold) }, [threshold])
  useEffect(() => { setLocalMaxRetries(maxRetries) }, [maxRetries])
  useEffect(() => { setLocalTemperature(temperature) }, [temperature])
  useEffect(() => { setLocalBatchSize(batchSize) }, [batchSize])

  const handleEnabledChange = (value: boolean) => {
    updateConfig.mutate(
      { translation_quality_enabled: String(value) },
      {
        onSuccess: () => toast(t('translation_quality.toast_setting_saved')),
        onError: () => toast(t('translation_quality.toast_save_failed'), 'error'),
      },
    )
  }

  const handleThresholdBlur = () => {
    const clamped = Math.max(0, Math.min(100, Math.round(localThreshold)))
    if (clamped !== threshold) {
      updateConfig.mutate(
        { translation_quality_threshold: String(clamped) },
        {
          onSuccess: () => toast(t('translation_quality.toast_threshold_saved')),
          onError: () => toast(t('translation_quality.toast_threshold_failed'), 'error'),
        },
      )
    }
  }

  const handleMaxRetriesBlur = () => {
    const clamped = Math.max(0, Math.min(5, Math.round(localMaxRetries)))
    if (clamped !== maxRetries) {
      updateConfig.mutate(
        { translation_quality_max_retries: String(clamped) },
        {
          onSuccess: () => toast(t('translation_quality.toast_max_retries_saved')),
          onError: () => toast(t('translation_quality.toast_max_retries_failed'), 'error'),
        },
      )
    }
  }

  const handleTemperatureBlur = () => {
    const clamped = Math.max(0, Math.min(1, Math.round(localTemperature * 10) / 10))
    if (String(clamped) !== String(temperature)) {
      updateConfig.mutate(
        { temperature: String(clamped) },
        {
          onSuccess: () => toast(t('translation_quality.toast_temperature_saved')),
          onError: () => toast(t('translation_quality.toast_temperature_failed'), 'error'),
        },
      )
    }
  }

  const handleBatchSizeBlur = () => {
    const clamped = Math.max(1, Math.min(100, Math.round(localBatchSize)))
    if (String(clamped) !== String(batchSize)) {
      updateConfig.mutate(
        { batch_size: String(clamped) },
        {
          onSuccess: () => toast(t('translation_quality.toast_batch_size_saved')),
          onError: () => toast(t('translation_quality.toast_batch_size_failed'), 'error'),
        },
      )
    }
  }

  return (
    <div
      className="rounded-lg p-5 space-y-4"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2">
        <Activity size={16} style={{ color: 'var(--accent)' }} />
        <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('translation_quality.title')}
        </h2>
      </div>

      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        {t('translation_quality.intro')}
      </p>

      <SettingRow
        label={t('translation_quality.enable_quality_scoring')}
        helpText={t('translation_quality.enable_help')}
      >
        <Toggle
          checked={enabled}
          onChange={handleEnabledChange}
          disabled={updateConfig.isPending}
        />
      </SettingRow>

      <SettingRow
        label={t('translation_quality.quality_threshold')}
        helpText={t('translation_quality.threshold_help')}
      >
        <input
          type="number"
          min={0}
          max={100}
          step={1}
          value={localThreshold}
          disabled={!enabled || updateConfig.isPending}
          onChange={(e) => {
            const parsed = parseInt(e.target.value, 10)
            if (!isNaN(parsed)) setLocalThreshold(parsed)
          }}
          onBlur={handleThresholdBlur}
          className="w-24 px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontSize: '13px',
            opacity: enabled ? 1 : 0.5,
          }}
        />
      </SettingRow>

      <SettingRow
        label={t('translation_quality.max_retries')}
        helpText={t('translation_quality.max_retries_help')}
      >
        <input
          type="number"
          min={0}
          max={5}
          step={1}
          value={localMaxRetries}
          disabled={!enabled || updateConfig.isPending}
          onChange={(e) => {
            const parsed = parseInt(e.target.value, 10)
            if (!isNaN(parsed)) setLocalMaxRetries(parsed)
          }}
          onBlur={handleMaxRetriesBlur}
          className="w-24 px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontSize: '13px',
            opacity: enabled ? 1 : 0.5,
          }}
        />
      </SettingRow>

      <SettingRow
        label={t('translation_quality.temperature')}
        helpText={t('translation_quality.temperature_help')}
      >
        <input
          data-testid="input-temperature"
          type="number"
          min={0}
          max={1}
          step={0.1}
          value={localTemperature}
          disabled={updateConfig.isPending}
          onChange={(e) => {
            const parsed = parseFloat(e.target.value)
            if (!isNaN(parsed)) setLocalTemperature(parsed)
          }}
          onBlur={handleTemperatureBlur}
          className="w-24 px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontSize: '13px',
          }}
        />
      </SettingRow>

      <SettingRow
        label={t('translation_quality.batch_size')}
        helpText={t('translation_quality.batch_size_help')}
      >
        <input
          data-testid="input-batch_size"
          type="number"
          min={1}
          max={100}
          step={1}
          value={localBatchSize}
          disabled={updateConfig.isPending}
          onChange={(e) => {
            const parsed = parseInt(e.target.value, 10)
            if (!isNaN(parsed)) setLocalBatchSize(parsed)
          }}
          onBlur={handleBatchSizeBlur}
          className="w-24 px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontSize: '13px',
          }}
        />
      </SettingRow>
    </div>
  )
}
