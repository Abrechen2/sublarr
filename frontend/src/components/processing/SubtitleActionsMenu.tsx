import { useEffect, useState } from 'react'
import { ChevronDown, Scissors, Wrench, RotateCcw } from 'lucide-react'
import { checkBakExists, processSubtitle, undoProcessSubtitle } from '@/api/client'
import type { ProcessingChange } from '@/api/client'
import { ProcessingPreviewPanel } from './ProcessingPreviewPanel'
import { toast } from '@/components/shared/Toast'

interface Props {
  subtitlePath: string
  onRefresh?: () => void
}

type ActivePanel = 'hi_removal' | 'common_fixes' | null

export function SubtitleActionsMenu({ subtitlePath, onRefresh }: Props) {
  const [open, setOpen] = useState(false)
  const [hasBak, setHasBak] = useState(false)
  const [activePanel, setActivePanel] = useState<ActivePanel>(null)
  const [previewChanges, setPreviewChanges] = useState<ProcessingChange[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setHasBak(false)
  }, [subtitlePath])

  async function handleOpen() {
    setOpen(v => !v)
    if (!open) {
      const exists = await checkBakExists(subtitlePath)
      setHasBak(exists)
    }
  }

  async function openPreview(mod: ActivePanel) {
    if (!mod) return
    setLoading(true)
    setOpen(false)
    try {
      const result = await processSubtitle(subtitlePath, [{ mod }], true)
      setPreviewChanges(result.changes)
      setActivePanel(mod)
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : 'Vorschau fehlgeschlagen', 'error')
    } finally {
      setLoading(false)
    }
  }

  async function confirmApply() {
    if (!activePanel) return
    setLoading(true)
    try {
      await processSubtitle(subtitlePath, [{ mod: activePanel }], false)
      toast('Änderungen angewendet', 'success')
      setActivePanel(null)
      onRefresh?.()
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : 'Anwenden fehlgeschlagen', 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleUndo() {
    setOpen(false)
    try {
      await undoProcessSubtitle(subtitlePath)
      toast('Backup wiederhergestellt', 'success')
      onRefresh?.()
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : 'Wiederherstellen fehlgeschlagen', 'error')
    }
  }

  return (
    <div className="relative inline-block">
      <button
        onClick={handleOpen}
        className="flex items-center gap-1 px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-600"
      >
        Aktionen <ChevronDown size={12} />
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-1 w-48 bg-zinc-900 border border-zinc-700 rounded shadow-lg">
          <button
            onClick={() => openPreview('hi_removal')}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
          >
            <Scissors size={14} /> HI entfernen
          </button>
          <button
            onClick={() => openPreview('common_fixes')}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
          >
            <Wrench size={14} /> Common Fixes
          </button>
          {hasBak && (
            <button
              onClick={handleUndo}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left text-yellow-400"
            >
              <RotateCcw size={14} /> Backup wiederherstellen
            </button>
          )}
        </div>
      )}

      {activePanel && (
        <div className="absolute right-0 z-30 mt-1">
          <ProcessingPreviewPanel
            changes={previewChanges}
            onConfirm={confirmApply}
            onCancel={() => setActivePanel(null)}
            loading={loading}
          />
        </div>
      )}
    </div>
  )
}
