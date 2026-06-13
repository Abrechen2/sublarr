import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getInterjections, putInterjections } from '@/api/client'
import { toast } from '@/components/shared/Toast'

export function InterjectionListEditor() {
  const { t } = useTranslation('common')
  const [text, setText] = useState('')
  const [isCustom, setIsCustom] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getInterjections().then(({ items, is_custom }) => {
      setText(items.join('\n'))
      setIsCustom(is_custom)
    }).catch(() => {
      toast(t('interjection.load_failed'), 'error')
    })
  }, [])

  async function handleSave() {
    setSaving(true)
    try {
      const items = text.split('\n').map(s => s.trim()).filter(Boolean)
      await putInterjections(items)
      setIsCustom(true)
      toast(t('interjection.saved'), 'success')
    } catch {
      toast(t('interjection.save_failed'), 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleReset() {
    try {
      await putInterjections([])
      const { items } = await getInterjections()
      setText(items.join('\n'))
      setIsCustom(false)
      toast(t('interjection.reset_done'), 'success')
    } catch {
      toast(t('interjection.reset_failed'), 'error')
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-400">{isCustom ? t('interjection.label_custom') : t('interjection.label_default')}</span>
        {isCustom && (
          <button onClick={handleReset} className="text-xs text-zinc-500 hover:text-zinc-300 underline">
            {t('interjection.reset')}
          </button>
        )}
      </div>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        className="w-full h-32 text-xs font-mono bg-zinc-900 border border-zinc-700 rounded p-2 text-zinc-200"
        placeholder={t('interjection_placeholder')}
      />
      <button
        onClick={handleSave}
        disabled={saving}
        className="px-3 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 rounded disabled:opacity-50"
      >
        {saving ? t('interjection.saving') : t('interjection.save')}
      </button>
    </div>
  )
}
