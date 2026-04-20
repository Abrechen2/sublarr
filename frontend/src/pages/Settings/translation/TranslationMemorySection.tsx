import { useState, useEffect } from 'react'
import { Loader2, Trash2, Database } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { ConfirmModal } from '@/components/shared/ConfirmModal'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig, useTranslationMemoryStats, useClearTranslationMemoryCache } from '@/hooks/useApi'

// ─── Translation Memory Section ─────────────────────────────────────────────

  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const { data: stats, isLoading: statsLoading } = useTranslationMemoryStats()
  const clearCache = useClearTranslationMemoryCache()
  const [showClearConfirm, setShowClearConfirm] = useState(false)

  const enabled = config
    ? (config as Record<string, unknown>)['translation_memory_enabled'] !== 'false'
    : true

  const threshold = config
    ? Number((config as Record<string, unknown>)['translation_memory_similarity_threshold'] ?? 0.85)
    : 0.85

  const [localThreshold, setLocalThreshold] = useState<number>(threshold)

  useEffect(() => {
    setLocalThreshold(threshold)
  }, [threshold])

  const handleEnabledChange = (value: boolean) => {
    updateConfig.mutate(
      { translation_memory_enabled: String(value) },
      {
        onSuccess: () => toast('Translation memory setting saved'),
        onError: () => toast('Failed to save setting', 'error'),
      },
    )
  }

  const handleThresholdBlur = () => {
    const clamped = Math.max(0.0, Math.min(1.0, localThreshold))
    const rounded = Math.round(clamped * 20) / 20  // snap to 0.05 increments
    if (rounded !== threshold) {
      updateConfig.mutate(
        { translation_memory_similarity_threshold: String(rounded) },
        {
          onSuccess: () => toast('Similarity threshold saved'),
          onError: () => toast('Failed to save threshold', 'error'),
        },
      )
    }
  }

  const handleClearCache = () => {
    clearCache.mutate(undefined, {
      onSuccess: (result) => toast(`Translation memory cleared (${result.deleted} entries removed)`),
      onError: () => toast('Failed to clear translation memory', 'error'),
    })
  }

  return (
    <div
      className="rounded-lg p-5 space-y-4"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2">
        <Database size={16} style={{ color: 'var(--accent)' }} />
        <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          Translation Memory
        </h2>
        {!statsLoading && stats && (
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {stats.entries.toLocaleString()} cached {stats.entries === 1 ? 'entry' : 'entries'}
          </span>
        )}
      </div>

      <SettingRow
        label={t('translation_memory_section.enable')}
        helpText="Reuse previously translated lines that are similar to new ones, reducing LLM calls and improving consistency."
      >
        <Toggle
          checked={enabled}
          onChange={handleEnabledChange}
          disabled={updateConfig.isPending}
        />
      </SettingRow>

      <SettingRow
        label={t('translation_memory_section.similarity_threshold')}
        helpText="Minimum similarity (0.0–1.0) for a cached translation to be reused. 1.0 = exact match only; 0.8 = near-identical lines reused."
      >
        <input
          type="number"
          min={0.0}
          max={1.0}
          step={0.05}
          value={localThreshold}
          disabled={!enabled || updateConfig.isPending}
          onChange={(e) => {
            const parsed = parseFloat(e.target.value)
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

      <div className="flex items-center gap-3 pt-1" style={{ borderTop: '1px solid var(--border)' }}>
        <button
          onClick={() => setShowClearConfirm(true)}
          disabled={clearCache.isPending || (stats?.entries ?? 0) === 0}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--error)',
            backgroundColor: 'var(--bg-primary)',
            opacity: clearCache.isPending || (stats?.entries ?? 0) === 0 ? 0.5 : 1,
            cursor: clearCache.isPending || (stats?.entries ?? 0) === 0 ? 'not-allowed' : 'pointer',
          }}
          onMouseEnter={(e) => {
            if (!e.currentTarget.disabled) {
              e.currentTarget.style.borderColor = 'var(--error)'
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--border)'
          }}
        >
          {clearCache.isPending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Trash2 size={12} />
          )}
          Clear translation memory
        </button>
        {!statsLoading && stats && (
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {stats.entries === 0
              ? 'Cache is empty'
              : `${stats.entries.toLocaleString()} ${stats.entries === 1 ? 'entry' : 'entries'} stored`}
          </span>
        )}
      </div>
      <ConfirmModal
        open={showClearConfirm}
        title={t('translation_memory_section.clear')}
        message="Clear all cached translations? This cannot be undone."
        confirmLabel="Clear"
        onConfirm={() => { setShowClearConfirm(false); handleClearCache() }}
        onCancel={() => setShowClearConfirm(false)}
      />
    </div>
  )
}
