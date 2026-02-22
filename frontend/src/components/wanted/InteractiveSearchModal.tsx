/**
 * InteractiveSearchModal — arr-style manual subtitle search modal.
 *
 * Shows all provider results for a wanted item or episode. Users can filter
 * by language, format, and provider, then download any result with or without
 * translation via a per-row popover.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { X, Loader2, Search, Download, RefreshCw, AlertCircle, ChevronsRight } from 'lucide-react'
import {
  useSearchInteractive,
  useSearchInteractiveEpisode,
  useDownloadSpecific,
  useDownloadSpecificEpisode,
} from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import type { InteractiveSearchResult } from '@/api/client'

interface InteractiveSearchModalProps {
  open: boolean
  itemTitle: string
  itemId?: number
  episodeId?: number
  onClose: () => void
  onDownloaded: () => void
}

interface PopoverState {
  rowKey: string
  top: number
  left: number
  result: InteractiveSearchResult
}

export function InteractiveSearchModal({
  open,
  itemTitle,
  itemId,
  episodeId,
  onClose,
  onDownloaded,
}: InteractiveSearchModalProps) {
  const [langFilter, setLangFilter] = useState('')
  const [formatFilter, setFormatFilter] = useState('')
  const [providerFilter, setProviderFilter] = useState('')
  const [popover, setPopover] = useState<PopoverState | null>(null)

  const downloadingRef = useRef<string | null>(null)
  const queryClient = useQueryClient()

  // Only one of itemId/episodeId is used — choose the right query hook
  const wantedQuery = useSearchInteractive(itemId ?? null, open && !!itemId)
  const episodeQuery = useSearchInteractiveEpisode(episodeId ?? null, open && !!episodeId)

  const query = itemId ? wantedQuery : episodeQuery
  const downloadWanted = useDownloadSpecific()
  const downloadEpisode = useDownloadSpecificEpisode()

  // Close popover on Escape, close modal on Escape if no popover
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (popover) setPopover(null)
        else onClose()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, popover, onClose])

  // Dismiss popover on outside click
  useEffect(() => {
    if (!popover) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Element
      if (!target.closest('[data-popover]') && !target.closest('[data-download-btn]')) {
        setPopover(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [popover])

  // Reset filters when modal opens with a new item
  useEffect(() => {
    if (open) {
      setLangFilter('')
      setFormatFilter('')
      setProviderFilter('')
      setPopover(null)
    }
  }, [open, itemId, episodeId])

  const handleDownloadBtn = useCallback((e: React.MouseEvent<HTMLButtonElement>, result: InteractiveSearchResult) => {
    const rowKey = `${result.provider_name}:${result.subtitle_id}`
    if (popover?.rowKey === rowKey) {
      setPopover(null)
      return
    }
    const rect = e.currentTarget.getBoundingClientRect()
    setPopover({
      rowKey,
      top: rect.bottom + window.scrollY + 4,
      left: rect.left + window.scrollX,
      result,
    })
  }, [popover])

  const handleDownload = useCallback(async (translate: boolean) => {
    if (!popover) return
    const { result } = popover
    const rowKey = `${result.provider_name}:${result.subtitle_id}`
    if (downloadingRef.current === rowKey) return
    downloadingRef.current = rowKey
    setPopover(null)

    try {
      const payload = {
        provider_name: result.provider_name,
        subtitle_id: result.subtitle_id,
        language: result.language,
        translate,
      }

      let res
      if (itemId) {
        res = await downloadWanted.mutateAsync({ itemId, payload })
      } else if (episodeId) {
        res = await downloadEpisode.mutateAsync({ episodeId, payload })
      }

      if (res?.success) {
        toast(translate ? 'Untertitel heruntergeladen & übersetzt' : 'Untertitel heruntergeladen', 'success')
        queryClient.invalidateQueries({ queryKey: ['jobs'] })
        queryClient.invalidateQueries({ queryKey: ['history'] })
        onDownloaded()
      } else {
        toast(res?.error ?? 'Download fehlgeschlagen', 'error')
      }
    } catch {
      toast('Download fehlgeschlagen', 'error')
    } finally {
      downloadingRef.current = null
    }
  }, [popover, itemId, episodeId, downloadWanted, downloadEpisode, onDownloaded, queryClient])

  if (!open) return null

  const results: InteractiveSearchResult[] = query.data?.results ?? []
  const isLoading = query.isLoading || query.isFetching

  // Derive unique filter options from results
  const languages = [...new Set(results.map(r => r.language).filter(Boolean))].sort()
  const formats = [...new Set(results.map(r => r.format).filter(Boolean))].sort()
  const providers = [...new Set(results.map(r => r.provider_name).filter(Boolean))].sort()

  const filtered = results.filter(r =>
    (!langFilter || r.language === langFilter) &&
    (!formatFilter || r.format === formatFilter) &&
    (!providerFilter || r.provider_name === providerFilter)
  )

  const isDownloading = downloadWanted.isPending || downloadEpisode.isPending

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
        onClick={() => { setPopover(null); onClose() }}
      />

      {/* Modal */}
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
        aria-modal="true"
        role="dialog"
      >
        <div
          className="pointer-events-auto w-full max-w-4xl bg-[#1a1a2e] border border-[#2a2a4a] rounded-xl shadow-2xl flex flex-col max-h-[85vh]"
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-[#2a2a4a]">
            <div className="flex items-center gap-3 min-w-0">
              <Search className="w-5 h-5 text-teal-400 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs text-slate-400 uppercase tracking-wider">Interaktive Suche</p>
                <h2 className="text-sm font-semibold text-white truncate">{itemTitle}</h2>
              </div>
            </div>
            <div className="flex items-center gap-2 ml-3">
              {!isLoading && (
                <button
                  onClick={() => query.refetch()}
                  className="p-1.5 text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                  title="Erneut suchen"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={onClose}
                className="p-1.5 text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Filter bar */}
          <div className="px-5 py-3 border-b border-[#2a2a4a] flex flex-wrap gap-2 items-center">
            <FilterSelect
              label="Sprache"
              value={langFilter}
              onChange={setLangFilter}
              options={languages}
            />
            <FilterSelect
              label="Format"
              value={formatFilter}
              onChange={setFormatFilter}
              options={formats}
            />
            <FilterSelect
              label="Anbieter"
              value={providerFilter}
              onChange={setProviderFilter}
              options={providers}
            />
            {(langFilter || formatFilter || providerFilter) && (
              <button
                onClick={() => { setLangFilter(''); setFormatFilter(''); setProviderFilter('') }}
                className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded transition-colors"
              >
                Filter zurücksetzen
              </button>
            )}
            <span className="ml-auto text-xs text-slate-500">
              {isLoading ? 'Suche läuft…' : `${filtered.length} Ergebnis${filtered.length !== 1 ? 'se' : ''}`}
            </span>
          </div>

          {/* Results */}
          <div className="flex-1 overflow-auto">
            {isLoading && (
              <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-400">
                <Loader2 className="w-8 h-8 animate-spin text-teal-400" />
                <p className="text-sm">Suche bei allen Anbietern…</p>
              </div>
            )}

            {!isLoading && query.isError && (
              <div className="flex flex-col items-center justify-center py-16 gap-3 text-red-400">
                <AlertCircle className="w-8 h-8" />
                <p className="text-sm">Suche fehlgeschlagen. Bitte erneut versuchen.</p>
              </div>
            )}

            {!isLoading && !query.isError && filtered.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-500">
                <Search className="w-8 h-8" />
                <p className="text-sm">{results.length === 0 ? 'Keine Ergebnisse gefunden.' : 'Keine Ergebnisse für aktive Filter.'}</p>
              </div>
            )}

            {!isLoading && filtered.length > 0 && (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-[#1a1a2e] border-b border-[#2a2a4a]">
                  <tr className="text-left text-xs text-slate-400 uppercase tracking-wider">
                    <th className="px-4 py-2.5 font-medium">Anbieter</th>
                    <th className="px-4 py-2.5 font-medium">Dateiname</th>
                    <th className="px-4 py-2.5 font-medium w-12">Lang</th>
                    <th className="px-4 py-2.5 font-medium w-12">Fmt</th>
                    <th className="px-4 py-2.5 font-medium w-16 text-right">Score</th>
                    <th className="px-4 py-2.5 font-medium w-12 text-right">Flags</th>
                    <th className="px-4 py-2.5 font-medium w-12"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2a2a4a]">
                  {filtered.map((result) => {
                    const key = `${result.provider_name}:${result.subtitle_id}`
                    const isPopoverOpen = popover?.rowKey === key
                    const isAss = result.format === 'ass'
                    return (
                      <tr
                        key={key}
                        className="hover:bg-white/[0.02] transition-colors"
                      >
                        <td className="px-4 py-2.5">
                          <span className="text-teal-400 font-medium capitalize text-xs">
                            {result.provider_name}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 max-w-xs">
                          <div className="text-slate-200 truncate text-xs" title={result.filename}>
                            {result.filename || <span className="text-slate-500 italic">—</span>}
                          </div>
                          {result.release_info && (
                            <div className="text-slate-500 text-xs truncate mt-0.5" title={result.release_info}>
                              {result.release_info}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className="text-slate-300 text-xs uppercase">{result.language}</span>
                        </td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                              isAss
                                ? 'bg-teal-500/20 text-teal-300'
                                : 'bg-slate-700/60 text-slate-400'
                            }`}
                          >
                            {result.format?.toUpperCase()}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <span className="text-slate-300 font-mono text-xs">{result.score}</span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <div className="flex items-center justify-end gap-1">
                            {result.uploader_trust_bonus !== undefined && result.uploader_trust_bonus > 0 && (
                              <span
                                className="text-[10px] text-emerald-400 bg-emerald-400/10 px-1 rounded"
                                title={result.uploader_name ? `Uploader: ${result.uploader_name}` : 'Vertrauenswürdiger Uploader'}
                              >
                                +{Math.round(result.uploader_trust_bonus)} Trust
                              </span>
                            )}
                            {(result.machine_translated || (result.mt_confidence !== undefined && result.mt_confidence > 0)) && (
                              <span
                                className="text-[10px] text-orange-400 bg-orange-400/10 px-1 rounded"
                                title="Likely machine-translated"
                              >
                                {result.mt_confidence !== undefined && result.mt_confidence > 0
                                  ? `MT ${Math.round(result.mt_confidence)}%`
                                  : 'MT'}
                              </span>
                            )}
                            {result.hearing_impaired && (
                              <span className="text-[10px] text-amber-400 bg-amber-400/10 px-1 rounded" title="Für Hörgeschädigte">HI</span>
                            )}
                            {result.forced && (
                              <span className="text-[10px] text-blue-400 bg-blue-400/10 px-1 rounded" title="Forced">F</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <button
                            data-download-btn
                            onClick={(e) => handleDownloadBtn(e, result)}
                            disabled={isDownloading}
                            className={`p-1.5 rounded-lg transition-colors ${
                              isPopoverOpen
                                ? 'bg-teal-500/20 text-teal-300'
                                : 'text-slate-400 hover:text-white hover:bg-white/10'
                            }`}
                            title="Herunterladen"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Footer */}
          <div className="px-5 py-3 border-t border-[#2a2a4a] flex items-center justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-slate-300 hover:text-white bg-white/5 hover:bg-white/10 rounded-lg transition-colors"
            >
              Schließen
            </button>
          </div>
        </div>
      </div>

      {/* Download popover (position:fixed to escape overflow:auto table) */}
      {popover && (
        <div
          data-popover
          style={{ top: popover.top, left: popover.left }}
          className="fixed z-[60] bg-[#1e1e36] border border-[#3a3a5a] rounded-lg shadow-xl py-1 min-w-[220px]"
        >
          <button
            onClick={() => handleDownload(false)}
            disabled={isDownloading}
            className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/10 transition-colors disabled:opacity-50"
          >
            <Download className="w-4 h-4 text-slate-400" />
            Nur herunterladen
          </button>
          <button
            onClick={() => handleDownload(true)}
            disabled={isDownloading}
            className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/10 transition-colors disabled:opacity-50"
          >
            <ChevronsRight className="w-4 h-4 text-teal-400" />
            Herunterladen & Übersetzen
          </button>
        </div>
      )}
    </>
  )
}

// ─── FilterSelect ─────────────────────────────────────────────────────────────

interface FilterSelectProps {
  label: string
  value: string
  onChange: (v: string) => void
  options: string[]
}

function FilterSelect({ label, value, onChange, options }: FilterSelectProps) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="text-xs bg-[#0f0f1e] border border-[#2a2a4a] text-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-teal-500 transition-colors"
    >
      <option value="">{label}: Alle</option>
      {options.map(opt => (
        <option key={opt} value={opt}>{opt.toUpperCase()}</option>
      ))}
    </select>
  )
}
