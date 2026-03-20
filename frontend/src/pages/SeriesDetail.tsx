import { useState, useMemo, useCallback, lazy, Suspense, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { SeasonSummaryBar } from '@/components/library/SeasonSummaryBar'
import { EpisodeRow } from '@/components/library/EpisodeRow'
import { useSeriesDetail, useEpisodeSearch, useEpisodeHistory, useProcessWantedItem, useGlossaryEntries, useCreateGlossaryEntry, useUpdateGlossaryEntry, useDeleteGlossaryEntry, useStartWantedBatch, useUpdateSeriesSettings, useAnidbMappingStatus, useRefreshAnidbMapping, useBatchTranslate, useSuggestGlossaryTerms, useExportGlossaryTsv, useStreamingEnabled, useSeriesFansubPrefs } from '@/hooks/useApi'
import {
  ArrowLeft, Loader2, ChevronDown, ChevronRight,
  Folder, FileVideo, AlertTriangle, Play, Tag, Globe, Search,
  Download, X, BookOpen, Plus, Edit2, Trash2, Check,
  Eye, Pencil, Database, RefreshCw,
  Layers, Sparkles, Trash, FileCode, Wand2,
} from 'lucide-react'
import { formatRelativeTime } from '@/lib/utils'
import { toast } from '@/components/shared/Toast'
import SubtitleEditorModal from '@/components/editor/SubtitleEditorModal'
import { PlayerModal } from '@/components/player/PlayerModal'
import type { PlayerSubtitleTrack } from '@/lib/types'
import { TrackPanel } from '@/components/tracks/TrackPanel'
import { autoSyncFile, startWantedBatchSearch, batchExtractAllTracks, listSeriesSubtitles, deleteSubtitles, getSubtitleDownloadUrl, getSeriesSubtitleExportUrl, exportSubtitleNfo } from '@/api/client'
import type { GlossaryCandidate } from '@/api/client'
import { useWebSocket } from '@/hooks/useWebSocket'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { InteractiveSearchModal } from '@/components/wanted/InteractiveSearchModal'
import { ComparisonSelector } from '@/components/comparison/ComparisonSelector'
import { HealthBadge } from '@/components/health/HealthBadge'
import { SubtitleCleanupModal } from '@/components/shared/SubtitleCleanupModal'
import type { EpisodeInfo, WantedSearchResponse, EpisodeHistoryEntry, SidecarSubtitle } from '@/lib/types'
import { EpisodeActionMenu } from '@/components/episodes/EpisodeActionMenu'
import { FansubOverrideModal } from '@/components/series/FansubOverrideModal'
import { SeriesAudioTrackPicker } from '@/components/series/SeriesAudioTrackPicker'
import { normLang, deriveSubtitlePath } from '@/components/series/seriesUtils'
import { SubtitleActionsMenu } from '@/components/processing/SubtitleActionsMenu'
import { SeriesProcessingOverride } from '@/components/processing/SeriesProcessingOverride'

import { SubBadge } from '@/components/series/SubBadge'
import { ScoreBadge } from '@/components/series/ScoreBadge'
import { EpisodeSearchPanel } from '@/components/series/EpisodeSearchPanel'
import { EpisodeHistoryPanel } from '@/components/series/EpisodeHistoryPanel'

const SubtitleComparison = lazy(() => import('@/components/comparison/SubtitleComparison').then(m => ({ default: m.SubtitleComparison })))
const SyncControls = lazy(() => import('@/components/sync/SyncControls').then(m => ({ default: m.SyncControls })))
const SyncModal = lazy(() => import('@/components/sync/SyncModal').then(m => ({ default: m.SyncModal })))
const HealthCheckPanel = lazy(() => import('@/components/health/HealthCheckPanel').then(m => ({ default: m.HealthCheckPanel })))

// ─── Glossary Panel ────────────────────────────────────────────────────────

const TERM_TYPE_COLORS: Record<string, string> = {
  character: 'var(--accent)',
  place: '#3b82f6',
  other: 'var(--text-muted)',
}

function TermTypeBadge({ type }: { type: string }) {
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[10px] font-medium"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: `1px solid ${TERM_TYPE_COLORS[type] ?? 'var(--border)'}`,
        color: TERM_TYPE_COLORS[type] ?? 'var(--text-muted)',
      }}
    >
      {type}
    </span>
  )
}

