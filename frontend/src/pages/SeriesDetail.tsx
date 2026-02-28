import { useState, useMemo, useCallback, lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSeriesDetail, useEpisodeSearch, useEpisodeHistory, useProcessWantedItem, useGlossaryEntries, useCreateGlossaryEntry, useUpdateGlossaryEntry, useDeleteGlossaryEntry, useStartWantedBatch, useUpdateSeriesSettings, useAnidbMappingStatus, useRefreshAnidbMapping } from '@/hooks/useApi'
import {
  ArrowLeft, Loader2, ChevronDown, ChevronRight,
  Folder, FileVideo, AlertTriangle, Play, Tag, Globe, Search, Clock,
  Download, X, ChevronUp, BookOpen, Plus, Edit2, Trash2, Check,
  Eye, Pencil, Columns2, Timer, ShieldCheck, ScanSearch, RefreshCw, Database,
  Layers, Sparkles, Trash,
} from 'lucide-react'
import { formatRelativeTime } from '@/lib/utils'
import { toast } from '@/components/shared/Toast'
import SubtitleEditorModal from '@/components/editor/SubtitleEditorModal'
import { TrackPanel } from '@/components/tracks/TrackPanel'
import { autoSyncFile, startWantedBatchSearch, batchExtractAllTracks, listSeriesSubtitles, deleteSubtitles } from '@/api/client'
import { useWebSocket } from '@/hooks/useWebSocket'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { InteractiveSearchModal } from '@/components/wanted/InteractiveSearchModal'
import { ComparisonSelector } from '@/components/comparison/ComparisonSelector'
import { HealthBadge } from '@/components/health/HealthBadge'
import { SubtitleCleanupModal } from '@/components/shared/SubtitleCleanupModal'
import type { EpisodeInfo, WantedSearchResponse, EpisodeHistoryEntry, SidecarSubtitle } from '@/lib/types'

const SubtitleComparison = lazy(() => import('@/components/comparison/SubtitleComparison').then(m => ({ default: m.SubtitleComparison })))
const SyncControls = lazy(() => import('@/components/sync/SyncControls').then(m => ({ default: m.SyncControls })))
const SyncModal = lazy(() => import('@/components/sync/SyncModal').then(m => ({ default: m.SyncModal })))
const HealthCheckPanel = lazy(() => import('@/components/health/HealthCheckPanel').then(m => ({ default: m.HealthCheckPanel })))

// ─── Language normalisation ─────────────────────────────────────────────────
// MKV/ffprobe stores ISO 639-2 three-letter codes (ger, eng, jpn…). Target
// languages in Sublarr use ISO 639-1 two-letter codes (de, en, ja…).
// normLang() maps 3→2 so that badge de-duplication works across both systems.

const ISO6392_TO_1: Record<string, string> = {
  ger: 'de', deu: 'de',
  eng: 'en',
  dut: 'nl', nld: 'nl',
  swe: 'sv',
  dan: 'da',
  nor: 'no', nob: 'no', nno: 'no',
  fre: 'fr', fra: 'fr',
  spa: 'es',
  ita: 'it',
  por: 'pt',
  ron: 'ro', rum: 'ro',
  pol: 'pl',
  rus: 'ru',
  ces: 'cs', cze: 'cs',
  slk: 'sk', slo: 'sk',
  hrv: 'hr',
  srp: 'sr',
  bul: 'bg',
  ukr: 'uk',
  jpn: 'ja',
  chi: 'zh', zho: 'zh',
  kor: 'ko',
  tha: 'th',
  vie: 'vi',
  ind: 'id',
  ara: 'ar',
  tur: 'tr',
  hun: 'hu',
  fin: 'fi',
  heb: 'he',
}

function normLang(code: string): string {
  const lower = code.toLowerCase()
  return ISO6392_TO_1[lower] ?? lower
}

/** Derive subtitle file path from media path + language + format. */
function deriveSubtitlePath(mediaPath: string, lang: string, format: string): string {
  const lastDot = mediaPath.lastIndexOf('.')
  const base = lastDot > 0 ? mediaPath.substring(0, lastDot) : mediaPath
  return `${base}.${lang}.${format}`
}

function SubBadge({ lang, format }: { lang: string; format: string }) {
  // Three visual states:
  //  teal   = optimal   (ass / embedded_ass)
  //  amber  = upgradeable (srt / embedded_srt — present but not best format)
  //  orange = missing   (no subtitle file at all)
  const isOptimal = format === 'ass' || format === 'embedded_ass'
  const isUpgradeable = format === 'srt' || format === 'embedded_srt'
  const isEmbedded = format === 'embedded_ass' || format === 'embedded_srt'
  const hasFile = isOptimal || isUpgradeable

  const bg = isOptimal ? 'var(--accent-bg)' : isUpgradeable ? 'var(--upgrade-bg)' : 'var(--warning-bg)'
  const color = isOptimal ? 'var(--accent)' : isUpgradeable ? 'var(--upgrade)' : 'var(--warning)'
  const border = isOptimal
    ? '1px solid var(--accent-dim)'
    : isUpgradeable
      ? '1px solid rgba(167,139,250,0.4)'
      : '1px solid rgba(245,158,11,0.3)'

  const label = isEmbedded ? format.replace('embedded_', '') + '⊕' : format
  const title = hasFile
    ? `${lang.toUpperCase()} (${format.toUpperCase()}${isEmbedded ? ' — eingebettet' : ''}${isUpgradeable ? ' — upgradeable zu ASS' : ''})`
    : `${lang.toUpperCase()} fehlt`

  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide"
      style={{ backgroundColor: bg, color, border }}
      title={title}
    >
      {lang.toUpperCase()}
      {hasFile && (
        <span style={{ opacity: 0.6, fontSize: '9px' }}>{label}</span>
      )}
    </span>
  )
}

function ScoreBadge({ score }: { score: number }) {
  const color = score >= 300 ? 'var(--success)' : score >= 200 ? 'var(--warning)' : 'var(--text-muted)'
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold tabular-nums"
      style={{ backgroundColor: `${color}18`, color, fontFamily: 'var(--font-mono)' }}
    >
      {score}
    </span>
  )
}

// ─── Search Results Panel ──────────────────────────────────────────────────

