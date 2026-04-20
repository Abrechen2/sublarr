import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Plus, Edit2, Trash2, Check, X, BookOpen, Search, Download } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import {
  useGlobalGlossaryEntries, useCreateGlossaryEntry, useUpdateGlossaryEntry, useDeleteGlossaryEntry,
  useExportGlossaryTsv, useConfig, useUpdateConfig,
} from '@/hooks/useApi'

// ─── Global Glossary Panel ──────────────────────────────────────────────────

  const { t } = useTranslation('settings')
  const { data, isLoading } = useGlobalGlossaryEntries()
  const createEntry = useCreateGlossaryEntry()
  const updateEntry = useUpdateGlossaryEntry()
  const deleteEntry = useDeleteGlossaryEntry()
  const exportTsv = useExportGlossaryTsv()
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
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

  const glossaryEnabled = config
    ? (config as Record<string, unknown>)['glossary_enabled'] !== 'false'
    : true
  const glossaryMaxTerms = config
    ? Number((config as Record<string, unknown>)['glossary_max_terms'] ?? 20)
    : 20
  const [localMaxTerms, setLocalMaxTerms] = useState<number>(glossaryMaxTerms)
  useEffect(() => { setLocalMaxTerms(glossaryMaxTerms) }, [glossaryMaxTerms])

  const handleGlossaryEnabledChange = (value: boolean) => {
    updateConfig.mutate(
      { glossary_enabled: String(value) },
      {
        onSuccess: () => toast('Glossary setting saved'),
        onError: () => toast('Failed to save setting', 'error'),
      },
    )
  }

  const handleMaxTermsBlur = () => {
    const clamped = Math.max(1, Math.min(200, Math.round(localMaxTerms)))
    if (clamped !== glossaryMaxTerms) {
      updateConfig.mutate(
        { glossary_max_terms: String(clamped) },
        {
          onSuccess: () => toast('Max glossary terms saved'),
          onError: () => toast('Failed to save setting', 'error'),
        },
      )
    }
  }

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
        { entryId: editingId, series_id: null, ...formData },
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
        { series_id: null, ...formData },
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
      { entryId: id, seriesId: null },
      {
        onSuccess: () => toast('Entry deleted'),
        onError: () => toast('Failed to delete entry', 'error'),
      }
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen size={16} style={{ color: 'var(--accent)' }} />
          <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            Global Glossary
          </h2>
          <span
            className="px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
          >
            {entries.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {entries.length > 0 && (
            <button
              onClick={() => exportTsv.mutate({ seriesId: null })}
              disabled={exportTsv.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
              style={{
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'var(--bg-primary)',
              }}
              data-testid="glossary-export-btn"
            >
              {exportTsv.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Download size={12} />
              )}
              Export TSV
            </button>
          )}
          <button
            onClick={() => {
              resetForm()
              setShowAdd(true)
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white"
            style={{ backgroundColor: 'var(--accent)' }}
            data-testid="glossary-add-btn"
          >
            <Plus size={12} />
            Add Entry
          </button>
        </div>
      </div>

      {/* Glossary Settings */}
      <div
        className="rounded-lg p-4 space-y-3"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <SettingRow
          label={t('glossary_page.title')}
          helpText="Inject per-series glossary terms into LLM translation prompts for consistent proper noun handling."
        >
          <Toggle
            checked={glossaryEnabled}
            onChange={handleGlossaryEnabledChange}
            disabled={updateConfig.isPending}
          />
        </SettingRow>
        <SettingRow
          label={t('glossary_page.max_terms')}
          helpText="Maximum number of glossary terms injected per translation request."
          advanced
        >
          <input
            data-testid="input-glossary_max_terms"
            type="number"
            min={1}
            max={200}
            step={1}
            value={localMaxTerms}
            disabled={!glossaryEnabled || updateConfig.isPending}
            onChange={(e) => {
              const parsed = parseInt(e.target.value, 10)
              if (!isNaN(parsed)) setLocalMaxTerms(parsed)
            }}
            onBlur={handleMaxTermsBlur}
            className="w-24 px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontSize: '13px',
              opacity: glossaryEnabled ? 1 : 0.5,
            }}
          />
        </SettingRow>
      </div>

      {/* Search */}
      {entries.length > 0 && (
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder={t('glossary_page.search_placeholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-md text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </div>
      )}

      {/* Add/Edit Form */}
      {(showAdd || editingId !== null) && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? 'Edit Entry' : 'New Global Entry'}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
                Source Term
              </label>
              <input
                type="text"
                placeholder={t('glossary_page.term_placeholder')}
                value={formData.source_term}
                onChange={(e) => setFormData((f) => ({ ...f, source_term: e.target.value }))}
                className="w-full px-3 py-2 rounded-md text-sm"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
                Target Term
              </label>
              <input
                type="text"
                placeholder={t('glossary_page.term_placeholder')}
                value={formData.target_term}
                onChange={(e) => setFormData((f) => ({ ...f, target_term: e.target.value }))}
                className="w-full px-3 py-2 rounded-md text-sm"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
              Notes (optional)
            </label>
            <input
              type="text"
              placeholder={t('glossary_page.notes_placeholder')}
              value={formData.notes}
              onChange={(e) => setFormData((f) => ({ ...f, notes: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={createEntry.isPending || updateEntry.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {(createEntry.isPending || updateEntry.isPending) ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Check size={12} />
              )}
              Save
            </button>
            <button onClick={resetForm} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
              <X size={12} /> Cancel
            </button>
          </div>
        </div>
      )}

      {/* Entries List */}
      {filteredEntries.length === 0 ? (
        <div
          className="rounded-lg p-6 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <BookOpen size={24} className="mx-auto mb-2" style={{ color: 'var(--text-muted)', opacity: 0.5 }} />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {searchQuery
              ? 'No entries match your search.'
              : 'No global glossary entries. Add terms that should be consistently translated across all series.'}
          </p>
        </div>
      ) : (
        <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
          <table className="w-full">
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-2" style={{ color: 'var(--text-muted)' }}>{t('glossary_page.col_source')}</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-2" style={{ color: 'var(--text-muted)' }}>{t('glossary_page.col_target')}</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-2" style={{ color: 'var(--text-muted)' }}>{t('glossary_page.col_notes')}</th>
                <th className="text-right text-[10px] font-semibold uppercase tracking-wider px-3 py-2" style={{ color: 'var(--text-muted)' }}>{t('glossary_page.col_actions')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredEntries.map((entry, i) => (
                <tr
                  key={entry.id}
                  style={{ borderBottom: i < filteredEntries.length - 1 ? '1px solid var(--border)' : undefined }}
                >
                  <td className="px-3 py-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {entry.source_term}
                  </td>
                  <td className="px-3 py-2 text-sm font-medium" style={{ color: 'var(--accent)' }}>
                    {entry.target_term}
                  </td>
                  <td className="px-3 py-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                    {entry.notes || '-'}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1 justify-end">
                      <button
                        onClick={() => startEdit(entry)}
                        className="p-1.5 rounded transition-all duration-150"
                        style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
                        title={t('glossary_page.edit_entry')}
                      >
                        <Edit2 size={12} />
                      </button>
                      <button
                        onClick={() => handleDelete(entry.id)}
                        disabled={deleteEntry.isPending}
                        className="p-1.5 rounded transition-all duration-150"
                        style={{ border: '1px solid var(--border)', color: 'var(--error)', backgroundColor: 'var(--bg-primary)' }}
                        title={t('glossary_page.delete_entry')}
                      >
                        <Trash2 size={12} />
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
