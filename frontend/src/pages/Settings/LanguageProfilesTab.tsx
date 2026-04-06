import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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
import { LanguagePillSelector } from '@/components/settings/LanguagePillSelector'

const LANGUAGE_OPTIONS = [
  { value: 'de', label: 'Deutsch' },
  { value: 'en', label: 'English' },
  { value: 'fr', label: 'Français' },
  { value: 'ja', label: 'Japanese' },
  { value: 'es', label: 'Español' },
  { value: 'it', label: 'Italiano' },
  { value: 'pt', label: 'Português' },
  { value: 'nl', label: 'Nederlands' },
  { value: 'pl', label: 'Polski' },
  { value: 'ru', label: 'Русский' },
  { value: 'ko', label: '한국어' },
  { value: 'zh', label: '中文' },
  { value: 'ar', label: 'العربية' },
  { value: 'tr', label: 'Türkçe' },
  { value: 'sv', label: 'Svenska' },
  { value: 'da', label: 'Dansk' },
  { value: 'fi', label: 'Suomi' },
  { value: 'no', label: 'Norsk' },
  { value: 'cs', label: 'Čeština' },
  { value: 'hu', label: 'Magyar' },
] as const

function getLangLabel(code: string): string {
  return LANGUAGE_OPTIONS.find((o) => o.value === code)?.label ?? code
}

// ─── Language Profiles Tab ────────────────────────────────────────────────────