function EpisodeSearchPanel({ results, isLoading, onProcess }: {
  results: WantedSearchResponse | null
  isLoading: boolean
  onProcess: (wantedId: number) => void
}) {
  const { t } = useTranslation('library')
  if (isLoading) {
    return (
      <div
        className="px-6 py-4 flex items-center gap-2 text-sm"
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}
      >
        <Loader2 size={14} className="animate-spin" />
        {t('series_detail.searching_providers')}
      </div>
    )
  }

  if (!results) return null

  const allResults = [
    ...results.target_results.map((r) => ({ ...r, _type: 'target' as const })),
    ...results.source_results.map((r) => ({ ...r, _type: 'source' as const })),
  ]

  if (allResults.length === 0) {
    return (
      <div
        className="px-6 py-4 text-sm"
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}
      >
        {t('series_detail.no_search_results')}
      </div>
    )
  }

  return (
    <div style={{ backgroundColor: 'var(--bg-primary)' }} className="px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          {t('series_detail.search_results', { count: allResults.length })}
        </span>
        <button
          onClick={() => onProcess(results.wanted_id)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-white hover:opacity-90"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <Download size={11} />
          {t('series_detail.download_best')}
        </button>
      </div>
      <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Provider</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Type</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Format</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Score</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Release</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Lang</th>
            </tr>
          </thead>
          <tbody>
            {allResults.map((r, i) => (
              <tr
                key={`${r.provider}-${r.subtitle_id}-${i}`}
                style={{ borderBottom: i < allResults.length - 1 ? '1px solid var(--border)' : undefined }}
              >
                <td className="px-3 py-1.5 text-xs" style={{ fontFamily: 'var(--font-mono)' }}>
                  {r.provider}
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase font-medium"
                    style={{
                      backgroundColor: r._type === 'target' ? 'rgba(16,185,129,0.1)' : 'rgba(29,184,212,0.1)',
                      color: r._type === 'target' ? 'var(--success)' : 'var(--accent)',
                    }}
                  >
                    {r._type === 'target' ? 'Target' : 'Source'}
                  </span>
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
                    style={{
                      backgroundColor: r.format === 'ass' ? 'rgba(16,185,129,0.1)' : 'var(--bg-surface)',
                      color: r.format === 'ass' ? 'var(--success)' : 'var(--text-secondary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {r.format}
                  </span>
                </td>
                <td className="px-3 py-1.5">
                  <ScoreBadge score={r.score} />
                </td>
                <td className="px-3 py-1.5 text-xs truncate max-w-[200px]" title={r.release_info || r.filename} style={{ color: 'var(--text-secondary)' }}>
                  {r.release_info || r.filename || '-'}
                </td>
                <td className="px-3 py-1.5 text-xs uppercase" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {r.language}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Glossary Panel ────────────────────────────────────────────────────────

function GlossaryPanel({ seriesId }: { seriesId: number }) {
  const { t } = useTranslation('library')
  const { data, isLoading } = useGlossaryEntries(seriesId)
  const createEntry = useCreateGlossaryEntry()
  const updateEntry = useUpdateGlossaryEntry()
  const deleteEntry = useDeleteGlossaryEntry()
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [formData, setFormData] = useState({ source_term: '', target_term: '', notes: '' })

  const entries = data?.entries || []
  const filteredEntries = searchQuery
    ? entries.filter((e) =>
        e.source_term.toLowerCase().includes(searchQuery.toLowerCase()) ||
        e.target_term.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : entries

  const resetForm = () => {
    setShowAdd(false)
    setEditingId(null)
    setFormData({ source_term: '', target_term: '', notes: '' })
  }

  const startEdit = (entry: { id: number; source_term: string; target_term: string; notes: string }) => {
    setEditingId(entry.id)
    setFormData({
      source_term: entry.source_term,
      target_term: entry.target_term,
      notes: entry.notes || '',
    })
    setShowAdd(false)
  }

  const handleSave = () => {
    if (!formData.source_term.trim() || !formData.target_term.trim()) {
      toast('Source and target terms are required', 'error')
      return
    }

    if (editingId) {
      updateEntry.mutate(
        { entryId: editingId, series_id: seriesId, ...formData },
        {
          onSuccess: () => {
            toast('Glossary entry updated')
            resetForm()
          },
          onError: () => toast('Failed to update entry', 'error'),
        }
      )
    } else {
      createEntry.mutate(
        { series_id: seriesId, ...formData },
        {
          onSuccess: () => {
            toast('Glossary entry created')
            resetForm()
          },
          onError: () => toast('Failed to create entry', 'error'),
        }
      )
    }
  }

  const handleDelete = (id: number) => {
    if (!confirm('Delete this glossary entry?')) return
    deleteEntry.mutate(
      { entryId: id, seriesId },
      {
        onSuccess: () => toast('Entry deleted'),
        onError: () => toast('Failed to delete entry', 'error'),
      }
    )
  }

  if (isLoading) {
    return (
      <div
        className="px-6 py-4 flex items-center gap-2 text-sm"
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}
      >
        <Loader2 size={14} className="animate-spin" />
        {t('series_detail.loading_glossary')}
      </div>
    )
  }

  return (
    <div style={{ backgroundColor: 'var(--bg-primary)' }} className="px-4 py-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          {t('series_detail.glossary')} ({entries.length})
        </span>
        <button
          onClick={() => {
            resetForm()
            setShowAdd(true)
          }}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-white hover:opacity-90"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <Plus size={11} />
          {t('series_detail.add_entry')}
        </button>
      </div>

      {entries.length > 0 && (
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Series-specific entries override global entries with the same source term.
        </p>
      )}

      {/* Search */}
      <input
        type="text"
        placeholder={t('series_detail.search_glossary')}
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="w-full px-3 py-1.5 rounded text-xs"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
        }}
      />

      {/* Add/Edit Form */}
      {(showAdd || editingId !== null) && (
        <div
          className="rounded-lg p-3 space-y-2"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? t('series_detail.edit_entry') : t('series_detail.new_entry')}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="text"
              placeholder={t('series_detail.source_term')}
              value={formData.source_term}
              onChange={(e) => setFormData((f) => ({ ...f, source_term: e.target.value }))}
              className="px-2 py-1.5 rounded text-xs"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
            <input
              type="text"
              placeholder={t('series_detail.target_term')}
              value={formData.target_term}
              onChange={(e) => setFormData((f) => ({ ...f, target_term: e.target.value }))}
              className="px-2 py-1.5 rounded text-xs"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
          <input
            type="text"
            placeholder={t('series_detail.notes_optional')}
            value={formData.notes}
            onChange={(e) => setFormData((f) => ({ ...f, notes: e.target.value }))}
            className="w-full px-2 py-1.5 rounded text-xs"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={createEntry.isPending || updateEntry.isPending}
              className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {(createEntry.isPending || updateEntry.isPending) ? (
                <Loader2 size={10} className="animate-spin" />
              ) : (
                <Check size={10} />
              )}
              {t('series_detail.save')}
            </button>
            <button onClick={resetForm} className="flex items-center gap-1 px-2.5 py-1 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
              <X size={10} /> {t('series_detail.cancel')}
            </button>
          </div>
        </div>
      )}

      {/* Entries List */}
      {filteredEntries.length === 0 ? (
        <div className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>
          {searchQuery ? t('series_detail.no_glossary_match') : t('series_detail.no_glossary_entries')}
        </div>
      ) : (
        <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
          <table className="w-full">
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Source</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Target</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Notes</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredEntries.map((entry, i) => (
                <tr
                  key={entry.id}
                  style={{ borderBottom: i < filteredEntries.length - 1 ? '1px solid var(--border)' : undefined }}
                >
                  <td className="px-3 py-1.5 text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                    {entry.source_term}
                  </td>
                  <td className="px-3 py-1.5 text-xs font-medium" style={{ color: 'var(--accent)' }}>
                    {entry.target_term}
                  </td>
                  <td className="px-3 py-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {entry.notes || '-'}
                  </td>
                  <td className="px-3 py-1.5">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => startEdit(entry)}
                        className="p-1 rounded transition-colors"
                        style={{ color: 'var(--text-secondary)', backgroundColor: 'var(--bg-surface)' }}
                        title="Edit"
                      >
                        <Edit2 size={10} />
                      </button>
                      <button
                        onClick={() => handleDelete(entry.id)}
                        disabled={deleteEntry.isPending}
                        className="p-1 rounded transition-colors"
                        style={{ color: 'var(--error)', backgroundColor: 'var(--bg-surface)' }}
                        title="Delete"
                      >
                        <Trash2 size={10} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ─── History Panel ─────────────────────────────────────────────────────────

function EpisodeHistoryPanel({ entries, isLoading }: {
  entries: EpisodeHistoryEntry[]
  isLoading: boolean
}) {
  const { t } = useTranslation('library')
  if (isLoading) {
    return (
      <div
        className="px-6 py-4 flex items-center gap-2 text-sm"
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}
      >
        <Loader2 size={14} className="animate-spin" />
        {t('series_detail.loading_history')}
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div
        className="px-6 py-4 text-sm"
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}
      >
        {t('series_detail.no_history')}
      </div>
    )
  }

  return (
    <div style={{ backgroundColor: 'var(--bg-primary)' }} className="px-4 py-3">
      <span className="text-xs font-semibold uppercase tracking-wider mb-2 block" style={{ color: 'var(--text-muted)' }}>
        {t('series_detail.history_count', { count: entries.length })}
      </span>
      <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Date</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Action</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Provider</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Format</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Score</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, i) => (
              <tr
                key={i}
                style={{ borderBottom: i < entries.length - 1 ? '1px solid var(--border)' : undefined }}
              >
                <td className="px-3 py-1.5 text-xs tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {entry.date ? formatRelativeTime(entry.date) : '-'}
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase font-medium"
                    style={{
                      backgroundColor: entry.action === 'download' ? 'rgba(29,184,212,0.1)' : 'rgba(16,185,129,0.1)',
                      color: entry.action === 'download' ? 'var(--accent)' : 'var(--success)',
                    }}
                  >
                    {entry.action}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-xs" style={{ fontFamily: 'var(--font-mono)' }}>
                  {entry.provider_name || '-'}
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
                    style={{
                      backgroundColor: entry.format === 'ass' ? 'rgba(16,185,129,0.1)' : 'var(--bg-surface)',
                      color: entry.format === 'ass' ? 'var(--success)' : 'var(--text-secondary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {entry.format || '-'}
                  </span>
                </td>
                <td className="px-3 py-1.5">
                  {entry.score > 0 ? <ScoreBadge score={entry.score} /> : <span className="text-xs" style={{ color: 'var(--text-muted)' }}>-</span>}
                </td>
                <td className="px-3 py-1.5 text-xs" style={{ color: entry.status === 'completed' || entry.status === 'downloaded' ? 'var(--success)' : entry.error ? 'var(--error)' : 'var(--text-secondary)' }}>
                  {entry.error || entry.status || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Season Group ──────────────────────────────────────────────────────────

function SeasonGroup({ season, episodes, targetLanguages, seriesId, isExtracting, expandedEp, onSearch, onInteractiveSearch, onHistory, onTracks, onClose, searchResults, searchLoading, historyEntries, historyLoading, onProcess, onPreviewSub, onEditSub, onCompare, onSync, onAutoSync, onVideoSync, onHealthCheck, healthScores, onOpenEditor, sidecarMap, onDeleteSidecar, onOpenCleanupModal, t }: {
  season: number
  episodes: EpisodeInfo[]
  targetLanguages: string[]
  seriesId: number | null
  isExtracting?: boolean
  expandedEp: { id: number; mode: 'search' | 'history' | 'glossary' | 'tracks' } | null
  onSearch: (ep: EpisodeInfo) => void
  onInteractiveSearch: (ep: EpisodeInfo) => void
  onHistory: (ep: EpisodeInfo) => void
  onTracks: (ep: EpisodeInfo) => void
  onClose: () => void
  searchResults: WantedSearchResponse | null
  searchLoading: boolean
  historyEntries: EpisodeHistoryEntry[]
  historyLoading: boolean
  onProcess: (wantedId: number) => void
  onPreviewSub: (filePath: string) => void
  onEditSub: (filePath: string) => void
  onCompare: (ep: EpisodeInfo) => void
  onSync: (filePath: string) => void
  onAutoSync: (filePath: string) => void
  onVideoSync: (ep: EpisodeInfo, subtitlePath: string) => void
  onHealthCheck: (filePath: string) => void
  healthScores: Record<string, number | null>
  onOpenEditor: (filePath: string) => void
  sidecarMap: Record<string, SidecarSubtitle[]>
  onDeleteSidecar: (path: string) => Promise<void>
  onOpenCleanupModal: () => void
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  const [expanded, setExpanded] = useState(true)
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(new Set())

  const allSelectableIds = useMemo(
    () => episodes.map(e => e.id).filter((id): id is number => id != null),
    [episodes]
  )

  const toggleEpisode = useCallback((id: number) => {
    setSelectedEpisodes(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }, [])

  const selectAll = useCallback(() => setSelectedEpisodes(new Set(allSelectableIds)), [allSelectableIds])
  const clearAll = useCallback(() => setSelectedEpisodes(new Set()), [])

  return (
    <div>
      {/* Season Header */}
      <div
        className="flex items-center"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          borderBottom: expanded ? '1px solid var(--border)' : 'none',
        }}
      >
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-1 flex items-center gap-2 px-4 py-2.5 text-left transition-colors"
        >
          {expanded ? (
            <ChevronDown size={14} style={{ color: 'var(--accent)' }} />
          ) : (
            <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
          )}
          <span className="text-sm font-semibold">
            {t('series_detail.season', { number: season })}
          </span>
          <span className="text-xs ml-1" style={{ color: 'var(--text-muted)' }}>
            ({t('series_detail.episodes_count', { count: episodes.length })})
          </span>
        </button>
        {expanded && (
          <div className="pr-4 flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={allSelectableIds.length > 0 && selectedEpisodes.size === allSelectableIds.length}
              onChange={() => selectedEpisodes.size === allSelectableIds.length ? clearAll() : selectAll()}
              className="rounded"
              style={{ accentColor: 'var(--accent)' }}
              title="Select all episodes in this season"
            />
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>All</span>
          </div>
        )}
      </div>

      {/* Episodes */}
      {expanded && (
        <div>
          {episodes
            .sort((a, b) => b.episode - a.episode)
            .map((ep) => {
              const isExpanded = expandedEp?.id === ep.id
              const mode = expandedEp?.mode

              return (
                <div key={ep.id}>
                  <div
                    className="flex items-start px-4 py-2 transition-colors"
                    style={{
                      borderBottom: isExpanded ? 'none' : '1px solid var(--border)',
                      backgroundColor: isExpanded ? 'var(--bg-surface-hover)' : '',
                    }}
                    onMouseEnter={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                    }}
                    onMouseLeave={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = ''
                    }}
                  >
                    {/* Selection checkbox */}
                    <div className="w-6 flex-shrink-0 flex items-center">
                      <input
                        type="checkbox"
                        checked={selectedEpisodes.has(ep.id)}
                        onChange={() => toggleEpisode(ep.id)}
                        className="rounded"
                        style={{ accentColor: 'var(--accent)' }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>

                    {/* Monitored indicator */}
                    <div className="w-5 flex-shrink-0">
                      {ep.has_file ? (
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: 'var(--success)' }}
                          title={t('series_detail.has_file')}
                        />
                      ) : (
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: 'var(--text-muted)' }}
                          title={t('series_detail.no_file')}
                        />
                      )}
                    </div>

                    {/* Episode number */}
                    <div
                      className="w-12 flex-shrink-0 text-sm font-medium"
                      style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                    >
                      {ep.episode}
                    </div>

                    {/* Title */}
                    <div className="flex-1 min-w-0 text-sm truncate" title={ep.title}>
                      {ep.title || t('series_detail.tba')}
                    </div>

                    {/* Audio */}
                    <div className="w-24 flex-shrink-0 flex gap-1">
                      {ep.audio_languages.length > 0 ? (
                        ep.audio_languages.map((lang, i) => (
                          <span
                            key={i}
                            className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase"
                            style={{
                              backgroundColor: 'rgba(99, 102, 241, 0.12)',
                              color: '#818cf8',
                            }}
                          >
                            {lang}
                          </span>
                        ))
                      ) : (
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>&mdash;</span>
                      )}
                    </div>

                    {/* Subtitles */}
                    <div className="flex-1 min-w-[200px] flex gap-1 flex-wrap items-center">
                      {ep.has_file ? (
                        <>
                          {/* Target language badges: teal=ass, amber=srt, orange=missing */}
                          {targetLanguages.length > 0 ? targetLanguages.map((lang) => {
                            const subFormat = ep.subtitles[lang] || ''
                            const epSidecars = sidecarMap[String(ep.id)] ?? []
                            // Find matching sidecar on disk (handles ISO 639-2 ↔ 639-1 mismatch)
                            const matchingSidecar = (subFormat === 'ass' || subFormat === 'srt')
                              ? epSidecars.find(s => normLang(s.language) === normLang(lang) && s.format === subFormat)
                              : null
                            return (
                              <span key={lang} className="inline-flex items-center gap-0.5">
                                <SubBadge lang={lang} format={subFormat} />
                                {matchingSidecar && (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(matchingSidecar.path) }}
                                    className="p-0.5 rounded hover:opacity-80"
                                    style={{ color: 'var(--error)', lineHeight: 1 }}
                                    title={`Löschen: ${matchingSidecar.path}`}
                                  >
                                    <X size={9} />
                                  </button>
                                )}
                                {(subFormat === 'ass' || subFormat === 'srt') && (
                                  <>
                                    <HealthBadge score={healthScores[deriveSubtitlePath(ep.file_path, lang, subFormat)] ?? null} size="sm" />
                                    <button
                                      onClick={() => onPreviewSub(deriveSubtitlePath(ep.file_path, lang, subFormat))}
                                      className="p-0.5 rounded transition-colors"
                                      style={{ color: 'var(--text-muted)' }}
                                      title="Preview subtitle"
                                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                                    >
                                      <Eye size={12} />
                                    </button>
                                    <button
                                      onClick={() => onEditSub(deriveSubtitlePath(ep.file_path, lang, subFormat))}
                                      className="p-0.5 rounded transition-colors"
                                      style={{ color: 'var(--text-muted)' }}
                                      title="Edit subtitle"
                                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                                    >
                                      <Pencil size={12} />
                                    </button>
                                  </>
                                )}
                              </span>
                            )
                          }) : (
                            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>&#x2014;</span>
                          )}

                          {/* Extra sidecar badges: non-target languages, deduped via normLang */}
                          {(() => {
                            const epSidecars = sidecarMap[String(ep.id)] ?? []
                            const extraSidecars = epSidecars.filter(
                              s => !targetLanguages.some(tl => normLang(tl) === normLang(s.language))
                            )
                            if (extraSidecars.length === 0) return null
                            return extraSidecars.map((s) => (
                              <span
                                key={s.path}
                                className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
                                style={{
                                  backgroundColor: 'var(--bg-surface)',
                                  color: 'var(--text-muted)',
                                  border: '1px solid var(--border)',
                                }}
                                title={`${s.language.toUpperCase()} ${s.format.toUpperCase()} — extra sidecar`}
                              >
                                {s.language.toUpperCase()}
                                <span style={{ opacity: 0.6, fontSize: '9px' }}>{s.format}</span>
                                <button
                                  onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(s.path) }}
                                  className="ml-0.5 rounded hover:opacity-80"
                                  style={{ color: 'var(--error)', lineHeight: 1 }}
                                  title={`Löschen: ${s.path}`}
                                >
                                  <X size={9} />
                                </button>
                              </span>
                            ))
                          })()}
                        </>
                      ) : (
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>No file</span>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="w-40 flex-shrink-0 flex gap-1 justify-end">
                      {isExpanded && (
                        <button
                          onClick={onClose}
                          className="p-1.5 rounded transition-colors"
                          style={{ color: 'var(--text-muted)' }}
                          title={t('series_detail.close')}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = 'var(--error)'
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = 'var(--text-muted)'
                          }}
                        >
                          <X size={14} />
                        </button>
                      )}
                      {/* Compare button: only show when 2+ subtitle files */}
                      {(() => {
                        const subCount = ep.has_file ? Object.values(ep.subtitles).filter(f => f === 'ass' || f === 'srt').length : 0
                        return subCount >= 2 ? (
                          <button
                            onClick={() => onCompare(ep)}
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--text-muted)' }}
                            title="Compare subtitles"
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = 'var(--accent)'
                              e.currentTarget.style.backgroundColor = 'var(--accent-subtle)'
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'var(--text-muted)'
                              e.currentTarget.style.backgroundColor = ''
                            }}
                          >
                            <Columns2 size={14} />
                          </button>
                        ) : null
                      })()}
                      {/* Sync button: only show when at least 1 subtitle file */}
                      {(() => {
                        const hasAnySub = ep.has_file && Object.values(ep.subtitles).some(f => f === 'ass' || f === 'srt')
                        if (!hasAnySub) return null
                        // Pick the first available subtitle for sync
                        const firstLang = Object.entries(ep.subtitles).find(([, f]) => f === 'ass' || f === 'srt')
                        if (!firstLang) return null
                        const syncPath = deriveSubtitlePath(ep.file_path, firstLang[0], firstLang[1])
                        return (
                          <button
                            onClick={() => onSync(syncPath)}
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--text-muted)' }}
                            title="Sync timing"
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = 'var(--accent)'
                              e.currentTarget.style.backgroundColor = 'var(--accent-subtle)'
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'var(--text-muted)'
                              e.currentTarget.style.backgroundColor = ''
                            }}
                          >
                            <Timer size={14} />
                          </button>
                        )
                      })()}
                      {/* Auto-sync button: call alass/ffsubsync directly */}
                      {(() => {
                        const hasAnySub = ep.has_file && Object.values(ep.subtitles).some(f => f === 'ass' || f === 'srt')
                        if (!hasAnySub) return null
                        const firstLang = Object.entries(ep.subtitles).find(([, f]) => f === 'ass' || f === 'srt')
                        if (!firstLang) return null
                        const syncPath = deriveSubtitlePath(ep.file_path, firstLang[0], firstLang[1])
                        return (
                          <button
                            onClick={() => onAutoSync(syncPath)}
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--text-muted)' }}
                            title="Auto-sync timing (alass/ffsubsync)"
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = 'var(--success)'
                              e.currentTarget.style.backgroundColor = 'var(--success-bg)'
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'var(--text-muted)'
                              e.currentTarget.style.backgroundColor = ''
                            }}
                          >
                            <RefreshCw size={14} />
                          </button>
                        )
                      })()}
                      {/* Video sync button: open SyncModal (ffsubsync/alass with engine/track selector) */}
                      {(() => {
                        if (!ep.has_file) return null
                        const firstLang = Object.entries(ep.subtitles).find(([, f]) => f === 'ass' || f === 'srt')
                        if (!firstLang) return null
                        const syncPath = deriveSubtitlePath(ep.file_path, firstLang[0], firstLang[1])
                        return (
                          <button
                            onClick={() => onVideoSync(ep, syncPath)}
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--text-muted)' }}
                            title="Video-Sync (ffsubsync / alass)"
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = 'var(--accent)'
                              e.currentTarget.style.backgroundColor = 'var(--accent-subtle)'
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'var(--text-muted)'
                              e.currentTarget.style.backgroundColor = ''
                            }}
                          >
                            <ScanSearch size={14} />
                          </button>
                        )
                      })()}
                      {/* Health button: only show when at least 1 subtitle file */}
                      {(() => {
                        const hasAnySub = ep.has_file && Object.values(ep.subtitles).some(f => f === 'ass' || f === 'srt')
                        if (!hasAnySub) return null
                        const firstLang = Object.entries(ep.subtitles).find(([, f]) => f === 'ass' || f === 'srt')
                        if (!firstLang) return null
                        const healthPath = deriveSubtitlePath(ep.file_path, firstLang[0], firstLang[1])
                        return (
                          <button
                            onClick={() => onHealthCheck(healthPath)}
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--text-muted)' }}
                            title="Health check"
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = 'var(--accent)'
                              e.currentTarget.style.backgroundColor = 'var(--accent-subtle)'
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'var(--text-muted)'
                              e.currentTarget.style.backgroundColor = ''
                            }}
                          >
                            <ShieldCheck size={14} />
                          </button>
                        )
                      })()}
                      {/* Tracks button: show all embedded tracks */}
                      {ep.has_file && (
                        <button
                          onClick={() => onTracks(ep)}
                          className="p-1.5 rounded transition-colors"
                          style={{ color: isExpanded && mode === 'tracks' ? 'var(--accent)' : 'var(--text-muted)' }}
                          title="Eingebettete Tracks anzeigen"
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = 'var(--accent)'
                            e.currentTarget.style.backgroundColor = 'var(--accent-subtle)'
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = isExpanded && mode === 'tracks' ? 'var(--accent)' : 'var(--text-muted)'
                            e.currentTarget.style.backgroundColor = ''
                          }}
                        >
                          <Database size={14} />
                        </button>
                      )}
                      <button
                        onClick={() => onSearch(ep)}
                        disabled={!ep.has_file}
                        className="p-1.5 rounded transition-colors"
                        style={{
                          color: isExpanded && mode === 'search' ? 'var(--accent)' : 'var(--text-muted)',
                          opacity: ep.has_file ? 1 : 0.4,
                        }}
                        title={t('series_detail.search_subtitles')}
                        onMouseEnter={(e) => {
                          if (ep.has_file) {
                            e.currentTarget.style.color = 'var(--accent)'
                            e.currentTarget.style.backgroundColor = 'var(--accent-subtle)'
                          }
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = isExpanded && mode === 'search' ? 'var(--accent)' : 'var(--text-muted)'
                          e.currentTarget.style.backgroundColor = ''
                        }}
                      >
                        {searchLoading && isExpanded && mode === 'search' ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : isExpanded && mode === 'search' ? (
                          <ChevronUp size={14} />
                        ) : (
                          <Search size={14} />
                        )}
                      </button>
                      <button
                        onClick={() => onInteractiveSearch(ep)}
                        disabled={!ep.has_file}
                        className="p-1.5 rounded transition-colors"
                        style={{
                          color: 'var(--text-muted)',
                          opacity: ep.has_file ? 1 : 0.4,
                        }}
                        title="Interaktive Suche"
                        onMouseEnter={(e) => {
                          if (ep.has_file) {
                            e.currentTarget.style.color = 'var(--accent)'
                            e.currentTarget.style.backgroundColor = 'var(--accent-subtle)'
                          }
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = 'var(--text-muted)'
                          e.currentTarget.style.backgroundColor = ''
                        }}
                      >
                        <ScanSearch size={14} />
                      </button>
                      <button
                        onClick={() => onHistory(ep)}
                        disabled={!ep.has_file}
                        className="p-1.5 rounded transition-colors"
                        style={{
                          color: isExpanded && mode === 'history' ? 'var(--accent)' : 'var(--text-muted)',
                          opacity: ep.has_file ? 1 : 0.4,
                        }}
                        title={t('series_detail.history')}
                        onMouseEnter={(e) => {
                          if (ep.has_file) {
                            e.currentTarget.style.color = 'var(--accent)'
                            e.currentTarget.style.backgroundColor = 'var(--accent-subtle)'
                          }
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = isExpanded && mode === 'history' ? 'var(--accent)' : 'var(--text-muted)'
                          e.currentTarget.style.backgroundColor = ''
                        }}
                      >
                        {historyLoading && isExpanded && mode === 'history' ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : isExpanded && mode === 'history' ? (
                          <ChevronUp size={14} />
                        ) : (
                          <Clock size={14} />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Expanded panel */}
                  {isExpanded && (
                    <div style={{ borderBottom: '1px solid var(--border)' }}>
                      {mode === 'search' && (
                        <EpisodeSearchPanel
                          results={searchResults}
                          isLoading={searchLoading}
                          onProcess={onProcess}
                        />
                      )}
                      {mode === 'history' && (
                        <EpisodeHistoryPanel
                          entries={historyEntries}
                          isLoading={historyLoading}
                        />
                      )}
                      {mode === 'tracks' && (
                        <TrackPanel
                          episodeId={ep.id}
                          onOpenEditor={onOpenEditor}
                        />
                      )}
                    </div>
                  )}
                </div>
              )
            })}

          {/* Batch toolbar — shown when any episodes are selected */}
          {selectedEpisodes.size > 0 && (
            <div
              data-testid="episode-batch-toolbar"
              className="flex items-center gap-2 px-3 py-2 rounded-lg mt-2 mx-2 mb-2"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--accent-dim)',
              }}
            >
              <span className="text-xs font-medium mr-1" style={{ color: 'var(--accent)' }}>
                {selectedEpisodes.size} selected
              </span>
              <button
                onClick={() => { void startWantedBatchSearch([...selectedEpisodes]); clearAll() }}
                className="px-3 py-1 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
              >
                Search
              </button>
              <button
                onClick={() => { if (seriesId != null && !isExtracting) { void batchExtractAllTracks(seriesId) } clearAll() }}
                disabled={isExtracting}
                className="px-3 py-1 rounded text-xs font-medium inline-flex items-center gap-1.5"
                style={{
                  backgroundColor: isExtracting ? 'var(--accent-bg)' : 'var(--bg-surface)',
                  color: isExtracting ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${isExtracting ? 'var(--accent-dim)' : 'var(--border)'}`,
                  opacity: isExtracting ? 0.8 : 1,
                  cursor: isExtracting ? 'default' : 'pointer',
                }}
              >
                {isExtracting
                  ? <><Loader2 size={11} className="animate-spin" /> Extrahiere...</>
                  : 'Extract'}
              </button>
              <button
                onClick={() => { onOpenCleanupModal(); clearAll() }}
                className="px-3 py-1 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
              >
                Bereinigen
              </button>
              <button
                onClick={clearAll}
                className="ml-auto px-2 py-1 rounded text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                Clear
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Main Page ─────────────────────────────────────────────────────────────

export function SeriesDetailPage() {
  const { t } = useTranslation('library')
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  // Fix 5: guard against malformed route parameter producing NaN
  const seriesId = id && !isNaN(Number(id)) ? Number(id) : null
  const { data: series, isLoading, error } = useSeriesDetail(seriesId)

  // Episode action state
  const [expandedEp, setExpandedEp] = useState<{ id: number; mode: 'search' | 'history' | 'glossary' | 'tracks' } | null>(null)
  const [showGlossary, setShowGlossary] = useState(false)
  const [searchResults, setSearchResults] = useState<Record<number, WantedSearchResponse>>({})
  const [historyEntries, setHistoryEntries] = useState<Record<number, EpisodeHistoryEntry[]>>({})

  // Subtitle editor modal state
  const [editorFilePath, setEditorFilePath] = useState<string | null>(null)
  const [editorMode, setEditorMode] = useState<'preview' | 'edit'>('preview')

  // Extraction progress (driven by WebSocket batch_extract_progress events)
  const [extractProgress, setExtractProgress] = useState<{
    current: number
    total: number
    filename: string
  } | null>(null)
  // Sidecar management
  const [showCleanupModal, setShowCleanupModal] = useState(false)
  const queryClient = useQueryClient()
  const { data: sidecarData } = useQuery({
    queryKey: ['series-subtitles', seriesId],
    queryFn: () => seriesId != null ? listSeriesSubtitles(seriesId) : Promise.resolve({ subtitles: {} }),
    enabled: seriesId != null,
    staleTime: 30_000,
    // Poll while extraction is running so sidecar badges appear as files are written
    refetchInterval: extractProgress !== null ? 4_000 : false,
  })
  const sidecarMap: Record<string, SidecarSubtitle[]> = sidecarData?.subtitles ?? {}

  // WebSocket: batch extraction progress
  useWebSocket({
    onBatchExtractProgress: (data) => {
      const d = data as { series_id: number; current: number; total: number; filename: string }
      if (d.series_id === seriesId) {
        setExtractProgress({ current: d.current, total: d.total, filename: d.filename })
      }
    },
    onBatchExtractCompleted: (data) => {
      const d = data as { series_id: number; succeeded: number; failed: number; skipped: number }
      if (d.series_id !== seriesId) return
      setExtractProgress(null)
      void queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
      void queryClient.invalidateQueries({ queryKey: ['series', seriesId] })
      const msg = d.succeeded > 0
        ? `${d.succeeded} Track(s) extrahiert${d.failed > 0 ? `, ${d.failed} fehlgeschlagen` : ''}`
        : d.failed > 0
          ? `Extraktion fehlgeschlagen (${d.failed} Fehler)`
          : 'Extraktion abgeschlossen — alle bereits vorhanden'
      toast(msg, d.failed > 0 ? 'warning' : 'success')
    },
  })

  // Comparison and sync state
  const [comparisonPaths, setComparisonPaths] = useState<string[] | null>(null)
  const [syncFilePath, setSyncFilePath] = useState<string | null>(null)
  const [compareSelectorEp, setCompareSelectorEp] = useState<EpisodeInfo | null>(null)

  // Video sync modal (ffsubsync / alass)
  const [videoSyncEp, setVideoSyncEp] = useState<{ ep: EpisodeInfo; subtitlePath: string } | null>(null)

  // Health check state
  const [healthCheckPath, setHealthCheckPath] = useState<string | null>(null)
  const [healthScores, setHealthScores] = useState<Record<string, number | null>>({})

  // Interactive search modal state
  const [interactiveEp, setInteractiveEp] = useState<{ id: number; title: string } | null>(null)

  const episodeSearch = useEpisodeSearch()
  const _episodeHistory = useEpisodeHistory(expandedEp?.mode === 'history' ? expandedEp.id : 0)
  const processItem = useProcessWantedItem()
  const startSeriesSearch = useStartWantedBatch()
  const [seriesSearchStarted, setSeriesSearchStarted] = useState(false)

  // AniDB absolute order
  const updateSeriesSettingsMutation = useUpdateSeriesSettings()
  const { data: anidbStatus } = useAnidbMappingStatus()
  const refreshAnidbMappingMutation = useRefreshAnidbMapping()

  const handleToggleAbsoluteOrder = useCallback((enabled: boolean) => {
    if (!seriesId) return
    updateSeriesSettingsMutation.mutate(
      { seriesId, settings: { absolute_order: enabled } },
      {
        onSuccess: () => toast(enabled ? 'Absolute order enabled' : 'Absolute order disabled'),
        onError: () => toast('Failed to update series settings', 'error'),
      }
    )
  }, [seriesId, updateSeriesSettingsMutation])

  const handleRefreshAnidbMapping = useCallback(() => {
    refreshAnidbMappingMutation.mutate(undefined, {
      onSuccess: () => toast('AniDB mapping refresh started'),
      onError: () => toast('Failed to refresh AniDB mapping', 'error'),
    })
  }, [refreshAnidbMappingMutation])

  const handleSearchAllEpisodes = useCallback(() => {
    if (!seriesId) return
    startSeriesSearch.mutate({ seriesId }, {
      onSuccess: (data) => {
        setSeriesSearchStarted(true)
        toast(`Suche gestartet für ${data.total_items} Episoden`, 'success')
      },
      onError: () => toast('Suche konnte nicht gestartet werden', 'error'),
    })
  }, [seriesId, startSeriesSearch])

  const handleSearch = useCallback((ep: EpisodeInfo) => {
    if (expandedEp?.id === ep.id && expandedEp?.mode === 'search') {
      setExpandedEp(null)
      return
    }
    setExpandedEp({ id: ep.id, mode: 'search' })
    episodeSearch.mutate(ep.id, {
      onSuccess: (data) => {
        setSearchResults((prev) => ({ ...prev, [ep.id]: data }))
      },
      onError: () => {
        toast('Search failed', 'error')
      },
    })
  }, [expandedEp, episodeSearch])

  const handleHistory = useCallback((ep: EpisodeInfo) => {
    if (expandedEp?.id === ep.id && expandedEp?.mode === 'history') {
      setExpandedEp(null)
      return
    }
    setExpandedEp({ id: ep.id, mode: 'history' })
    // Fetch history via mutation-style (since the hook is lazy)
    import('@/api/client').then(({ episodeHistory: fetchHistory }) => {
      fetchHistory(ep.id).then((data) => {
        setHistoryEntries((prev) => ({ ...prev, [ep.id]: data.entries }))
      }).catch(() => {
        setHistoryEntries((prev) => ({ ...prev, [ep.id]: [] }))
        toast('Failed to load history', 'error')
      })
    })
  }, [expandedEp])

  const handleProcess = useCallback((wantedId: number) => {
    processItem.mutate(wantedId, {
      onSuccess: () => {
        toast('Download started')
      },
      onError: () => {
        toast('Download failed', 'error')
      },
    })
  }, [processItem])

  const handleClose = useCallback(() => {
    setExpandedEp(null)
  }, [])

  const handleTracks = useCallback((ep: EpisodeInfo) => {
    if (expandedEp?.id === ep.id && expandedEp?.mode === 'tracks') {
      setExpandedEp(null)
      return
    }
    setExpandedEp({ id: ep.id, mode: 'tracks' })
  }, [expandedEp])

  const handleCompare = useCallback((ep: EpisodeInfo) => {
    setCompareSelectorEp(ep)
  }, [])

  const handleSync = useCallback((filePath: string) => {
    setSyncFilePath(filePath)
  }, [])

  const handleAutoSync = useCallback((filePath: string) => {
    toast('Auto-syncing…', 'info')
    void autoSyncFile(filePath).then(() => {
      toast('Auto-sync complete')
    }).catch((err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Auto-sync failed'
      toast(msg, 'error')
    })
  }, [])

  const handleVideoSync = useCallback((ep: EpisodeInfo, subtitlePath: string) => {
    setVideoSyncEp({ ep, subtitlePath })
  }, [])

  const handleHealthCheck = useCallback((filePath: string) => {
    setHealthCheckPath(filePath)
  }, [])

  const handleDeleteSidecar = useCallback(async (path: string) => {
    try {
      await deleteSubtitles([path])
      toast('Sidecar gelöscht')
      await queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
    } catch {
      toast('Löschen fehlgeschlagen', 'error')
    }
  }, [queryClient, seriesId])

  // Group episodes by season
  const seasonGroups = useMemo(() => {
    if (!series?.episodes) return []
    const groups = new Map<number, EpisodeInfo[]>()
    for (const ep of series.episodes) {
      if (!groups.has(ep.season)) {
        groups.set(ep.season, [])
      }
      groups.get(ep.season)!.push(ep)
    }
    return Array.from(groups.entries())
      .sort((a, b) => b[0] - a[0]) // Latest season first
  }, [series?.episodes])

  // Count missing subs — align with Library's definition:
  // only episodes where existing_sub is '' or null/undefined (no subtitle at all).
  // 'srt', 'embedded_srt', 'embedded_ass', 'ass' etc. are NOT missing — they are
  // upgrade candidates or already satisfied, matching get_series_missing_counts() logic.
  const missingCount = useMemo(() => {
    if (!series?.episodes) return 0
    let count = 0
    for (const ep of series.episodes) {
      if (!ep.has_file) continue
      for (const lang of series.target_languages) {
        const sub = ep.subtitles[lang]
        if (sub == null || sub === '') {
          count++
        }
      }
    }
    return count
  }, [series])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  if (error || !series) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/library')}
          className="flex items-center gap-2 text-sm transition-colors"
          style={{ color: 'var(--text-secondary)' }}
        >
          <ArrowLeft size={14} />
          {t('series_detail.back_to_library')}
        </button>
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <p style={{ color: 'var(--error)' }}>{t('series_detail.failed_to_load')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4 animate-in">
      {/* Back button */}
      <button
        onClick={() => navigate('/library')}
        className="flex items-center gap-2 text-sm transition-colors hover:opacity-80"
        style={{ color: 'var(--text-secondary)' }}
      >
        <ArrowLeft size={14} />
        Back to Library
      </button>

      {/* Hero Header — like Bazarr */}
      <div
        className="rounded-lg overflow-hidden relative"
        style={{ border: '1px solid var(--border)' }}
      >
        {/* Fanart background */}
        {series.fanart && (
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `url(${series.fanart})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              opacity: 0.15,
              filter: 'blur(2px)',
            }}
          />
        )}
        <div
          className="absolute inset-0"
          style={{
            background: 'linear-gradient(135deg, rgba(23,25,35,0.95) 0%, rgba(30,33,48,0.85) 100%)',
          }}
        />

        <div className="relative flex gap-5 p-5">
          {/* Poster */}
          <div
            className="flex-shrink-0 w-[150px] rounded-lg overflow-hidden shadow-lg"
            style={{ border: '1px solid var(--border)' }}
          >
            {series.poster ? (
              <img
                src={series.poster}
                alt={series.title}
                className="w-full h-auto"
              />
            ) : (
              <div
                className="w-full aspect-[2/3] flex items-center justify-center"
                style={{ backgroundColor: 'var(--bg-surface)' }}
              >
                <FileVideo size={32} style={{ color: 'var(--text-muted)' }} />
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0 flex flex-col gap-3">
            <h1 className="text-xl font-bold leading-tight">{series.title}</h1>

            {/* Metadata chips */}
            <div className="flex flex-wrap gap-2 text-xs">
              <span
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded"
                style={{ backgroundColor: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)' }}
              >
                <Folder size={11} />
                {series.path}
              </span>
              <span
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded"
                style={{ backgroundColor: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)' }}
              >
                <FileVideo size={11} />
                {t('series_detail.files', { count: series.episode_file_count })}
              </span>
              <span
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded"
                style={{
                  backgroundColor: missingCount > 0 ? 'var(--warning-bg)' : 'var(--success-bg)',
                  color: missingCount > 0 ? 'var(--warning)' : 'var(--success)',
                }}
              >
                <AlertTriangle size={11} />
                {t('series_detail.missing_subtitles', { count: missingCount })}
              </span>
              <span
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded"
                style={{ backgroundColor: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)' }}
              >
                <Play size={11} />
                {series.status === 'continuing' ? t('series_detail.continuing') : series.status === 'ended' ? t('series_detail.ended') : series.status}
              </span>
              {series.tags.length > 0 && (
                <span
                  className="inline-flex items-center gap-1.5 px-2 py-1 rounded"
                  style={{ backgroundColor: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)' }}
                >
                  <Tag size={11} />
                  {series.tags.join(' | ')}
                </span>
              )}
            </div>

            {/* Language info */}
            <div className="flex flex-wrap gap-2 text-xs">
              <span
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded"
                style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
              >
                <Globe size={11} />
                {series.profile_name}
              </span>
              {series.target_language_names.map((name, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded font-medium"
                  style={{
                    backgroundColor: 'var(--accent-subtle)',
                    color: 'var(--accent)',
                    border: '1px solid var(--accent-dim)',
                  }}
                >
                  {name}
                </span>
              ))}
              <span
                className="inline-flex items-center gap-1 px-2 py-1 rounded"
                style={{ backgroundColor: 'rgba(99,102,241,0.1)', color: '#818cf8' }}
              >
                {series.source_language_name}
              </span>
              <button
                onClick={() => setShowGlossary(!showGlossary)}
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded transition-colors"
                style={{
                  backgroundColor: showGlossary ? 'var(--accent-bg)' : 'rgba(255,255,255,0.06)',
                  color: showGlossary ? 'var(--accent)' : 'var(--text-secondary)',
                }}
                onMouseEnter={(e) => {
                  if (!showGlossary) {
                    e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!showGlossary) {
                    e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)'
                  }
                }}
              >
                <BookOpen size={11} />
                {t('series_detail.glossary')}
              </button>

              {/* Absolute Order toggle */}
              <button
                onClick={() => handleToggleAbsoluteOrder(!(series.absolute_order ?? false))}
                disabled={updateSeriesSettingsMutation.isPending}
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded transition-colors"
                style={{
                  backgroundColor: series.absolute_order ? 'var(--accent-bg)' : 'rgba(255,255,255,0.06)',
                  color: series.absolute_order ? 'var(--accent)' : 'var(--text-secondary)',
                  opacity: updateSeriesSettingsMutation.isPending ? 0.6 : 1,
                  cursor: updateSeriesSettingsMutation.isPending ? 'default' : 'pointer',
                }}
                title="Use AniDB absolute episode numbers for subtitle search (anime)"
                onMouseEnter={(e) => {
                  if (!updateSeriesSettingsMutation.isPending && !series.absolute_order) {
                    e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!series.absolute_order) {
                    e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)'
                  }
                }}
              >
                {updateSeriesSettingsMutation.isPending
                  ? <Loader2 size={11} className="animate-spin" />
                  : <Database size={11} />
                }
                Absolute order
              </button>

              {/* AniDB refresh button — shown only when absolute order is active */}
              {series.absolute_order && (
                <button
                  onClick={handleRefreshAnidbMapping}
                  disabled={refreshAnidbMappingMutation.isPending}
                  className="inline-flex items-center gap-1.5 px-2 py-1 rounded transition-colors"
                  style={{
                    backgroundColor: 'rgba(255,255,255,0.06)',
                    color: 'var(--text-secondary)',
                    opacity: refreshAnidbMappingMutation.isPending ? 0.6 : 1,
                    cursor: refreshAnidbMappingMutation.isPending ? 'default' : 'pointer',
                  }}
                  title={anidbStatus?.last_sync
                    ? `Last sync: ${new Date(anidbStatus.last_sync).toLocaleString()} · ${anidbStatus.entry_count ?? 0} entries`
                    : 'Refresh AniDB mapping database'}
                  onMouseEnter={(e) => {
                    if (!refreshAnidbMappingMutation.isPending) {
                      e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)'
                  }}
                >
                  {refreshAnidbMappingMutation.isPending
                    ? <Loader2 size={11} className="animate-spin" />
                    : <RefreshCw size={11} />
                  }
                  Refresh AniDB
                </button>
              )}

            </div>

            {/* Series-level action toolbar */}
            <div className="flex flex-wrap gap-2 pt-1" style={{ borderTop: '1px solid rgba(255,255,255,0.07)' }}>
              {/* Extract all embedded tracks */}
              <button
                onClick={() => { if (seriesId != null && !extractProgress) { void batchExtractAllTracks(seriesId) } }}
                disabled={extractProgress !== null}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors"
                style={{
                  backgroundColor: extractProgress ? 'var(--accent-bg)' : 'rgba(255,255,255,0.06)',
                  color: extractProgress ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${extractProgress ? 'var(--accent-dim)' : 'transparent'}`,
                  cursor: extractProgress ? 'default' : 'pointer',
                }}
                onMouseEnter={(e) => { if (!extractProgress) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
                onMouseLeave={(e) => { if (!extractProgress) e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)' }}
                title="Alle eingebetteten Subtitle-Tracks der Serie extrahieren"
              >
                {extractProgress
                  ? <><Loader2 size={11} className="animate-spin" /> Extrahiere {extractProgress.current}/{extractProgress.total}…</>
                  : <><Layers size={11} /> Tracks extrahieren</>
                }
              </button>

              {/* Sidecar cleanup modal */}
              <button
                onClick={() => setShowCleanupModal(true)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors"
                style={{ backgroundColor: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)', cursor: 'pointer' }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)' }}
                title="Sidecar-Untertitel bereinigen (nach Sprache/Format filtern)"
              >
                <Trash size={11} />
                Bereinigen
              </button>

              {/* Search all missing */}
              {missingCount > 0 && (
                <button
                  onClick={handleSearchAllEpisodes}
                  disabled={startSeriesSearch.isPending || seriesSearchStarted}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors"
                  style={{
                    backgroundColor: seriesSearchStarted ? 'var(--success-bg)' : 'var(--accent-bg)',
                    color: seriesSearchStarted ? 'var(--success)' : 'var(--accent)',
                    opacity: startSeriesSearch.isPending ? 0.7 : 1,
                    cursor: startSeriesSearch.isPending || seriesSearchStarted ? 'default' : 'pointer',
                    border: '1px solid transparent',
                  }}
                  onMouseEnter={(e) => {
                    if (!startSeriesSearch.isPending && !seriesSearchStarted)
                      e.currentTarget.style.opacity = '0.85'
                  }}
                  onMouseLeave={(e) => { e.currentTarget.style.opacity = startSeriesSearch.isPending ? '0.7' : '1' }}
                  title={`${missingCount} fehlende Untertitel bei Providern suchen`}
                >
                  {startSeriesSearch.isPending
                    ? <Loader2 size={11} className="animate-spin" />
                    : seriesSearchStarted ? <Sparkles size={11} /> : <Search size={11} />
                  }
                  {seriesSearchStarted ? 'Suche läuft…' : `${missingCount} fehlende suchen`}
                </button>
              )}
            </div>

            {/* Overview */}
            {series.overview && (
              <p className="text-xs leading-relaxed line-clamp-3" style={{ color: 'var(--text-secondary)' }}>
                {series.overview}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Glossary Panel */}
      {showGlossary && (
        <div
          className="rounded-lg overflow-hidden"
          style={{ border: '1px solid var(--border)' }}
        >
          {seriesId !== null && <GlossaryPanel seriesId={seriesId} />}
        </div>
      )}

      {/* Episode Table */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ border: '1px solid var(--border)' }}
      >
        {/* Table Header */}
        <div
          className="flex items-center px-4 py-2"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div className="w-6 flex-shrink-0" />
          <div className="w-5 flex-shrink-0" />
          <div
            className="w-12 flex-shrink-0 text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            {t('series_detail.ep')}
          </div>
          <div
            className="flex-1 text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            {t('series_detail.title_col')}
          </div>
          <div
            className="w-24 flex-shrink-0 text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            {t('series_detail.audio')}
          </div>
          <div
            className="flex-1 min-w-[200px] text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            {t('series_detail.subtitles')}
          </div>
          <div
            className="w-40 flex-shrink-0 text-[11px] font-semibold uppercase tracking-wider text-right"
            style={{ color: 'var(--text-secondary)' }}
          >
            {t('series_detail.actions')}
          </div>
        </div>

        {/* Extraction Progress Banner */}
        {extractProgress && (
          <div
            className="px-4 py-3"
            style={{ backgroundColor: 'var(--accent-bg)', borderBottom: '1px solid var(--accent-dim)' }}
          >
            <div className="flex items-center gap-2 mb-2">
              <Loader2 size={13} className="animate-spin flex-shrink-0" style={{ color: 'var(--accent)' }} />
              <span className="text-xs font-semibold" style={{ color: 'var(--accent)' }}>
                Extrahiere Tracks — {extractProgress.current} / {extractProgress.total} Episoden
              </span>
              {extractProgress.filename && (
                <span
                  className="text-xs truncate"
                  style={{ color: 'var(--text-muted)', maxWidth: '340px' }}
                  title={extractProgress.filename}
                >
                  · {extractProgress.filename}
                </span>
              )}
            </div>
            <ProgressBar value={extractProgress.current} max={extractProgress.total} showLabel={false} />
          </div>
        )}

        {/* Season Groups */}
        {seasonGroups.map(([season, episodes]) => (
          <SeasonGroup
            key={season}
            season={season}
            episodes={episodes}
            targetLanguages={series.target_languages}
            seriesId={seriesId}
            isExtracting={extractProgress !== null}
            expandedEp={expandedEp}
            onSearch={handleSearch}
            onInteractiveSearch={(ep) => setInteractiveEp({ id: ep.id, title: `${series.title} ${ep.title ? `– ${ep.title}` : ''}`.trim() })}
            onHistory={handleHistory}
            onTracks={handleTracks}
            onClose={handleClose}
            searchResults={expandedEp ? searchResults[expandedEp.id] ?? null : null}
            searchLoading={episodeSearch.isPending}
            historyEntries={expandedEp ? historyEntries[expandedEp.id] ?? [] : []}
            historyLoading={expandedEp?.mode === 'history' && !(expandedEp.id in historyEntries)}
            onProcess={handleProcess}
            onPreviewSub={(path) => { setEditorFilePath(path); setEditorMode('preview') }}
            onEditSub={(path) => { setEditorFilePath(path); setEditorMode('edit') }}
            onCompare={handleCompare}
            onSync={handleSync}
            onAutoSync={handleAutoSync}
            onVideoSync={handleVideoSync}
            onHealthCheck={handleHealthCheck}
            healthScores={healthScores}
            onOpenEditor={(path) => { setEditorFilePath(path); setEditorMode('edit') }}
            sidecarMap={sidecarMap}
            onDeleteSidecar={handleDeleteSidecar}
            onOpenCleanupModal={() => setShowCleanupModal(true)}
            t={t}
          />
        ))}

        {seasonGroups.length === 0 && (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
            {t('series_detail.no_episodes')}
          </div>
        )}
      </div>

      {/* Sidecar Cleanup Modal */}
      {showCleanupModal && seriesId != null && (
        <SubtitleCleanupModal
          seriesId={seriesId}
          targetLanguages={series?.target_languages ?? []}
          onClose={() => setShowCleanupModal(false)}
        />
      )}

      {/* Subtitle Editor Modal */}
      {editorFilePath && (
        <SubtitleEditorModal
          filePath={editorFilePath}
          initialMode={editorMode}
          onClose={() => setEditorFilePath(null)}
        />
      )}

      {/* Comparison Selector Modal */}
      {compareSelectorEp && series && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setCompareSelectorEp(null)
          }}
        >
          <div className="w-full max-w-md mx-4">
            <ComparisonSelector
              availableFiles={
                Object.entries(compareSelectorEp.subtitles)
                  .filter(([, f]) => f === 'ass' || f === 'srt')
                  .map(([lang, fmt]) => ({
                    path: deriveSubtitlePath(compareSelectorEp.file_path, lang, fmt),
                    label: `${lang.toUpperCase()} (${fmt.toUpperCase()})`,
                  }))
              }
              onCompare={(paths) => {
                setComparisonPaths(paths)
                setCompareSelectorEp(null)
              }}
              onClose={() => setCompareSelectorEp(null)}
            />
          </div>
        </div>
      )}

      {/* Comparison View Modal */}
      {comparisonPaths && (
        <div
          className="fixed inset-0 z-50 flex flex-col"
          style={{ backgroundColor: 'var(--bg-primary)' }}
        >
          <Suspense
            fallback={
              <div className="flex flex-1 items-center justify-center" style={{ color: 'var(--text-muted)' }}>
                <Loader2 size={24} className="animate-spin" />
              </div>
            }
          >
            <SubtitleComparison
              filePaths={comparisonPaths}
              onClose={() => setComparisonPaths(null)}
            />
          </Suspense>
        </div>
      )}

      {/* Sync Controls Modal */}
      {syncFilePath && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setSyncFilePath(null)
          }}
        >
          <div className="w-full max-w-lg mx-4">
            <Suspense
              fallback={
                <div
                  className="rounded-lg p-8 flex items-center justify-center"
                  style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
                >
                  <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
                </div>
              }
            >
              <SyncControls
                filePath={syncFilePath}
                onSynced={() => setSyncFilePath(null)}
                onClose={() => setSyncFilePath(null)}
              />
            </Suspense>
          </div>
        </div>
      )}

      {/* Video Sync Modal (ffsubsync / alass) */}
      {videoSyncEp && (
        <Suspense fallback={null}>
          <SyncModal
            episodeId={videoSyncEp.ep.id}
            subtitlePath={videoSyncEp.subtitlePath}
            videoPath={videoSyncEp.ep.file_path}
            onClose={() => setVideoSyncEp(null)}
            onComplete={() => {
              toast('Video-Sync abgeschlossen')
              setVideoSyncEp(null)
            }}
          />
        </Suspense>
      )}

      {/* Interactive Search Modal */}
      <InteractiveSearchModal
        open={!!interactiveEp}
        episodeId={interactiveEp?.id}
        itemTitle={interactiveEp?.title ?? ''}
        onClose={() => setInteractiveEp(null)}
        onDownloaded={() => setInteractiveEp(null)}
      />

      {/* Health Check Panel Modal */}
      {healthCheckPath && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setHealthCheckPath(null)
          }}
        >
          <div className="w-full max-w-lg mx-4">
            <Suspense
              fallback={
                <div
                  className="rounded-lg p-8 flex items-center justify-center"
                  style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
                >
                  <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
                </div>
              }
            >
              <HealthCheckPanel
                filePath={healthCheckPath}
                onClose={() => setHealthCheckPath(null)}
                onFixed={() => {
                  // Update health scores cache when a fix is applied
                  import('@/api/client').then(({ runHealthCheck }) => {
                    runHealthCheck(healthCheckPath).then((result) => {
                      setHealthScores((prev) => ({ ...prev, [healthCheckPath]: result.score }))
                    }).catch(() => { /* ignore */ })
                  })
                }}
              />
            </Suspense>
          </div>
        </div>
      )}
    </div>
  )
}
