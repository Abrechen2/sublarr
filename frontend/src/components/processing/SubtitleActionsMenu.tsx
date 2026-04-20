import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Scissors, Wrench, RotateCcw, Clock } from 'lucide-react'
import { checkBakExists, processSubtitle, undoProcessSubtitle } from '@/api/client'
import { advancedSync } from '@/api/system/tasks'
import type { ProcessingChange } from '@/api/client'
import { ProcessingPreviewPanel } from './ProcessingPreviewPanel'
import { toast } from '@/components/shared/Toast'

interface Props {
  subtitlePath: string
  onRefresh?: () => void
}

type ActivePanel = 'hi_removal' | 'common_fixes' | 'timing' | null

export function SubtitleActionsMenu({ subtitlePath, onRefresh }: Props) {
  const [open, setOpen] = useState(false)
  const [hasBak, setHasBak] = useState(false)
  const [activePanel, setActivePanel] = useState<ActivePanel>(null)
  const [previewChanges, setPreviewChanges] = useState<ProcessingChange[]>([])
  const [loading, setLoading] = useState(false)
  const [timingOffset, setTimingOffset] = useState(0)

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

  async function openPreview(mod: 'hi_removal' | 'common_fixes') {
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
    if (!activePanel || activePanel === 'timing') return
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

  async function applyTiming() {
    if (timingOffset === 0) return
    setLoading(true)
    try {
      await advancedSync(subtitlePath, 'offset', { offset_ms: timingOffset })
      toast(`Timing um ${timingOffset > 0 ? '+' : ''}${timingOffset} ms verschoben`, 'success')
      setActivePanel(null)
      setTimingOffset(0)
      onRefresh?.()
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : 'Timing-Anpassung fehlgeschlagen', 'error')
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
        <div className="absolute right-0 z-20 mt-1 w-52 bg-zinc-900 border border-zinc-700 rounded shadow-lg">
          <button
            onClick={() => { setOpen(false); openPreview('hi_removal') }}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
          >
            <Scissors size={14} /> HI entfernen
          </button>
          <button
            onClick={() => { setOpen(false); openPreview('common_fixes') }}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
          >
            <Wrench size={14} /> Common Fixes
          </button>
          <button
            onClick={() => { setOpen(false); setActivePanel('timing') }}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
          >
            <Clock size={14} /> Timing verschieben
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

      {activePanel === 'timing' && (
        <div className="absolute right-0 z-30 mt-1 border border-zinc-700 rounded-lg bg-zinc-900 p-4 space-y-3 w-64">
          <div className="text-sm font-medium text-zinc-300">{tc('ui.timing_shift')}</div>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={timingOffset}
              onChange={(e) => setTimingOffset(parseInt(e.target.value) || 0)}
              className="w-28 px-2 py-1.5 rounded text-sm text-center bg-zinc-800 border border-zinc-600 text-zinc-100"
              placeholder="0"
            />
            <span className="text-xs text-zinc-400">
              ms {timingOffset > 0 ? '(verzögern)' : timingOffset < 0 ? '(vorverlegen)' : ''}
            </span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={applyTiming}
              disabled={loading || timingOffset === 0}
              className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded disabled:opacity-50"
            >
              {loading ? 'Wird angewendet…' : 'Übernehmen'}
            </button>
            <button
              onClick={() => { setActivePanel(null); setTimingOffset(0) }}
              className="px-3 py-1.5 text-sm bg-zinc-700 hover:bg-zinc-600 text-white rounded"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {(activePanel === 'hi_removal' || activePanel === 'common_fixes') && (
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
