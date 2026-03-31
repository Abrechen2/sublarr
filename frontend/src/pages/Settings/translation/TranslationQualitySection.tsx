import { useState, useEffect } from 'react'
import { Activity } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'

// ─── Translation Quality Section ─────────────────────────────────────────────

export function TranslationQualitySection() {
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
        onSuccess: () => toast('Translation quality setting saved'),
        onError: () => toast('Failed to save setting', 'error'),
      },
    )
  }

  const handleThresholdBlur = () => {
    const clamped = Math.max(0, Math.min(100, Math.round(localThreshold)))
    if (clamped !== threshold) {
      updateConfig.mutate(
        { translation_quality_threshold: String(clamped) },
        {
          onSuccess: () => toast('Quality threshold saved'),
          onError: () => toast('Failed to save threshold', 'error'),
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
          onSuccess: () => toast('Max retries saved'),
          onError: () => toast('Failed to save max retries', 'error'),
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
          onSuccess: () => toast('Temperature saved'),
          onError: () => toast('Failed to save temperature', 'error'),
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
          onSuccess: () => toast('Batch size saved'),
          onError: () => toast('Failed to save batch size', 'error'),
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
          Translation Quality
        </h2>
      </div>

      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        Lines scoring below threshold are retried up to max retries.
      </p>

      <SettingRow
        label="Enable quality scoring"
        helpText="Score each translated line after translation and retry low-quality results."
      >
        <Toggle
          checked={enabled}
          onChange={handleEnabledChange}
          disabled={updateConfig.isPending}
        />
      </SettingRow>

      <SettingRow
        label="Quality threshold (0–100)"
        helpText="Lines scoring below this value are retried. Default: 50."
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
        label="Max retries (0–5)"
        helpText="Max retry attempts per line when quality is below threshold. Default: 2."
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
        label="Temperature (0.0–1.0)"
        helpText="LLM sampling temperature. Lower values are more deterministic; 0.1–0.3 recommended for translation. Default: 0.3."
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
        label="Batch size (lines)"
        helpText="Number of subtitle lines sent to the LLM per request. Smaller batches are slower but use less context. Default: 15."
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
