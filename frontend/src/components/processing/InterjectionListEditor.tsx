import { useEffect, useState } from 'react'
import { getInterjections, putInterjections } from '@/api/client'
import { toast } from '@/components/shared/Toast'

export function InterjectionListEditor() {
  const [text, setText] = useState('')
  const [isCustom, setIsCustom] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getInterjections().then(({ items, is_custom }) => {
      setText(items.join('\n'))
      setIsCustom(is_custom)
    }).catch(() => {
      toast('Interjektionsliste konnte nicht geladen werden', 'error')
    })
  }, [])

  async function handleSave() {
    setSaving(true)
    try {
      const items = text.split('\n').map(s => s.trim()).filter(Boolean)
      await putInterjections(items)
      setIsCustom(true)
      toast('Liste gespeichert', 'success')
    } catch {
      toast('Speichern fehlgeschlagen', 'error')
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
      toast('Auf Standard zurückgesetzt', 'success')
    } catch {
      toast('Zurücksetzen fehlgeschlagen', 'error')
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-400">Interjektionen {isCustom ? '(benutzerdefiniert)' : '(Standard)'}</span>
        {isCustom && (
          <button onClick={handleReset} className="text-xs text-zinc-500 hover:text-zinc-300 underline">
            Zurücksetzen
          </button>
        )}
      </div>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        className="w-full h-32 text-xs font-mono bg-zinc-900 border border-zinc-700 rounded p-2 text-zinc-200"
        placeholder="Eine Interjektion pro Zeile"
      />
      <button
        onClick={handleSave}
        disabled={saving}
        className="px-3 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 rounded disabled:opacity-50"
      >
        {saving ? 'Speichert…' : 'Liste speichern'}
      </button>
    </div>
  )
}
