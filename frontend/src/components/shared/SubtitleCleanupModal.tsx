/**
 * SubtitleCleanupModal — Batch-delete subtitle sidecars for a whole series.
 *
 * Shows all sidecar files grouped by language, lets the user filter by language
 * (checkboxes), shows a size preview, and calls batchDeleteSeriesSubtitles.
 */
import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { X, Trash2, Loader2, CheckSquare, Square } from 'lucide-react'
import { listSeriesSubtitles, batchDeleteSeriesSubtitles } from '@/api/client'
import { toast } from '@/components/shared/Toast'

interface Props {
  seriesId: number
  targetLanguages: string[]
  onClose: () => void
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function SubtitleCleanupModal({ seriesId, targetLanguages, onClose }: Props) {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['series-subtitles', seriesId],
    queryFn: () => listSeriesSubtitles(seriesId),
    staleTime: 15_000,
  })

  // Group all sidecars by language
  const byLanguage = useMemo<Record<string, { count: number; totalBytes: number; formats: Set<string> }>>(() => {
    const map: Record<string, { count: number; totalBytes: number; formats: Set<string> }> = {}
    if (!data) return map
    for (const sidecars of Object.values(data.subtitles)) {
      for (const s of sidecars) {
        if (!map[s.language]) map[s.language] = { count: 0, totalBytes: 0, formats: new Set() }
        map[s.language].count++
        map[s.language].totalBytes += s.size_bytes
        map[s.language].formats.add(s.format)
      }
    }
    return map
  }, [data])

  const allLanguages = useMemo(() => Object.keys(byLanguage).sort(), [byLanguage])

  // Languages to DELETE (user selects which to remove)
  const [toDelete, setToDelete] = useState<Set<string>>(new Set())
  const [isBusy, setIsBusy] = useState(false)

  const toggleLang = (lang: string) =>
    setToDelete((prev) => {
      const next = new Set(prev)
      if (next.has(lang)) next.delete(lang)
      else next.add(lang)
      return next
    })

  const selectNonTarget = () => {
    setToDelete(new Set(allLanguages.filter((l) => !targetLanguages.includes(l))))
  }

  const clearSelection = () => setToDelete(new Set())

  const previewCount = useMemo(
    () => [...toDelete].reduce((acc, lang) => acc + (byLanguage[lang]?.count ?? 0), 0),
    [toDelete, byLanguage]
  )

  const previewBytes = useMemo(
    () => [...toDelete].reduce((acc, lang) => acc + (byLanguage[lang]?.totalBytes ?? 0), 0),
    [toDelete, byLanguage]
  )

  const handleConfirm = async () => {
    if (toDelete.size === 0) return
    setIsBusy(true)
    try {
      const result = await batchDeleteSeriesSubtitles(seriesId, { languages: [...toDelete] })
      toast(`Bereinigt: ${result.deleted} Dateien gelöscht${result.failed ? `, ${result.failed} Fehler` : ''}`)
      await queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
      await queryClient.invalidateQueries({ queryKey: ['series-detail', seriesId] })
      onClose()
    } catch {
      toast('Bereinigung fehlgeschlagen', 'error')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-md rounded-lg flex flex-col"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', maxHeight: '80vh' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
            Sidecar bereinigen
          </span>
          <button
            onClick={onClose}
            className="p-1 rounded"
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm py-4" style={{ color: 'var(--text-secondary)' }}>
              <Loader2 size={14} className="animate-spin" />
              Lade Sidecar-Dateien…
            </div>
          ) : allLanguages.length === 0 ? (
            <p className="text-sm py-4 text-center" style={{ color: 'var(--text-muted)' }}>
              Keine Sidecar-Dateien gefunden.
            </p>
          ) : (
            <>
              {/* Quick actions */}
              <div className="flex gap-2">
                <button
                  onClick={selectNonTarget}
                  className="text-xs px-2.5 py-1 rounded border"
                  style={{ color: 'var(--accent)', borderColor: 'var(--accent-dim)', backgroundColor: 'var(--accent-bg)' }}
                >
                  Nur Target-Sprachen behalten
                </button>
                {toDelete.size > 0 && (
                  <button
                    onClick={clearSelection}
                    className="text-xs px-2.5 py-1 rounded"
                    style={{ color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
                  >
                    Auswahl leeren
                  </button>
                )}
              </div>

              {/* Language list */}
              <div className="space-y-1.5">
                {allLanguages.map((lang) => {
                  const info = byLanguage[lang]
                  const isTarget = targetLanguages.includes(lang)
                  const selected = toDelete.has(lang)
                  return (
                    <label
                      key={lang}
                      className="flex items-center gap-3 px-3 py-2 rounded cursor-pointer"
                      style={{
                        backgroundColor: selected ? 'rgba(239,68,68,0.08)' : 'var(--bg-primary)',
                        border: `1px solid ${selected ? 'rgba(239,68,68,0.3)' : 'var(--border)'}`,
                      }}
                    >
                      <span style={{ color: selected ? 'var(--error)' : 'var(--accent)' }}>
                        {selected ? <CheckSquare size={14} /> : <Square size={14} />}
                      </span>
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={selected}
                        onChange={() => toggleLang(lang)}
                      />
                      <span className="flex-1 flex items-center gap-2">
                        <span
                          className="text-xs font-bold uppercase px-1.5 py-0.5 rounded"
                          style={{
                            fontFamily: 'var(--font-mono)',
                            backgroundColor: isTarget ? 'var(--accent-bg)' : 'var(--bg-surface)',
                            color: isTarget ? 'var(--accent)' : 'var(--text-secondary)',
                          }}
                        >
                          {lang}
                        </span>
                        {isTarget && (
                          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Target</span>
                        )}
                      </span>
                      <span className="text-xs tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                        {info.count} {info.count === 1 ? 'Datei' : 'Dateien'} · {formatBytes(info.totalBytes)}
                      </span>
                    </label>
                  )
                })}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        {!isLoading && allLanguages.length > 0 && (
          <div className="px-4 py-3 flex items-center justify-between" style={{ borderTop: '1px solid var(--border)' }}>
            <span className="text-xs" style={{ color: toDelete.size > 0 ? 'var(--error)' : 'var(--text-muted)' }}>
              {toDelete.size > 0
                ? `Löscht ${previewCount} Dateien (${formatBytes(previewBytes)})`
                : 'Nichts ausgewählt'}
            </span>
            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="px-3 py-1.5 rounded text-xs"
                style={{ color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
              >
                Abbrechen
              </button>
              <button
                onClick={handleConfirm}
                disabled={toDelete.size === 0 || isBusy}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
                style={{ backgroundColor: toDelete.size > 0 ? 'var(--error)' : 'var(--text-muted)' }}
              >
                {isBusy ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                Löschen
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
