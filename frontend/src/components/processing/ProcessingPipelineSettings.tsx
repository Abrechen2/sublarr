import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { InterjectionListEditor } from './InterjectionListEditor'

interface PipelineConfig {
  auto_process_common_fixes: boolean
  auto_process_hi_removal: boolean
  auto_process_credit_removal: boolean
  auto_sync_after_download: boolean
  auto_process_sync_threshold: number
  auto_sync_engine: string
  auto_process_sync_fallback_engine: string
}

interface Props {
  config: PipelineConfig
  onSave: (updates: Partial<PipelineConfig>) => void
}

export function ProcessingPipelineSettings({ config, onSave }: Props) {
  const { t } = useTranslation('settings')
  const [hiExpanded, setHiExpanded] = useState(false)

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-zinc-300">
        {t('automation_page.processing_pipeline.heading')}
      </h3>

      {/* Common Fixes */}
      <div className="flex items-center justify-between py-2 border-b border-zinc-800">
        <span className="text-sm text-zinc-300">
          {t('automation_page.processing_pipeline.common_fixes')}
        </span>
        <input
          type="checkbox"
          checked={config.auto_process_common_fixes}
          onChange={e => onSave({ auto_process_common_fixes: e.target.checked })}
          className="w-4 h-4 accent-blue-500"
        />
      </div>

      {/* HI Removal */}
      <div className="border-b border-zinc-800 pb-2">
        <div className="flex items-center justify-between py-2">
          <button
            onClick={() => setHiExpanded(v => !v)}
            className="flex items-center gap-1 text-sm text-zinc-300"
          >
            {hiExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {t('automation_page.processing_pipeline.hi_removal')}
          </button>
          <input
            type="checkbox"
            checked={config.auto_process_hi_removal}
            onChange={e => onSave({ auto_process_hi_removal: e.target.checked })}
            className="w-4 h-4 accent-blue-500"
          />
        </div>
        {hiExpanded && (
          <div className="pl-4 pt-2">
            <InterjectionListEditor />
          </div>
        )}
      </div>

      {/* Credit Removal */}
      <div className="flex items-center justify-between py-2 border-b border-zinc-800">
        <span className="text-sm text-zinc-300">
          {t('automation_page.processing_pipeline.credit_removal')}
        </span>
        <input
          type="checkbox"
          checked={config.auto_process_credit_removal}
          onChange={e => onSave({ auto_process_credit_removal: e.target.checked })}
          className="w-4 h-4 accent-blue-500"
        />
      </div>

      {/* Auto-Sync */}
      <div className="space-y-2 py-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">
            {t('automation_page.processing_pipeline.auto_sync')}
          </span>
          <input
            type="checkbox"
            checked={config.auto_sync_after_download}
            onChange={e => onSave({ auto_sync_after_download: e.target.checked })}
            className="w-4 h-4 accent-blue-500"
          />
        </div>
        {config.auto_sync_after_download && (
          <div className="pl-4 space-y-2 text-xs text-zinc-400">
            <div className="flex items-center gap-2">
              <span>{t('automation_page.processing_pipeline.score_threshold')}</span>
              <input
                type="number"
                min={0}
                max={100}
                value={config.auto_process_sync_threshold}
                onChange={e => onSave({ auto_process_sync_threshold: Number(e.target.value) })}
                className="w-16 bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5"
              />
            </div>
            <div className="flex items-center gap-2">
              <span>{t('automation_page.processing_pipeline.engine')}</span>
              <select
                value={config.auto_sync_engine}
                onChange={e => onSave({ auto_sync_engine: e.target.value })}
                className="bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5"
              >
                <option value="alass">alass</option>
                <option value="ffsubsync">ffsubsync</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span>{t('automation_page.processing_pipeline.fallback')}</span>
              <select
                value={config.auto_process_sync_fallback_engine}
                onChange={e => onSave({ auto_process_sync_fallback_engine: e.target.value })}
                className="bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5"
              >
                <option value="ffsubsync">ffsubsync</option>
                <option value="alass">alass</option>
                <option value="">{t('automation_page.processing_pipeline.no_fallback')}</option>
              </select>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
