import { useState, useRef } from 'react'
import {
  useLanguageProfiles, useCreateProfile, useUpdateProfile, useDeleteProfile,
  useBackends,
  useWatchedFolders, useSaveWatchedFolder, useDeleteWatchedFolder,
  useTriggerStandaloneScan, useStandaloneStatus,
  useFullBackups, useCreateFullBackup, useRestoreFullBackup,
  useSubtitleTool, usePreviewSubtitle,
} from '@/hooks/useApi'
import { Save, Loader2, Trash2, Plus, Edit2, X, Check, Globe, Upload, Download, Eye, FolderOpen, RefreshCw, RotateCcw, HardDrive, AlertTriangle, Wrench } from 'lucide-react'
import { ChevronUp, ChevronDown } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { downloadFullBackupUrl } from '@/api/client'
import type { LanguageProfile, WatchedFolder, FullBackupInfo } from '@/lib/types'
import type { FieldConfig } from './index'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'

// ─── Language Profiles Tab ────────────────────────────────────────────────────

export function LanguageProfilesTab() {
  const { data: profiles, isLoading } = useLanguageProfiles()
  const { data: backendsData } = useBackends()
  const createProfile = useCreateProfile()
  const updateProfile = useUpdateProfile()
  const deleteProfile = useDeleteProfile()
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({
    name: '',
    source_language: 'en',
    source_language_name: 'English',
    target_languages: '',
    target_language_names: '',
    translation_backend: '',
    fallback_chain: [] as string[],
    forced_preference: 'disabled' as 'disabled' | 'separate' | 'auto',
  })

  const backends = backendsData?.backends ?? []

  const resetForm = () => {
    setForm({ name: '', source_language: 'en', source_language_name: 'English', target_languages: '', target_language_names: '', translation_backend: '', fallback_chain: [], forced_preference: 'disabled' })
    setEditingId(null)
    setShowAdd(false)
  }

  const startEdit = (p: LanguageProfile) => {
    setForm({
      name: p.name,
      source_language: p.source_language,
      source_language_name: p.source_language_name,
      target_languages: p.target_languages.join(', '),
      target_language_names: p.target_language_names.join(', '),
      translation_backend: p.translation_backend || '',
      fallback_chain: p.fallback_chain || [],
      forced_preference: p.forced_preference || 'disabled',
    })
    setEditingId(p.id)
    setShowAdd(false)
  }

  const handleFallbackMove = (index: number, direction: 'up' | 'down') => {
    const chain = [...form.fallback_chain]
    const swapIdx = direction === 'up' ? index - 1 : index + 1
    if (swapIdx < 0 || swapIdx >= chain.length) return
    ;[chain[index], chain[swapIdx]] = [chain[swapIdx], chain[index]]
    setForm((f) => ({ ...f, fallback_chain: chain }))
  }

  const handleFallbackRemove = (index: number) => {
    setForm((f) => ({ ...f, fallback_chain: f.fallback_chain.filter((_, i) => i !== index) }))
  }

  const handleFallbackAdd = (name: string) => {
    if (!name || form.fallback_chain.includes(name)) return
    setForm((f) => ({ ...f, fallback_chain: [...f.fallback_chain, name] }))
  }

  const handleSave = () => {
    const targetLangs = form.target_languages.split(',').map((s) => s.trim()).filter(Boolean)
    const targetNames = form.target_language_names.split(',').map((s) => s.trim()).filter(Boolean)
    if (!form.name || targetLangs.length === 0) {
      toast('Name and at least one target language required', 'error')
      return
    }
    if (targetLangs.length !== targetNames.length) {
      toast('Target language codes and names must have the same count', 'error')
      return
    }

    const payload = {
      name: form.name,
      source_language: form.source_language,
      source_language_name: form.source_language_name,
      target_languages: targetLangs,
      target_language_names: targetNames,
      translation_backend: form.translation_backend || '',
      fallback_chain: form.fallback_chain,
      forced_preference: form.forced_preference,
    }

    if (editingId) {
      updateProfile.mutate({ id: editingId, data: payload }, {
        onSuccess: () => { toast('Profile updated'); resetForm() },
        onError: () => toast('Failed to update profile', 'error'),
      })
    } else {
      createProfile.mutate(payload, {
        onSuccess: () => { toast('Profile created'); resetForm() },
        onError: () => toast('Failed to create profile', 'error'),
      })
    }
  }

  const handleDelete = (id: number) => {
    deleteProfile.mutate(id, {
      onSuccess: () => toast('Profile deleted'),
      onError: () => toast('Cannot delete default profile', 'error'),
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          Language profiles define which languages to translate for each series/movie
        </span>
        <button
          onClick={() => { setShowAdd(true); setEditingId(null); setForm({ name: '', source_language: 'en', source_language_name: 'English', target_languages: '', target_language_names: '', translation_backend: '', fallback_chain: [], forced_preference: 'disabled' }) }}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
          style={{ border: '1px solid var(--accent-dim)', color: 'var(--accent)', backgroundColor: 'var(--accent-bg)' }}
        >
          <Plus size={12} />
          Add Profile
        </button>
      </div>

      {/* Add/Edit Form */}
      {(showAdd || editingId !== null) && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? 'Edit Profile' : 'New Profile'}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Name</label>
              <input
                type="text" value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. German Only"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Source Language Code</label>
              <input
                type="text" value={form.source_language}
                onChange={(e) => setForm((f) => ({ ...f, source_language: e.target.value }))}
                placeholder="en"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Source Language Name</label>
              <input
                type="text" value={form.source_language_name}
                onChange={(e) => setForm((f) => ({ ...f, source_language_name: e.target.value }))}
                placeholder="English"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Target Language Codes (comma-separated)</label>
              <input
                type="text" value={form.target_languages}
                onChange={(e) => setForm((f) => ({ ...f, target_languages: e.target.value }))}
                placeholder="de, fr"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
              />
            </div>
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Target Language Names (comma-separated, same order)</label>
              <input
                type="text" value={form.target_language_names}
                onChange={(e) => setForm((f) => ({ ...f, target_language_names: e.target.value }))}
                placeholder="German, French"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              />
            </div>

            {/* Forced Subtitles Preference */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Forced Subtitles</label>
              <select
                value={form.forced_preference}
                onChange={(e) => setForm((f) => ({ ...f, forced_preference: e.target.value as 'disabled' | 'separate' | 'auto' }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="disabled">Disabled</option>
                <option value="separate">Separate</option>
                <option value="auto">Auto</option>
              </select>
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {form.forced_preference === 'disabled' && 'Do not manage forced/signs subtitles'}
                {form.forced_preference === 'separate' && 'Actively search and track forced subtitles separately'}
                {form.forced_preference === 'auto' && 'Detect forced subtitles if found, but don\'t actively search'}
              </p>
            </div>

            {/* Translation Backend Selector */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Translation Backend</label>
              <select
                value={form.translation_backend}
                onChange={(e) => setForm((f) => ({ ...f, translation_backend: e.target.value }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="">Default (Ollama)</option>
                {backends.map((b) => (
                  <option key={b.name} value={b.name}>{b.display_name}</option>
                ))}
              </select>
            </div>

            {/* Fallback Chain Editor */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Fallback Chain</label>
              <div className="space-y-1.5">
                {form.fallback_chain.length > 0 ? (
                  form.fallback_chain.map((name, idx) => {
                    const isPrimary = name === form.translation_backend
                    return (
                      <div key={name} className="flex items-center gap-1.5">
                        <span
                          className="flex-1 px-2 py-1 rounded text-xs"
                          style={{
                            backgroundColor: 'var(--bg-primary)',
                            border: '1px solid var(--border)',
                            color: isPrimary ? 'var(--accent)' : 'var(--text-primary)',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          {idx + 1}. {backends.find((b) => b.name === name)?.display_name || name}
                          {isPrimary && ' (primary)'}
                        </span>
                        <button
                          onClick={() => handleFallbackMove(idx, 'up')}
                          disabled={idx === 0}
                          className="p-1 rounded"
                          style={{ color: idx === 0 ? 'var(--text-muted)' : 'var(--text-secondary)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-primary)' }}
                        >
                          <ChevronUp size={10} />
                        </button>
                        <button
                          onClick={() => handleFallbackMove(idx, 'down')}
                          disabled={idx === form.fallback_chain.length - 1}
                          className="p-1 rounded"
                          style={{ color: idx === form.fallback_chain.length - 1 ? 'var(--text-muted)' : 'var(--text-secondary)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-primary)' }}
                        >
                          <ChevronDown size={10} />
                        </button>
                        {!isPrimary && (
                          <button
                            onClick={() => handleFallbackRemove(idx)}
                            className="p-1 rounded"
                            style={{ color: 'var(--error)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-primary)' }}
                          >
                            <X size={10} />
                          </button>
                        )}
                      </div>
                    )
                  })
                ) : (
                  <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    No fallback chain configured. Add backends below.
                  </span>
                )}
                {/* Add backend to chain */}
                {backends.filter((b) => !form.fallback_chain.includes(b.name)).length > 0 && (
                  <select
                    value=""
                    onChange={(e) => { handleFallbackAdd(e.target.value); e.target.value = '' }}
                    className="w-full px-2.5 py-1 rounded text-xs"
                    style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
                  >
                    <option value="">+ Add backend to fallback chain...</option>
                    {backends
                      .filter((b) => !form.fallback_chain.includes(b.name))
                      .map((b) => (
                        <option key={b.name} value={b.name}>{b.display_name}</option>
                      ))}
                  </select>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={handleSave}
              disabled={createProfile.isPending || updateProfile.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {(createProfile.isPending || updateProfile.isPending) ? (
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

      {/* Profile List */}
      {(profiles || []).map((p) => (
        <div
          key={p.id}
          className="rounded-lg p-4 space-y-2"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Globe size={14} style={{ color: 'var(--accent)' }} />
              <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{p.name}</span>
              {p.is_default && (
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                  style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                >
                  Default
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => startEdit(p)}
                className="p-1.5 rounded transition-all duration-150"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
                title="Edit profile"
              >
                <Edit2 size={12} />
              </button>
              {!p.is_default && (
                <button
                  onClick={() => handleDelete(p.id)}
                  disabled={deleteProfile.isPending}
                  className="p-1.5 rounded transition-all duration-150"
                  style={{ border: '1px solid var(--border)', color: 'var(--error)', backgroundColor: 'var(--bg-primary)' }}
                  title="Delete profile"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <span>Source: <code style={{ fontFamily: 'var(--font-mono)' }}>{p.source_language}</code> ({p.source_language_name})</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Targets:</span>
            {p.target_languages.map((lang, i) => (
              <span
                key={lang}
                className="px-2 py-0.5 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}
              >
                {lang.toUpperCase()} ({p.target_language_names[i]})
              </span>
            ))}
          </div>
          {/* Translation backend info */}
          <div className="flex items-center gap-4 flex-wrap text-xs" style={{ color: 'var(--text-secondary)' }}>
            {p.translation_backend && (
              <span>
                Backend: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.translation_backend}</code>
              </span>
            )}
            {p.fallback_chain && p.fallback_chain.length > 0 && (
              <span>
                Fallback: <code style={{ fontFamily: 'var(--font-mono)' }}>{p.fallback_chain.join(' > ')}</code>
              </span>
            )}
            {p.forced_preference && p.forced_preference !== 'disabled' && (
              <span>
                Forced: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.forced_preference}</code>
              </span>
            )}
          </div>
        </div>
      ))}

      {(!profiles || profiles.length === 0) && !showAdd && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          No language profiles configured. A default profile will be created automatically.
        </div>
      )}
    </div>
  )
}

// ─── Library Sources Tab (Standalone Mode) ──────────────────────────────────

export function LibrarySourcesTab({
  values,
  onFieldChange,
  fields,
}: {
  values: Record<string, string>
  onFieldChange: (key: string, value: string) => void
  fields: FieldConfig[]
}) {
  const { data: folders, isLoading: foldersLoading } = useWatchedFolders()
  const saveFolder = useSaveWatchedFolder()
  const removeFolder = useDeleteWatchedFolder()
  const scanAll = useTriggerStandaloneScan()
  const { data: standaloneStatus } = useStandaloneStatus()
  const [showAdd, setShowAdd] = useState(false)
  const [newPath, setNewPath] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newMediaType, setNewMediaType] = useState<'auto' | 'tv' | 'movie'>('auto')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editPath, setEditPath] = useState('')
  const [editLabel, setEditLabel] = useState('')
  const [editMediaType, setEditMediaType] = useState<'auto' | 'tv' | 'movie'>('auto')

  const tabFields = fields.filter((f) => f.tab === 'Library Sources')

  const handleAddFolder = () => {
    if (!newPath.trim()) return
    saveFolder.mutate(
      { path: newPath.trim(), label: newLabel.trim(), media_type: newMediaType, enabled: true },
      {
        onSuccess: () => {
          setNewPath('')
          setNewLabel('')
          setNewMediaType('auto')
          setShowAdd(false)
          toast('Folder added')
        },
        onError: () => toast('Failed to add folder', 'error'),
      },
    )
  }

  const handleEditFolder = (folder: WatchedFolder) => {
    setEditingId(folder.id)
    setEditPath(folder.path)
    setEditLabel(folder.label)
    setEditMediaType(folder.media_type)
  }

  const handleSaveEdit = () => {
    if (!editingId || !editPath.trim()) return
    saveFolder.mutate(
      { id: editingId, path: editPath.trim(), label: editLabel.trim(), media_type: editMediaType },
      {
        onSuccess: () => {
          setEditingId(null)
          toast('Folder updated')
        },
        onError: () => toast('Failed to update folder', 'error'),
      },
    )
  }

  const handleToggleEnabled = (folder: WatchedFolder) => {
    saveFolder.mutate(
      { id: folder.id, path: folder.path, enabled: !folder.enabled },
    )
  }

  const handleDelete = (folderId: number) => {
    removeFolder.mutate(folderId, {
      onSuccess: () => toast('Folder removed'),
      onError: () => toast('Failed to remove folder', 'error'),
    })
  }

  const handleScanAll = () => {
    scanAll.mutate(undefined, {
      onSuccess: () => toast('Scan started'),
      onError: () => toast('Failed to start scan', 'error'),
    })
  }

  const selectStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontSize: '13px',
  }

  return (
    <div
      className="rounded-lg p-5 space-y-5"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      {/* Config fields — SettingRow handles advanced/showAdvanced filtering internally */}
      {tabFields.map((field) => (
        <SettingRow
          key={field.key}
          label={field.label}
          description={field.description}
          advanced={field.advanced}
        >
          {field.type === 'toggle' ? (
            <Toggle
              checked={values[field.key] === 'true'}
              onChange={(v) => onFieldChange(field.key, String(v))}
            />
          ) : (
            <input
              type={field.type}
              value={values[field.key] === '***configured***' ? '' : (values[field.key] ?? '')}
              onChange={(e) => onFieldChange(field.key, e.target.value)}
              placeholder={values[field.key] === '***configured***' ? '(configured -- enter new value to change)' : field.placeholder}
              className="w-full px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: field.type === 'text' ? 'var(--font-mono)' : undefined,
                fontSize: '13px',
              }}
            />
          )}
        </SettingRow>
      ))}

      {/* Watched Folders section */}
      <div className="pt-4 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FolderOpen size={16} style={{ color: 'var(--accent)' }} />
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              Watched Folders
            </h3>
            {standaloneStatus && (
              <span
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium"
                style={{
                  backgroundColor: standaloneStatus.watcher_running ? 'var(--success-bg)' : 'rgba(124,130,147,0.08)',
                  color: standaloneStatus.watcher_running ? 'var(--success)' : 'var(--text-muted)',
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: standaloneStatus.watcher_running ? 'var(--success)' : 'var(--text-muted)' }}
                />
                {standaloneStatus.watcher_running ? 'Watching' : 'Stopped'}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleScanAll}
              disabled={scanAll.isPending}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
              style={{
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'var(--bg-primary)',
              }}
              title="Scan all folders"
            >
              {scanAll.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <RefreshCw size={12} />
              )}
              Scan All
            </button>
            <button
              onClick={() => setShowAdd(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
              style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
            >
              <Plus size={12} />
              Add Folder
            </button>
          </div>
        </div>

        {/* Folder list */}
        {foldersLoading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
          </div>
        ) : (
          <div className="space-y-2">
            {folders && folders.length > 0 ? (
              folders.map((folder) => (
                <div
                  key={folder.id}
                  className="rounded-lg p-3 space-y-2"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    opacity: folder.enabled ? 1 : 0.6,
                  }}
                >
                  {editingId === folder.id ? (
                    /* Edit mode */
                    <div className="space-y-2">
                      <input
                        type="text"
                        value={editPath}
                        onChange={(e) => setEditPath(e.target.value)}
                        placeholder="/path/to/media"
                        className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
                        style={{
                          backgroundColor: 'var(--bg-surface)',
                          border: '1px solid var(--border)',
                          color: 'var(--text-primary)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '13px',
                        }}
                      />
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={editLabel}
                          onChange={(e) => setEditLabel(e.target.value)}
                          placeholder="Label (optional)"
                          className="flex-1 px-2.5 py-1.5 rounded text-sm focus:outline-none"
                          style={{
                            backgroundColor: 'var(--bg-surface)',
                            border: '1px solid var(--border)',
                            color: 'var(--text-primary)',
                            fontSize: '13px',
                          }}
                        />
                        <select
                          value={editMediaType}
                          onChange={(e) => setEditMediaType(e.target.value as 'auto' | 'tv' | 'movie')}
                          className="px-2.5 py-1.5 rounded text-sm focus:outline-none"
                          style={selectStyle}
                        >
                          <option value="auto">Auto</option>
                          <option value="tv">TV</option>
                          <option value="movie">Movie</option>
                        </select>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleSaveEdit}
                          disabled={saveFolder.isPending}
                          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-white"
                          style={{ backgroundColor: 'var(--accent)' }}
                        >
                          {saveFolder.isPending ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
                          Save
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          <X size={10} />
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Display mode */
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className="text-sm truncate"
                            style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }}
                            title={folder.path}
                          >
                            {folder.path}
                          </span>
                          <span
                            className="px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0"
                            style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                          >
                            {folder.media_type}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                          {folder.label && <span>{folder.label}</span>}
                          {folder.last_scan_at && (
                            <span>Last scan: {new Date(folder.last_scan_at).toLocaleString()}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          onClick={() => handleToggleEnabled(folder)}
                          className="px-2 py-1 rounded text-[10px] font-medium transition-all duration-150"
                          style={{
                            backgroundColor: folder.enabled ? 'var(--accent-bg)' : 'var(--bg-surface)',
                            color: folder.enabled ? 'var(--accent)' : 'var(--text-muted)',
                            border: '1px solid ' + (folder.enabled ? 'var(--accent-dim)' : 'var(--border)'),
                          }}
                        >
                          {folder.enabled ? 'Enabled' : 'Disabled'}
                        </button>
                        <button
                          onClick={() => handleEditFolder(folder)}
                          className="p-1.5 rounded transition-all duration-150"
                          style={{ color: 'var(--text-muted)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
                          title="Edit folder"
                        >
                          <Edit2 size={12} />
                        </button>
                        <button
                          onClick={() => handleDelete(folder.id)}
                          className="p-1.5 rounded transition-all duration-150"
                          style={{ color: 'var(--text-muted)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
                          title="Remove folder"
                          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-center py-4 text-xs" style={{ color: 'var(--text-muted)' }}>
                No watched folders configured. Add a folder to start scanning for media.
              </div>
            )}
          </div>
        )}

        {/* Add folder form */}
        {showAdd && (
          <div
            className="rounded-lg p-3 space-y-2"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--accent-dim)' }}
          >
            <input
              type="text"
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              placeholder="/path/to/media"
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
              }}
              autoFocus
            />
            <div className="flex gap-2">
              <input
                type="text"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder="Label (optional)"
                className="flex-1 px-2.5 py-1.5 rounded text-sm focus:outline-none"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontSize: '13px',
                }}
              />
              <select
                value={newMediaType}
                onChange={(e) => setNewMediaType(e.target.value as 'auto' | 'tv' | 'movie')}
                className="px-2.5 py-1.5 rounded text-sm focus:outline-none"
                style={selectStyle}
              >
                <option value="auto">Auto</option>
                <option value="tv">TV</option>
                <option value="movie">Movie</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleAddFolder}
                disabled={saveFolder.isPending || !newPath.trim()}
                className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-white"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {saveFolder.isPending ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
                Save
              </button>
              <button
                onClick={() => { setShowAdd(false); setNewPath(''); setNewLabel(''); setNewMediaType('auto') }}
                className="flex items-center gap-1 px-2.5 py-1 rounded text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                <X size={10} />
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Backup Tab ──────────────────────────────────────────────────────────────

export function BackupTab() {
  const { data: backupsData, isLoading } = useFullBackups()
  const createBackup = useCreateFullBackup()
  const restoreBackup = useRestoreFullBackup()
  const [restoreFile, setRestoreFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-'
    const d = new Date(dateStr)
    return d.toLocaleString()
  }

  const handleCreate = () => {
    createBackup.mutate(undefined, {
      onSuccess: (data) => {
        toast(`Backup created: ${data.filename}`)
      },
      onError: () => toast('Failed to create backup', 'error'),
    })
  }

  const handleRestoreFromFile = () => {
    if (!restoreFile) return
    restoreBackup.mutate(restoreFile, {
      onSuccess: (result) => {
        const imported = result.config_imported?.length || 0
        toast(`Restored: ${imported} config keys, DB ${result.db_restored ? 'restored' : 'skipped'}`)
        setRestoreFile(null)
      },
      onError: () => toast('Restore failed', 'error'),
    })
  }

  const backups = backupsData?.backups || []

  return (
    <div className="space-y-4">
      {/* Create Backup */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          Create Full Backup
        </h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          Creates a ZIP archive containing the database and configuration.
        </p>
        <button
          onClick={handleCreate}
          disabled={createBackup.isPending}
          className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {createBackup.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <HardDrive size={14} />
          )}
          {createBackup.isPending ? 'Creating...' : 'Create Backup'}
        </button>
      </div>

      {/* Backup List */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          Existing Backups
        </h3>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
          </div>
        ) : backups.length === 0 ? (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            No backups found. Create one above.
          </p>
        ) : (
          <div className="space-y-2">
            {backups.map((backup: FullBackupInfo) => (
              <div
                key={backup.filename}
                className="flex items-center justify-between px-3 py-2 rounded-md"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              >
                <div>
                  <div className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                    {backup.filename}
                  </div>
                  <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    {formatSize(backup.size_bytes)} &middot; {formatDate(backup.created_at)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href={downloadFullBackupUrl(backup.filename)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-all"
                    style={{
                      border: '1px solid var(--border)',
                      color: 'var(--text-secondary)',
                      backgroundColor: 'var(--bg-surface)',
                    }}
                  >
                    <Download size={12} />
                    Download
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Restore from File */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          Restore from File
        </h3>
        <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--warning)' }}>
          <AlertTriangle size={14} />
          <span className="text-xs">API keys will need to be re-entered after restore.</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            <Upload size={14} />
            Select ZIP File
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            onChange={(e) => setRestoreFile(e.target.files?.[0] || null)}
            className="hidden"
          />
          {restoreFile && (
            <>
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {restoreFile.name}
              </span>
              <button
                onClick={handleRestoreFromFile}
                disabled={restoreBackup.isPending}
                className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {restoreBackup.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <RotateCcw size={12} />
                )}
                Restore
              </button>
            </>
          )}
        </div>
      </div>

      {/* Auto-Backup Info */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          Automatic Backups
        </h3>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          The built-in database backup scheduler runs daily and manages retention automatically.
          Configure retention settings in General tab (backup_retention_daily, backup_retention_weekly, backup_retention_monthly).
        </p>
      </div>
    </div>
  )
}

// ─── Subtitle Tools Tab ──────────────────────────────────────────────────────

function highlightLine(line: string, format: string): string {
  if (format === 'ass') {
    if (line.startsWith('[') || line.startsWith('Format:') || line.startsWith('Style:')) return 'var(--accent)'
    if (line.startsWith('Dialogue:') || line.startsWith('Comment:')) return 'var(--text-primary)'
    return 'var(--text-muted)'
  }
  // SRT
  if (/^\d+$/.test(line.trim())) return 'var(--accent)'
  if (/-->/.test(line)) return 'var(--text-muted)'
  return 'var(--text-primary)'
}

export function SubtitleToolsTab() {
  const subtitleTool = useSubtitleTool()
  const previewMutation = usePreviewSubtitle()
  const [hiPath, setHiPath] = useState('')
  const [timingPath, setTimingPath] = useState('')
  const [timingOffset, setTimingOffset] = useState(0)
  const [fixesPath, setFixesPath] = useState('')
  const [fixes, setFixes] = useState({ encoding: true, whitespace: true, linebreaks: true, empty_lines: true })
  const [previewPath, setPreviewPath] = useState('')
  const [previewData, setPreviewData] = useState<{ format: string; lines: string[]; total_lines: number } | null>(null)
  const [toolResult, setToolResult] = useState<Record<string, string | null>>({})

  const runTool = (tool: string, params: Record<string, unknown>, resultKey: string) => {
    subtitleTool.mutate({ tool, params }, {
      onSuccess: (data) => {
        setToolResult((prev) => ({ ...prev, [resultKey]: data.status || 'Done' }))
        toast(`Tool "${tool}" completed successfully`)
      },
      onError: () => {
        setToolResult((prev) => ({ ...prev, [resultKey]: 'Failed' }))
        toast(`Tool "${tool}" failed`, 'error')
      },
    })
  }

  const handlePreview = () => {
    if (!previewPath.trim()) return
    previewMutation.mutate(previewPath, {
      onSuccess: (data) => setPreviewData(data),
      onError: () => toast('Preview failed', 'error'),
    })
  }

  return (
    <div className="space-y-4">
      <div className="text-xs px-1" style={{ color: 'var(--text-muted)' }}>
        <AlertTriangle size={12} className="inline mr-1" />
        A backup (.bak) is created before any modification.
      </div>

      {/* Remove HI Markers */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          Remove Hearing-Impaired Markers
        </h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          Removes [HI], (music), and other hearing-impaired annotations from subtitle files.
        </p>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={hiPath}
            onChange={(e) => setHiPath(e.target.value)}
            placeholder="File path (e.g. /media/show/sub.srt)"
            className="flex-1 px-3 py-2 rounded-md text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
            }}
          />
          <button
            onClick={() => runTool('remove-hi', { file_path: hiPath }, 'hi')}
            disabled={!hiPath.trim() || subtitleTool.isPending}
            className="flex items-center gap-1 px-3 py-2 rounded-md text-sm font-medium text-white shrink-0"
            style={{ backgroundColor: 'var(--accent)', opacity: !hiPath.trim() ? 0.5 : 1 }}
          >
            {subtitleTool.isPending ? <Loader2 size={14} className="animate-spin" /> : <Wrench size={14} />}
            Remove
          </button>
        </div>
        {toolResult.hi && (
          <p className="text-xs mt-2" style={{ color: toolResult.hi === 'Failed' ? 'var(--error)' : 'var(--success)' }}>
            Result: {toolResult.hi}
          </p>
        )}
      </div>

      {/* Adjust Timing */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          Adjust Timing
        </h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          Shift all subtitle timestamps by a specified millisecond offset.
          Positive values delay, negative values advance.
        </p>
        <div className="flex items-center gap-2">
          <input type="text" value={timingPath} onChange={(e) => setTimingPath(e.target.value)} placeholder="File path"
            className="flex-1 px-3 py-2 rounded-md text-sm"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }} />
          <div className="flex items-center gap-1">
            <input type="number" value={timingOffset} onChange={(e) => setTimingOffset(parseInt(e.target.value) || 0)}
              className="w-24 px-2 py-2 rounded-md text-sm text-center"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }} />
            <span className="text-xs shrink-0" style={{ color: 'var(--text-muted)' }}>ms ({timingOffset >= 0 ? 'delay' : 'advance'})</span>
          </div>
          <button
            onClick={() => runTool('adjust-timing', { file_path: timingPath, offset_ms: timingOffset }, 'timing')}
            disabled={!timingPath.trim() || subtitleTool.isPending}
            className="flex items-center gap-1 px-3 py-2 rounded-md text-sm font-medium text-white shrink-0"
            style={{ backgroundColor: 'var(--accent)', opacity: !timingPath.trim() ? 0.5 : 1 }}
          >
            {subtitleTool.isPending ? <Loader2 size={14} className="animate-spin" /> : <Wrench size={14} />}
            Apply
          </button>
        </div>
        {toolResult.timing && (
          <p className="text-xs mt-2" style={{ color: toolResult.timing === 'Failed' ? 'var(--error)' : 'var(--success)' }}>Result: {toolResult.timing}</p>
        )}
      </div>

      {/* Common Fixes */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>Common Fixes</h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          Apply common subtitle cleaning operations: fix encoding, trim whitespace, normalize line breaks, remove empty lines.
        </p>
        <div className="flex items-center gap-2 mb-3">
          <input type="text" value={fixesPath} onChange={(e) => setFixesPath(e.target.value)} placeholder="File path"
            className="flex-1 px-3 py-2 rounded-md text-sm"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }} />
        </div>
        <div className="flex flex-wrap gap-3 mb-3">
          {(['encoding', 'whitespace', 'linebreaks', 'empty_lines'] as const).map((fix) => (
            <label key={fix} className="flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={fixes[fix]} onChange={(e) => setFixes((prev) => ({ ...prev, [fix]: e.target.checked }))}
                className="rounded" style={{ accentColor: 'var(--accent)' }} />
              {fix.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
            </label>
          ))}
        </div>
        <button
          onClick={() => runTool('common-fixes', { file_path: fixesPath, fixes }, 'fixes')}
          disabled={!fixesPath.trim() || subtitleTool.isPending}
          className="flex items-center gap-1 px-3 py-2 rounded-md text-sm font-medium text-white"
          style={{ backgroundColor: 'var(--accent)', opacity: !fixesPath.trim() ? 0.5 : 1 }}
        >
          {subtitleTool.isPending ? <Loader2 size={14} className="animate-spin" /> : <Wrench size={14} />}
          Apply Fixes
        </button>
        {toolResult.fixes && (
          <p className="text-xs mt-2" style={{ color: toolResult.fixes === 'Failed' ? 'var(--error)' : 'var(--success)' }}>Result: {toolResult.fixes}</p>
        )}
      </div>

      {/* Preview */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>Preview Subtitle</h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>View the first 100 lines of a subtitle file.</p>
        <div className="flex items-center gap-2 mb-3">
          <input type="text" value={previewPath} onChange={(e) => setPreviewPath(e.target.value)} placeholder="File path"
            className="flex-1 px-3 py-2 rounded-md text-sm"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }} />
          <button
            onClick={handlePreview}
            disabled={!previewPath.trim() || previewMutation.isPending}
            className="flex items-center gap-1 px-3 py-2 rounded-md text-sm font-medium text-white shrink-0"
            style={{ backgroundColor: 'var(--accent)', opacity: !previewPath.trim() ? 0.5 : 1 }}
          >
            {previewMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Eye size={14} />}
            Preview
          </button>
        </div>
        {previewData && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-medium px-2 py-0.5 rounded" style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}>
                {previewData.format.toUpperCase()}
              </span>
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{previewData.total_lines} total lines</span>
            </div>
            <div
              className="max-h-64 overflow-auto rounded p-3 text-xs"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', fontFamily: 'var(--font-mono)', lineHeight: 1.6 }}
            >
              {previewData.lines.map((line, i) => (
                <div key={i} style={{ color: highlightLine(line, previewData.format) }}>{line || '\u00A0'}</div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
