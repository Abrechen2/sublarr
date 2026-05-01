import { useEffect, useState } from 'react'
import {
  ChevronDown, Scissors, Wrench, RotateCcw, Clock,
  Eye, Pencil, Download, FileCode,
  RefreshCw, Clapperboard, ShieldCheck,
} from 'lucide-react'
import {
  checkBakExists, processSubtitle, undoProcessSubtitle,
  getSubtitleDownloadUrl, exportSubtitleNfo,
} from '@/api/client'
import type { ProcessingChange } from '@/api/client'
import { ProcessingPreviewPanel } from './ProcessingPreviewPanel'
import { toast } from '@/components/shared/Toast'

interface Props {
  subtitlePath: string
  onRefresh?: () => void
  /** Open the preview modal for this sub. Omit to hide the entry. */
  onPreview?: (path: string) => void
  /** Open the inline editor for this sub. Omit to hide the entry. */
  onEdit?: (path: string) => void
  /** Open the full timing-sync modal (offset + speed + framerate + chapter). */
  onSync?: (path: string) => void
  /** Run auto-sync against the parent video. Omit to hide. */
  onAutoSync?: (path: string) => void
  /** Run video-sync against the parent video. Omit to hide. */
  onVideoSync?: (path: string) => void
  /** Run health-check on this sub. Omit to hide. */
  onHealthCheck?: (path: string) => void
}

type ActivePanel = 'hi_removal' | 'common_fixes' | null

export function SubtitleActionsMenu({
  subtitlePath, onRefresh, onPreview, onEdit, onSync, onAutoSync, onVideoSync, onHealthCheck,
}: Props) {
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
        <div className="absolute right-0 z-20 mt-1 w-52 bg-zinc-900 border border-zinc-700 rounded shadow-lg">
          {onPreview && (
            <button
              onClick={() => { setOpen(false); onPreview(subtitlePath) }}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
            >
              <Eye size={14} /> Vorschau
            </button>
          )}
          {onEdit && (
            <button
              onClick={() => { setOpen(false); onEdit(subtitlePath) }}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
            >
              <Pencil size={14} /> Editor
            </button>
          )}
          <a
            href={getSubtitleDownloadUrl(subtitlePath)}
            download
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
          >
            <Download size={14} /> Download
          </a>
          <button
            onClick={() => {
              setOpen(false)
              exportSubtitleNfo(subtitlePath)
                .then(() => toast('NFO exportiert', 'success'))
                .catch(() => toast('NFO-Export fehlgeschlagen', 'error'))
            }}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
          >
            <FileCode size={14} /> NFO exportieren
          </button>
          <div className="border-t border-zinc-700 my-1" />
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
          {onSync && (
            <button
              onClick={() => { setOpen(false); onSync(subtitlePath) }}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
            >
              <Clock size={14} /> Timing anpassen
            </button>
          )}
          {onAutoSync && (
            <button
              onClick={() => { setOpen(false); onAutoSync(subtitlePath) }}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
            >
              <RefreshCw size={14} /> Auto-Sync
            </button>
          )}
          {onVideoSync && (
            <button
              onClick={() => { setOpen(false); onVideoSync(subtitlePath) }}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
            >
              <Clapperboard size={14} /> Video-Sync
            </button>
          )}
          {onHealthCheck && (
            <button
              onClick={() => { setOpen(false); onHealthCheck(subtitlePath) }}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-zinc-800 text-left"
            >
              <ShieldCheck size={14} /> Health-Check
            </button>
          )}
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