export function LanguageProfilesTab() {
  const { t } = useTranslation('settings')
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
    target_languages: [] as string[],
    translation_backend: '',
    fallback_chain: [] as string[],
    forced_preference: 'disabled' as 'disabled' | 'separate' | 'auto',
  })

  const backends = backendsData?.backends ?? []

  const resetForm = () => {
    setForm({ name: '', source_language: 'en', source_language_name: 'English', target_languages: [], translation_backend: '', fallback_chain: [], forced_preference: 'disabled' })
    setEditingId(null)
    setShowAdd(false)
  }

  const startEdit = (p: LanguageProfile) => {
    setForm({
      name: p.name,
      source_language: p.source_language,
      source_language_name: p.source_language_name,
      target_languages: p.target_languages,
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
    const targetLangs = form.target_languages
    const targetNames = targetLangs.map(getLangLabel)
    if (!form.name || targetLangs.length === 0) {
      toast('Profilname und mindestens eine Zielsprache erforderlich', 'error')
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
        onSuccess: () => { toast('Profil gespeichert'); resetForm() },
        onError: () => toast('Profil konnte nicht gespeichert werden', 'error'),
      })
    } else {
      createProfile.mutate(payload, {
        onSuccess: () => { toast('Profil erstellt'); resetForm() },
        onError: () => toast('Profil konnte nicht erstellt werden', 'error'),
      })
    }
  }

  const handleDelete = (id: number) => {
    deleteProfile.mutate(id, {
      onSuccess: () => toast('Profil gelöscht'),
      onError: () => toast('Standard-Profil kann nicht gelöscht werden', 'error'),
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
          Sprachprofile legen fest, welche Untertitelsprachen pro Serie/Film gesucht werden.
        </span>
        <button
          onClick={() => { setShowAdd(true); setEditingId(null); setForm({ name: '', source_language: 'en', source_language_name: 'English', target_languages: [], translation_backend: '', fallback_chain: [], forced_preference: 'disabled' }) }}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
          style={{ border: '1px solid var(--accent-dim)', color: 'var(--accent)', backgroundColor: 'var(--accent-bg)' }}
        >
          <Plus size={12} />
          Profil hinzufügen
        </button>
      </div>

      {/* Add/Edit Form */}
      {(showAdd || editingId !== null) && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? 'Profil bearbeiten' : 'Neues Profil'}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Profilname</label>
              <input
                type="text" value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="z.B. Deutsch"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                Originalsprache des Mediums
                <span className="ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: 'rgba(245,158,11,0.12)', color: 'var(--warning, #f59e0b)', border: '1px solid rgba(245,158,11,0.3)' }}>
                  Erweitert
                </span>
              </label>
              <select
                value={form.source_language}
                onChange={(e) => {
                  const opt = LANGUAGE_OPTIONS.find((o) => o.value === e.target.value)
                  setForm((f) => ({ ...f, source_language: e.target.value, source_language_name: opt?.label ?? e.target.value }))
                }}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                {LANGUAGE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                Sprache des Originals (z.B. Japanisch für Anime). Nur ändern wenn nötig.
              </p>
            </div>
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                Zielsprachen
                <span className="ml-1.5 text-[10px] font-normal" style={{ color: 'var(--text-muted)' }}>
                  1. = Primär · 2. = Fallback · 3. = weiterer Fallback
                </span>
              </label>
              <LanguagePillSelector
                value={form.target_languages}
                options={LANGUAGE_OPTIONS}
                onChange={(langs) => setForm((f) => ({ ...f, target_languages: langs }))}
                placeholder="— Sprache hinzufügen —"
              />
              <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                Sublarr sucht Untertitel in dieser Reihenfolge. Die erste verfügbare Sprache wird verwendet.
              </p>
            </div>

            {/* Forced Subtitles Preference */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Erzwungene Untertitel</label>
              <select
                value={form.forced_preference}
                onChange={(e) => setForm((f) => ({ ...f, forced_preference: e.target.value as 'disabled' | 'separate' | 'auto' }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="disabled">Deaktiviert</option>
                <option value="separate">Separat suchen</option>
                <option value="auto">Automatisch erkennen</option>
              </select>
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {form.forced_preference === 'disabled' && 'Forced/Signs-Untertitel werden ignoriert'}
                {form.forced_preference === 'separate' && 'Forced-Untertitel werden aktiv gesucht und separat verwaltet'}
                {form.forced_preference === 'auto' && 'Forced-Untertitel werden erkannt wenn vorhanden, aber nicht aktiv gesucht'}
              </p>
            </div>

            {/* Translation Backend Selector */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Übersetzungs-Backend</label>
              <select
                value={form.translation_backend}
                onChange={(e) => setForm((f) => ({ ...f, translation_backend: e.target.value }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="">Standard (Ollama)</option>
                {backends.map((b) => (
                  <option key={b.name} value={b.name}>{b.display_name}</option>
                ))}
              </select>
            </div>

            {/* Fallback Chain Editor */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                Backend-Fallback-Kette
                <span className="ml-1.5 text-[10px] font-normal" style={{ color: 'var(--text-muted)' }}>(Übersetzung)</span>
              </label>
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
                          {isPrimary && ' (primär)'}
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
                    Keine Fallback-Kette konfiguriert.
                  </span>
                )}
                {backends.filter((b) => !form.fallback_chain.includes(b.name)).length > 0 && (
                  <select
                    value=""
                    onChange={(e) => { handleFallbackAdd(e.target.value); e.target.value = '' }}
                    className="w-full px-2.5 py-1 rounded text-xs"
                    style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
                  >
                    <option value="">+ Backend zur Fallback-Kette hinzufügen...</option>
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
              Speichern
            </button>
            <button onClick={resetForm} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
              <X size={12} /> Abbrechen
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
                  Standard
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
            <span>Original: <code style={{ fontFamily: 'var(--font-mono)' }}>{p.source_language}</code> ({p.source_language_name})</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Zielsprachen:</span>
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
                Übersetzung: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.translation_backend}</code>
              </span>
            )}
            {p.fallback_chain && p.fallback_chain.length > 0 && (
              <span>
                Fallback-Kette: <code style={{ fontFamily: 'var(--font-mono)' }}>{p.fallback_chain.join(' > ')}</code>
              </span>
            )}
            {p.forced_preference && p.forced_preference !== 'disabled' && (
              <span>
                Erzwungen: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.forced_preference}</code>
              </span>
            )}
          </div>
        </div>
      ))}

      {(!profiles || profiles.length === 0) && !showAdd && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          Keine Sprachprofile konfiguriert. Ein Standard-Profil wird automatisch erstellt.
        </div>
      )}
    </div>
  )
}