function GlossaryPanel({ seriesId }: { seriesId: number }) {
  const { t } = useTranslation('library')
  const { data, isLoading } = useGlossaryEntries(seriesId)
  const createEntry = useCreateGlossaryEntry()
  const updateEntry = useUpdateGlossaryEntry()
  const deleteEntry = useDeleteGlossaryEntry()
  const suggestTerms = useSuggestGlossaryTerms()
  const exportTsv = useExportGlossaryTsv()
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [formData, setFormData] = useState({ source_term: '', target_term: '', notes: '' })
  const [showCandidates, setShowCandidates] = useState<boolean>(false)
  const [candidates, setCandidates] = useState<GlossaryCandidate[]>([])

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

  const handleSuggest = () => {
    suggestTerms.mutate(
      { seriesId, options: { source_lang: 'en', min_freq: 3 } },
      {
        onSuccess: (data) => {
          setCandidates(data.candidates)
          setShowCandidates(true)
          if (data.candidates.length === 0) toast('No new candidates found', 'info')
        },
        onError: () => toast('Failed to fetch suggestions', 'error'),
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
        <div className="flex items-center gap-1.5">
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
          <button
            onClick={handleSuggest}
            disabled={suggestTerms.isPending}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium hover:opacity-90"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            {suggestTerms.isPending ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
            Suggest
          </button>
          <button
            onClick={() => exportTsv.mutate({ seriesId })}
            disabled={exportTsv.isPending}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium hover:opacity-90"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            <Download size={11} />
            TSV
          </button>
        </div>
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

      {/* Candidates */}
      {showCandidates && candidates.length > 0 && (
        <div
          className="rounded-lg p-3 space-y-2"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
              {candidates.length} Suggestions
            </span>
            <button onClick={() => setShowCandidates(false)} style={{ color: 'var(--text-muted)' }}>
              <X size={12} />
            </button>
          </div>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {candidates.map((c) => (
              <div
                key={c.source_term}
                className="flex items-center gap-2 px-2 py-1 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)' }}
              >
                <span className="font-medium flex-1" style={{ color: 'var(--text-primary)' }}>
                  {c.source_term}
                </span>
                <TermTypeBadge type={c.term_type} />
                <span style={{ color: 'var(--text-muted)' }}>{Math.round(c.confidence * 100)}%</span>
                <button
                  onClick={() => {
                    setFormData({ source_term: c.source_term, target_term: '', notes: '' })
                    setShowAdd(true)
                    setShowCandidates(false)
                  }}
                  className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-white"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  <Plus size={10} /> Add
                </button>
              </div>
            ))}
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
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Type</th>
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
                    <div className="flex items-center gap-1 flex-wrap">
                      <TermTypeBadge type={entry.term_type ?? 'other'} />
                      {entry.approved === 0 && (
                        <span className="text-[10px] px-1 rounded" style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
                          pending
                        </span>
                      )}
                    </div>
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

// ─── Season Group ──────────────────────────────────────────────────────────

function SeasonGroup({ season, episodes, targetLanguages, seriesId: _seriesId, isExtracting, onExtract, expandedEp, onSearch, onInteractiveSearch, onHistory, onTracks, onClose, searchResults, searchLoading, historyEntries, historyLoading, onProcess, onPreviewSub, onEditSub, onCompare, onSync, onAutoSync, onVideoSync, onHealthCheck, healthScores, onOpenEditor, sidecarMap, onDeleteSidecar, onOpenCleanupModal, onPreview, streamingEnabled, onRefreshSidecars, t }: {
  season: number
  episodes: EpisodeInfo[]
  targetLanguages: string[]
  seriesId: number | null
  isExtracting?: boolean
  onExtract?: () => void
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
  onAutoSync: (subtitlePath: string, videoPath: string) => void
  onVideoSync: (ep: EpisodeInfo, subtitlePath: string) => void
  onHealthCheck: (filePath: string) => void
  healthScores: Record<string, number | null>
  onOpenEditor: (filePath: string) => void
  sidecarMap: Record<string, SidecarSubtitle[]>
  onDeleteSidecar: (path: string) => Promise<void>
  onOpenCleanupModal: () => void
  onPreview: (ep: EpisodeInfo) => void
  streamingEnabled: boolean
  onRefreshSidecars?: () => void
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
  const batchTranslateMutation = useBatchTranslate()

  return (
    <div>
      {/* Season Header — pill-shaped tab style */}
      <div
        className="flex items-center"
        style={{
          backgroundColor: expanded ? 'var(--bg-elevated)' : 'var(--bg-surface)',
          borderBottom: expanded ? '1px solid var(--border)' : 'none',
          transition: 'background-color 0.15s',
        }}
      >
        <button
          data-testid="season-group"
          onClick={() => setExpanded(!expanded)}
          className="flex-1 flex items-center gap-2 text-left transition-colors"
          style={{ padding: '8px 16px' }}
        >
          {expanded ? (
            <ChevronDown size={14} style={{ color: 'var(--accent)' }} />
          ) : (
            <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
          )}
          <span style={{ fontSize: '13px', fontWeight: 600 }}>
            {t('series_detail.season', { number: season })}
          </span>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '4px' }}>
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
                <EpisodeRow
                  key={ep.id}
                  ep={ep}
                  targetLanguages={targetLanguages}
                >
                <div data-testid="episode-row">
                  <div
                    className="flex items-start transition-colors"
                    style={{
                      padding: '10px 14px',
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
                                  <>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(matchingSidecar.path) }}
                                      className="p-0.5 rounded hover:opacity-80"
                                      style={{ color: 'var(--error)', lineHeight: 1 }}
                                      title={`Löschen: ${matchingSidecar.path}`}
                                    >
                                      <X size={9} />
                                    </button>
                                    <a
                                      href={getSubtitleDownloadUrl(matchingSidecar.path)}
                                      download
                                      title={`Download ${matchingSidecar.language} ${matchingSidecar.format}`}
                                      className="ml-1 text-neutral-400 hover:text-teal-400 transition-colors"
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <svg
                                        xmlns="http://www.w3.org/2000/svg"
                                        className="h-3.5 w-3.5 inline"
                                        viewBox="0 0 20 20"
                                        fill="currentColor"
                                        aria-hidden="true"
                                      >
                                        <path
                                          fillRule="evenodd"
                                          d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                                          clipRule="evenodd"
                                        />
                                      </svg>
                                    </a>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); exportSubtitleNfo(matchingSidecar.path).then(() => toast('NFO exported', 'success')).catch(() => toast('NFO export failed', 'error')) }}
                                      className="p-0.5 rounded transition-colors"
                                      style={{ color: 'var(--text-muted)', lineHeight: 1 }}
                                      title="Export NFO sidecar"
                                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                                    >
                                      <FileCode size={11} />
                                    </button>
                                    <SubtitleActionsMenu
                                      subtitlePath={matchingSidecar.path}
                                      onRefresh={onRefreshSidecars}
                                    />
                                  </>
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
                                <a
                                  href={getSubtitleDownloadUrl(s.path)}
                                  download
                                  title={`Download ${s.language} ${s.format}`}
                                  className="ml-1 text-neutral-400 hover:text-teal-400 transition-colors"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <svg
                                    xmlns="http://www.w3.org/2000/svg"
                                    className="h-3.5 w-3.5 inline"
                                    viewBox="0 0 20 20"
                                    fill="currentColor"
                                    aria-hidden="true"
                                  >
                                    <path
                                      fillRule="evenodd"
                                      d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                                      clipRule="evenodd"
                                    />
                                  </svg>
                                </a>
                                <SubtitleActionsMenu
                                  subtitlePath={s.path}
                                  onRefresh={onRefreshSidecars}
                                />
                              </span>
                            ))
                          })()}
                        </>
                      ) : (
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>No file</span>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="w-64 flex-shrink-0 flex gap-0.5 justify-end">
                      {streamingEnabled && ep.has_file && ep.file_path && (
                        <button
                          onClick={() => onPreview(ep)}
                          className="hover-surface p-1 rounded text-[var(--text-muted)] hover:text-[var(--teal-accent)]"
                          title="Preview in player"
                          aria-label={`Preview episode ${ep.episode}`}
                        >
                          <Play size={14} />
                        </button>
                      )}
                      {(() => {
                        const firstLang = ep.has_file
                          ? Object.entries(ep.subtitles).find(([, f]) => f === 'ass' || f === 'srt')
                          : null
                        const firstSubPath = firstLang
                          ? deriveSubtitlePath(ep.file_path, firstLang[0], firstLang[1])
                          : null
                        const hasMultipleSubs = ep.has_file
                          ? Object.values(ep.subtitles).filter(f => f === 'ass' || f === 'srt').length >= 2
                          : false
                        return (
                          <EpisodeActionMenu
                            ep={ep}
                            isExpanded={isExpanded}
                            mode={mode}
                            searchLoading={searchLoading}
                            historyLoading={historyLoading}
                            firstSubPath={firstSubPath}
                            hasMultipleSubs={hasMultipleSubs}
                            onSearch={() => onSearch(ep)}
                            onEditSub={onEditSub}
                            onPreviewSub={onPreviewSub}
                            onCompare={() => onCompare(ep)}
                            onSync={onSync}
                            onAutoSync={onAutoSync}
                            onVideoSync={(subtitlePath) => onVideoSync(ep, subtitlePath)}
                            onHealthCheck={onHealthCheck}
                            onTracks={() => onTracks(ep)}
                            onInteractiveSearch={() => onInteractiveSearch(ep)}
                            onHistory={() => onHistory(ep)}
                            onClose={onClose}
                          />
                        )
                      })()}
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
                </EpisodeRow>
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
                onClick={() => { onExtract?.(); clearAll() }}
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
                onClick={() => { void batchTranslateMutation.mutate([...selectedEpisodes]); clearAll() }}
                disabled={batchTranslateMutation.isPending}
                className="px-3 py-1 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
              >
                Translate
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

  // Web player state
  const { data: streamingEnabled } = useStreamingEnabled()
  const seekFnRef = useRef<((seconds: number) => void) | null>(null)
  const [playerState, setPlayerState] = useState<{
    videoPath: string
    tracks: PlayerSubtitleTrack[]
  } | null>(null)

  // Extraction progress (driven by WebSocket batch_extract_progress events)
  const [extractProgress, setExtractProgress] = useState<{
    current: number
    total: number
    filename: string
  } | null>(null)
  // Sidecar management
  const [showCleanupModal, setShowCleanupModal] = useState(false)
  const [fansubOpen, setFansubOpen] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [deleteAlsoBlacklist, setDeleteAlsoBlacklist] = useState(false)
  const queryClient = useQueryClient()
  const { data: sidecarData } = useQuery({
    queryKey: ['series-subtitles', seriesId],
    queryFn: () => seriesId != null ? listSeriesSubtitles(seriesId) : Promise.resolve({ subtitles: {} }),
    enabled: seriesId != null,
    staleTime: extractProgress !== null ? 0 : 30_000,
    // Fallback poll while extraction is running (covers edge cases like reconnects)
    refetchInterval: extractProgress !== null ? 2_000 : false,
  })
  const sidecarMap: Record<string, SidecarSubtitle[]> = useMemo(() => sidecarData?.subtitles ?? {}, [sidecarData])

  // WebSocket: batch extraction progress
  useWebSocket({
    onBatchExtractProgress: (data) => {
      const d = data as { series_id: number; current: number; total: number; filename: string; status: string }
      if (d.series_id !== seriesId) return
      setExtractProgress({ current: d.current, total: d.total, filename: d.filename })
      if (d.status === 'ok') {
        void queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
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
      toast(msg, d.failed > 0 ? 'error' : 'success')
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

  // Fansub override indicator
  const { data: fansubPrefs } = useSeriesFansubPrefs(seriesId ?? -1)
  const hasFansubOverride = seriesId !== null && (
    (fansubPrefs?.preferred_groups.length ?? 0) > 0 ||
    (fansubPrefs?.excluded_groups.length ?? 0) > 0
  )

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

  const handleAutoSync = useCallback((subtitlePath: string, videoPath: string) => {
    toast('Auto-syncing…', 'info')
    void autoSyncFile(subtitlePath, videoPath).then(() => {
      toast('Auto-sync gestartet')
    }).catch((err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Auto-sync fehlgeschlagen'
      toast(msg, 'error')
    })
  }, [])

  const handleVideoSync = useCallback((ep: EpisodeInfo, subtitlePath: string) => {
    setVideoSyncEp({ ep, subtitlePath })
  }, [])

  const handleHealthCheck = useCallback((filePath: string) => {
    setHealthCheckPath(filePath)
  }, [])

  const handleExtract = useCallback(() => {
    if (seriesId == null || extractProgress !== null) return
    setExtractProgress({ current: 0, total: 0, filename: '' })
    batchExtractAllTracks(seriesId).catch((err: unknown) => {
      setExtractProgress(null)
      const msg = err instanceof Error ? err.message : 'Extraktion fehlgeschlagen'
      toast(msg, 'error')
    })
  }, [seriesId, extractProgress])

  const handlePreview = useCallback((ep: EpisodeInfo) => {
    const epSidecars = sidecarMap[String(ep.id)] ?? []
    const tracks: PlayerSubtitleTrack[] = epSidecars
      .filter((s) => s.format === 'ass' || s.format === 'srt' || s.format === 'vtt')
      .map((s) => ({
        path: s.path,
        language: s.language,
        format: s.format as 'ass' | 'srt' | 'vtt',
        label: `${s.language.toUpperCase()} — ${s.format.toUpperCase()}`,
      }))
    setPlayerState({ videoPath: ep.file_path, tracks })
  }, [sidecarMap])

  const handleDeleteSidecar = useCallback((path: string): Promise<void> => {
    setDeleteAlsoBlacklist(false)
    setDeleteConfirm(path)
    return Promise.resolve()
  }, [])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteConfirm) return
    const path = deleteConfirm
    setDeleteConfirm(null)
    try {
      await deleteSubtitles([path], deleteAlsoBlacklist)
      if (deleteAlsoBlacklist) {
        toast('Untertitel gelöscht und gesperrt', 'success')
        queryClient.invalidateQueries({ queryKey: ['blacklist'] })
      } else {
        toast('Sidecar gelöscht')
      }
      await queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
    } catch {
      toast('Löschen fehlgeschlagen', 'error')
    }
  }, [deleteConfirm, deleteAlsoBlacklist, queryClient, seriesId])

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
      {/* Breadcrumb navigation */}
      <div className="flex items-center justify-between">
        <Breadcrumb items={[{ label: 'Library', href: '/library' }, { label: series.title }]} />
        {/* Hidden back button for tests */}
        <button
          data-testid="series-back-btn"
          onClick={() => navigate('/library')}
          className="sr-only"
          aria-hidden="true"
        >
          <ArrowLeft size={14} />
          Back to Library
        </button>
      </div>

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

        <div className="relative flex gap-6 p-5">
          {/* Poster */}
          <div
            className="flex-shrink-0 rounded-lg overflow-hidden shadow-lg relative"
            style={{ width: '180px', minWidth: '180px', aspectRatio: '2/3', border: '1px solid var(--border)' }}
          >
            {series.poster ? (
              <img
                src={series.poster}
                alt={series.title}
                className="w-full h-full object-cover"
              />
            ) : (
              <div
                className="w-full h-full flex items-center justify-center"
                style={{ backgroundColor: 'var(--bg-surface)' }}
              >
                <FileVideo size={32} style={{ color: 'var(--text-muted)' }} />
              </div>
            )}
            {/* Score overlay gradient */}
            <div
              className="absolute bottom-0 left-0 right-0"
              style={{ height: '60%', background: 'linear-gradient(to top, rgba(19,21,25,0.9), transparent)' }}
            />
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0 flex flex-col gap-3">
            <div className="flex items-center gap-2.5">
              <h1 data-testid="series-title" style={{ fontSize: '24px', fontWeight: 700, letterSpacing: '-0.5px' }}>{series.title}</h1>
              {series.year && (
                <span className="text-sm" style={{ color: 'var(--text-muted)', fontWeight: 400 }}>{series.year}</span>
              )}
            </div>

            {/* Stat boxes */}
            {(() => {
              const withSubs = series.episodes?.filter(
                (ep) => ep.has_file && series.target_languages.some(
                  (lang) => { const f = ep.subtitles[lang]; return f != null && f !== '' }
                )
              ).length ?? 0
              const totalEps = series.episode_file_count
              return (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
                  {[
                    { label: 'Episodes', value: totalEps, color: 'var(--accent)' },
                    { label: 'With Subs', value: withSubs, color: 'var(--success)' },
                    { label: 'Missing', value: missingCount, color: missingCount > 0 ? 'var(--error)' : 'var(--success)' },
                    { label: 'Low Score', value: 0, color: 'var(--upgrade)' },
                  ].map(({ label, value, color }) => (
                    <div
                      key={label}
                      className="flex flex-col items-center text-center"
                      style={{
                        backgroundColor: 'var(--bg-surface)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-md)',
                        padding: '10px 14px',
                      }}
                    >
                      <span style={{ fontSize: '20px', fontWeight: 700, color, fontFamily: 'var(--font-mono)' }} className="tabular-nums">
                        {value}
                      </span>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.3px', marginTop: '2px' }}>
                        {label}
                      </span>
                    </div>
                  ))}
                </div>
              )
            })()}

            {/* Meta tags — pill-shaped with bg-elevated */}
            <div className="flex flex-wrap gap-1.5" style={{ marginBottom: '4px' }}>
              <span
                className="inline-flex items-center gap-1.5"
                style={{ padding: '3px 10px', borderRadius: '6px', background: 'var(--bg-elevated)', border: '1px solid var(--border)', fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}
              >
                <Folder size={11} />
                {series.path}
              </span>
              <span
                className="inline-flex items-center gap-1.5"
                style={{ padding: '3px 10px', borderRadius: '6px', background: 'var(--bg-elevated)', border: '1px solid var(--border)', fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}
              >
                <FileVideo size={11} />
                {t('series_detail.files', { count: series.episode_file_count })}
              </span>
              <span
                className="inline-flex items-center gap-1.5"
                style={{
                  padding: '3px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 500,
                  backgroundColor: missingCount > 0 ? 'var(--warning-bg)' : 'var(--success-bg)',
                  color: missingCount > 0 ? 'var(--warning)' : 'var(--success)',
                  border: '1px solid transparent',
                }}
              >
                <AlertTriangle size={11} />
                {t('series_detail.missing_subtitles', { count: missingCount })}
              </span>
              <span
                className="inline-flex items-center gap-1.5"
                style={{ padding: '3px 10px', borderRadius: '6px', background: 'var(--bg-elevated)', border: '1px solid var(--border)', fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}
              >
                <Play size={11} />
                {series.status === 'continuing' ? t('series_detail.continuing') : series.status === 'ended' ? t('series_detail.ended') : series.status}
              </span>
              {series.tags.length > 0 && (
                <span
                  className="inline-flex items-center gap-1.5"
                  style={{ padding: '3px 10px', borderRadius: '6px', background: 'var(--bg-elevated)', border: '1px solid var(--border)', fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}
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
              {seriesId != null && (
                <SeriesAudioTrackPicker
                  seriesId={seriesId}
                  episodes={series.episodes ?? []}
                />
              )}

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
                onClick={() => handleExtract()}
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

              {/* Fansub override button */}
              {seriesId !== null && (
                <button
                  onClick={() => setFansubOpen(true)}
                  title="Fansub Preferences"
                  style={{
                    background: 'transparent',
                    border: `1px solid ${hasFansubOverride ? 'var(--accent)' : 'var(--border)'}`,
                    color: hasFansubOverride ? 'var(--accent)' : 'var(--text-muted)',
                    borderRadius: 4, padding: '4px 10px', fontSize: 12, cursor: 'pointer',
                    fontWeight: hasFansubOverride ? 600 : 400,
                  }}
                >
                  Fansub
                </button>
              )}

              {/* Export ZIP */}
              <a
                href={getSeriesSubtitleExportUrl(series.id)}
                download
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded bg-neutral-700 hover:bg-neutral-600 text-neutral-200 transition-colors"
                title="Download all subtitles for this series as ZIP"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-4 w-4"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                    clipRule="evenodd"
                  />
                </svg>
                Export ZIP
              </a>

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

      {/* Processing Override Panel */}
      {seriesId !== null && (
        <SeriesProcessingOverride
          seriesId={seriesId}
          initialConfig={(series as { processing_config?: Record<string, boolean | null> })?.processing_config ?? {}}
        />
      )}

      {/* Episode Table */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ border: '1px solid var(--border)' }}
      >
        {/* Table Header */}
        <div
          className="flex items-center px-4"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            borderBottom: '1px solid var(--border)',
            padding: '6px 14px',
          }}
        >
          <div className="w-6 flex-shrink-0" />
          <div className="w-5 flex-shrink-0" />
          <div
            className="w-12 flex-shrink-0"
            style={{ color: 'var(--text-muted)', fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}
          >
            {t('series_detail.ep')}
          </div>
          <div
            className="flex-1"
            style={{ color: 'var(--text-muted)', fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}
          >
            {t('series_detail.title_col')}
          </div>
          <div
            className="w-24 flex-shrink-0"
            style={{ color: 'var(--text-muted)', fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}
          >
            {t('series_detail.audio')}
          </div>
          <div
            className="flex-1 min-w-[200px]"
            style={{ color: 'var(--text-muted)', fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}
          >
            {t('series_detail.subtitles')}
          </div>
          <div
            className="w-64 flex-shrink-0 text-right"
            style={{ color: 'var(--text-muted)', fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}
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
                {extractProgress.total === 0
                  ? 'Extraktion wird gestartet…'
                  : `Extrahiere Tracks — ${extractProgress.current} / ${extractProgress.total} Episoden`}
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
            <ProgressBar value={extractProgress.total === 0 ? 0 : extractProgress.current} max={extractProgress.total === 0 ? 100 : extractProgress.total} showLabel={false} />
          </div>
        )}

        {/* Season Groups */}
        {seasonGroups.map(([season, episodes]) => (
          <div key={season}>
            <SeasonSummaryBar
              season={season}
              episodes={episodes}
              targetLanguages={series.target_languages}
            />
          <SeasonGroup
            season={season}
            episodes={episodes}
            targetLanguages={series.target_languages}
            seriesId={seriesId}
            isExtracting={extractProgress !== null}
            onExtract={handleExtract}
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
            onPreview={handlePreview}
            streamingEnabled={streamingEnabled ?? false}
            onRefreshSidecars={() => queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })}
            t={t}
          />
          </div>
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

      {/* Delete Sidecar Confirmation Dialog */}
      {deleteConfirm && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setDeleteConfirm(null) }}
        >
          <div
            className="w-full max-w-sm mx-4 rounded-xl p-5 space-y-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <Trash2 size={16} style={{ color: 'var(--error)' }} />
                <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                  Untertitel löschen
                </h3>
              </div>
              <button
                onClick={() => setDeleteConfirm(null)}
                className="p-1 rounded"
                style={{ color: 'var(--text-muted)' }}
              >
                <X size={14} />
              </button>
            </div>

            <div
              className="text-xs px-2 py-1.5 rounded truncate"
              style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
              title={deleteConfirm}
            >
              {deleteConfirm.split('/').pop() ?? deleteConfirm}
            </div>

            <label className="flex items-center gap-2 cursor-pointer text-sm select-none" style={{ color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={deleteAlsoBlacklist}
                onChange={(e) => setDeleteAlsoBlacklist(e.target.checked)}
                className="rounded"
              />
              Auch zur Sperrliste hinzufügen
            </label>

            <div className="flex gap-2 justify-end pt-1">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-3 py-1.5 rounded-md text-sm transition-colors"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
              >
                Abbrechen
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="px-3 py-1.5 rounded-md text-sm font-medium transition-colors"
                style={{ backgroundColor: 'var(--error)', color: 'white' }}
              >
                Löschen
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Subtitle Editor Modal */}
      {editorFilePath && (
        <SubtitleEditorModal
          filePath={editorFilePath}
          initialMode={editorMode}
          onClose={() => setEditorFilePath(null)}
          onSeekRequest={playerState ? (seconds) => seekFnRef.current?.(seconds) : undefined}
        />
      )}

      {/* Comparison Selector Modal */}
      {compareSelectorEp && series && createPortal(
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
        </div>,
        document.body
      )}

      {/* Comparison View Modal */}
      {comparisonPaths && createPortal(
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
        </div>,
        document.body
      )}

      {/* Sync Controls Modal */}
      {syncFilePath && createPortal(
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
        </div>,
        document.body
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

      {/* Web Player Modal */}
      {playerState && (
        <PlayerModal
          videoPath={playerState.videoPath}
          subtitleTracks={playerState.tracks}
          onClose={() => setPlayerState(null)}
          onSeekReady={(fn) => { seekFnRef.current = fn }}
        />
      )}

      {/* Health Check Panel Modal */}
      {healthCheckPath && createPortal(
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
        </div>,
        document.body
      )}

      {seriesId !== null && (
        <FansubOverrideModal
          seriesId={seriesId}
          open={fansubOpen}
          onClose={() => setFansubOpen(false)}
        />
      )}
    </div>
  )
}
