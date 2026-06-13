import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { SettingRow } from '@/components/shared/SettingRow'
import { useOllamaPullModel } from '@/hooks/useTranslationApi'

// ─── Ollama Pull Section ──────────────────────────────────────────────────────

export function OllamaPullSection() {
  const { t: tc } = useTranslation('common')
  const [modelName, setModelName] = useState('')
  const [pulling, setPulling] = useState(false)
  const pullMut = useOllamaPullModel()

  const handlePull = () => {
    if (!modelName.trim()) return
    setPulling(true)
    pullMut.mutate(modelName.trim(), {
      onSuccess: (r) => {
        toast(r.message ?? tc('settings:ollama_pull.toast_pulling', { model: modelName }))
        setPulling(false)
      },
      onError: () => {
        toast(tc('settings:ollama_pull.toast_failed'), 'error')
        setPulling(false)
      },
    })
  }

  return (
    <SettingRow label={tc('ui.pull_ollama_model')} description={tc('settings:ollama_pull.description')}>
      <div className="flex gap-2 items-center">
        <input
          type="text"
          className="input-base"
          placeholder={tc('settings:ollama_pull.model_placeholder')}
          value={modelName}
          onChange={(e) => setModelName(e.target.value)}
          data-testid="ollama-model-input"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            borderRadius: '6px',
            padding: '6px 10px',
            fontSize: '13px',
            minWidth: '180px',
          }}
        />
        <button
          className="btn-primary flex items-center gap-1"
          onClick={handlePull}
          disabled={pulling || !modelName.trim()}
          data-testid="ollama-pull-btn"
          style={{
            backgroundColor: 'var(--accent)',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            padding: '6px 12px',
            fontSize: '13px',
            cursor: pulling || !modelName.trim() ? 'not-allowed' : 'pointer',
            opacity: pulling || !modelName.trim() ? 0.5 : 1,
          }}
        >
          {pulling && <Loader2 size={14} className="animate-spin" />}
          {tc('settings:ollama_pull.pull_button')}
        </button>
      </div>
    </SettingRow>
  )
}
