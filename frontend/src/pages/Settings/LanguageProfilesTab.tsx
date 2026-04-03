import { useState } from 'react'
import {
  useLanguageProfiles,
  useCreateProfile,
  useUpdateProfile,
  useDeleteProfile,
  useBackends,
} from '@/hooks/useApi'
import {
  Loader2,
  Trash2,
  Plus,
  Edit2,
  X,
  Check,
  Globe,
} from 'lucide-react'
import { ChevronUp, ChevronDown } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import type { LanguageProfile } from '@/lib/types'

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
