import { useState, useEffect } from 'react'
import { Loader2, Trash2, Database } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { ConfirmModal } from '@/components/shared/ConfirmModal'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig, useTranslationMemoryStats, useClearTranslationMemoryCache } from '@/hooks/useApi'
import { useTranslation } from 'react-i18next'

// ─── Translation Memory Section ─────────────────────────────────────────────

export function TranslationMemorySection() {
  const { t } = useTranslation('settings')
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
        onSuccess: () => toast(t('translation_memory_section.toast_setting_saved')),
        onError: () => toast(t('translation_memory_section.toast_save_failed'), 'error'),
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
          onSuccess: () => toast(t('translation_memory_section.toast_threshold_saved')),
          onError: () => toast(t('translation_memory_section.toast_threshold_failed'), 'error'),
        },
      )
    }
  }

  const handleClearCache = () => {
    clearCache.mutate(undefined, {
      onSuccess: (result) => toast(t('translation_memory_section.toast_cleared', { count: result.deleted })),
      onError: () => toast(t('translation_memory_section.toast_clear_failed'), 'error'),
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
          {t('translation_memory_section.title')}
        </h2>
        {!statsLoading && stats && (
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {t('translation_memory_section.cached_entries', { count: stats.entries })}
          </span>
        )}
      </div>

      <SettingRow
        label={t('translation_memory_section.enable')}
        helpText={t('translation_memory_section.enable_help')}
      >
        <Toggle
          checked={enabled}
          onChange={handleEnabledChange}
          disabled={updateConfig.isPending}
        />
      </SettingRow>

      <SettingRow
        label={t('translation_memory_section.similarity_threshold')}
        helpText={t('translation_memory_section.threshold_help')}
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
          {t('translation_memory_section.clear_button')}
        </button>
        {!statsLoading && stats && (
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {stats.entries === 0
              ? t('translation_memory_section.cache_empty')
              : t('translation_memory_section.entries_stored', { count: stats.entries })}
          </span>
        )}
      </div>
      <ConfirmModal
        open={showClearConfirm}
        title={t('translation_memory_section.clear')}
        message={t('translation_memory_section.clear_confirm_message')}
        confirmLabel={t('translation_memory_section.clear_confirm_label')}
        onConfirm={() => { setShowClearConfirm(false); handleClearCache() }}
        onCancel={() => setShowClearConfirm(false)}
      />
    </div>
  )
}
