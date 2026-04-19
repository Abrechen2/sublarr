import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTranslationMemoryTelemetry } from '@/hooks/useTranslationCost'
import { useTranslationMutations } from '@/hooks/useTranslationMutations'
import { toast } from '@/components/shared/Toast'

export function TranslationMemoryPanel() {
  const { t } = useTranslation('settings')
  const { data } = useTranslationMemoryTelemetry()
  const { purgeMemory } = useTranslationMutations()
  const [days, setDays] = useState(30)

  const handlePurge = () => {
    if (!confirm(t('translation.memory.confirm_purge', { days }))) return
    purgeMemory.mutate(
      { older_than_days: days },
      {
        onSuccess: (r) =>
          toast(t('translation.memory.purged', { n: r.deleted }), 'success'),
        onError: (e: Error) => toast(e.message, 'error'),
      },
    )
  }

  if (!data) return null
  const sizeMb = (data.size_bytes / 1024 / 1024).toFixed(2)

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="font-medium">{t('translation.memory.title')}</h3>
      <div className="mt-2 flex gap-6 text-sm">
        <div>
          <div className="text-muted">{t('translation.memory.rows')}</div>
          <div className="font-semibold">{data.rows.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-muted">{t('translation.memory.size')}</div>
          <div className="font-semibold">{sizeMb} MB</div>
        </div>
        <div>
          <div className="text-muted">
            {t('translation.memory.hit_rate_7d')}
          </div>
          <div className="font-semibold">
            {(data.hit_rate_7d * 100).toFixed(1)}%
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <label className="text-sm text-muted">
          {t('translation.memory.purge_older_than')}
        </label>
        <input
          type="number"
          min={1}
          max={3650}
          value={days}
          onChange={(e) =>
            setDays(Math.max(1, Number(e.target.value) || 30))
          }
          className="w-20 rounded-md border border-border bg-surface px-2 py-1 text-sm"
        />
        <span className="text-sm text-muted">
          {t('translation.memory.days')}
        </span>
        <button
          onClick={handlePurge}
          disabled={purgeMemory.isPending}
          className="rounded-md bg-accent px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {t('translation.memory.purge')}
        </button>
      </div>
    </div>
  )
}
