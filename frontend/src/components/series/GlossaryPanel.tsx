import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Edit2, Trash2, Check, X, Download, Loader2, Wand2 } from 'lucide-react'
import { useGlossaryEntries, useCreateGlossaryEntry, useUpdateGlossaryEntry, useDeleteGlossaryEntry, useSuggestGlossaryTerms, useExportGlossaryTsv } from '@/hooks/useApi'
import type { GlossaryCandidate } from '@/api/client'
import { toast } from '@/components/shared/Toast'

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

export interface GlossaryPanelProps {
  readonly seriesId: number
}

export function GlossaryPanel({ seriesId }: GlossaryPanelProps) {
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
