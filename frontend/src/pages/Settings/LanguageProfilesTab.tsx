import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useLanguageProfiles,
  useCreateProfile,
  useUpdateProfile,
  useDeleteProfile,
  useSetProfileAsDefaultForAll,
} from '@/hooks/useApi'
import {
  Loader2,
  Trash2,
  Plus,
  Edit2,
  X,
  Check,
  Globe,
  Star,
} from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import type { LanguageProfile } from '@/lib/types'
import { LanguagePillSelector } from '@/components/settings/LanguagePillSelector'
import { LANGUAGE_OPTIONS } from '@/styles/settingsShared'

function getLangLabel(code: string): string {
  return LANGUAGE_OPTIONS.find((o) => o.value === code)?.label ?? code
}

// ─── Language Profiles Tab ────────────────────────────────────────────────────

export function LanguageProfilesTab() {
  const { t: _t } = useTranslation('settings')
  const { data: profiles, isLoading } = useLanguageProfiles()
  const createProfile = useCreateProfile()
  const updateProfile = useUpdateProfile()
  const deleteProfile = useDeleteProfile()
  const setAsDefaultForAll = useSetProfileAsDefaultForAll()
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({
    name: '',
    target_languages: [] as string[],
    forced_preference: 'disabled' as 'disabled' | 'separate' | 'auto',
    forced_scoring: 'include' as 'include' | 'prefer' | 'exclude' | 'only',
    hi_preference: 'include' as 'include' | 'prefer' | 'exclude' | 'only',
    cutoff_language: '',
  })

  const resetForm = () => {
    setForm({ name: '', target_languages: [], forced_preference: 'disabled', forced_scoring: 'include', hi_preference: 'include', cutoff_language: '' })
    setEditingId(null)
    setShowAdd(false)
  }

  const startEdit = (p: LanguageProfile) => {
    setForm({
      name: p.name,
      target_languages: p.target_languages,
      forced_preference: p.forced_preference || 'disabled',
      forced_scoring: p.forced_scoring || 'include',
      hi_preference: p.hi_preference || 'include',
      cutoff_language: p.cutoff_language || '',
    })
    setEditingId(p.id)
    setShowAdd(false)
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
      target_languages: targetLangs,
      target_language_names: targetNames,
      forced_preference: form.forced_preference,
      forced_scoring: form.forced_scoring,
      hi_preference: form.hi_preference,
      cutoff_language: form.cutoff_language,
    }

    if (editingId) {
      updateProfile.mutate({ id: editingId, data: payload }, {
        onSuccess: () => { toast('Profil gespeichert'); resetForm() },
        onError: () => toast('Profil konnte nicht gespeichert werden', 'error'),
      })
    } else {
      createProfile.mutate(payload as Omit<LanguageProfile, 'id' | 'is_default'>, {
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
          onClick={() => { setShowAdd(true); setEditingId(null); setForm({ name: '', target_languages: [], forced_preference: 'disabled', forced_scoring: 'include', hi_preference: 'include', cutoff_language: '' }) }}
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

            {/* Profile name */}
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Profilname</label>
              <input
                type="text" value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="z.B. Deutsch"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              />
            </div>

            {/* Target languages */}
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
                onChange={(langs) => setForm((f) => ({
                  ...f,
                  target_languages: langs,
                  // reset cutoff if the selected language was removed
                  cutoff_language: langs.includes(f.cutoff_language) ? f.cutoff_language : '',
                }))}
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

            {/* Forced Subtitles Scoring */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Forced-Untertitel Wertung</label>
              <select
                value={form.forced_scoring}
                onChange={(e) => setForm((f) => ({ ...f, forced_scoring: e.target.value as 'include' | 'prefer' | 'exclude' | 'only' }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="include">Einschließen</option>
                <option value="prefer">Bevorzugen</option>
                <option value="exclude">Ausschließen</option>
                <option value="only">Nur Forced</option>
              </select>
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {form.forced_scoring === 'include' && 'Forced-Untertitel werden gleichwertig bewertet'}
                {form.forced_scoring === 'prefer' && 'Forced-Untertitel erhalten +30 Punkte beim Scoring'}
                {form.forced_scoring === 'exclude' && 'Forced-Untertitel werden beim Scoring auf -999 gesetzt'}
                {form.forced_scoring === 'only' && 'Nur Forced-Untertitel werden akzeptiert (normale auf -999)'}
              </p>
            </div>

            {/* HI Subtitles Preference */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Hörgeschädigten-Untertitel (HI)</label>
              <select
                value={form.hi_preference}
                onChange={(e) => setForm((f) => ({ ...f, hi_preference: e.target.value as 'include' | 'prefer' | 'exclude' | 'only' }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="include">Einschließen</option>
                <option value="prefer">Bevorzugen</option>
                <option value="exclude">Ausschließen</option>
                <option value="only">Nur HI</option>
              </select>
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {form.hi_preference === 'include' && 'HI-Untertitel werden gleichwertig eingeschlossen'}
                {form.hi_preference === 'prefer' && 'HI-Untertitel werden bevorzugt, falls verfügbar'}
                {form.hi_preference === 'exclude' && 'HI-Untertitel werden übersprungen'}
                {form.hi_preference === 'only' && 'Nur HI-Untertitel werden akzeptiert'}
              </p>
            </div>

            {/* Cutoff Language */}
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                Cutoff-Sprache
              </label>
              <select
                value={form.cutoff_language}
                onChange={(e) => setForm((f) => ({ ...f, cutoff_language: e.target.value }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                disabled={form.target_languages.length === 0}
              >
                <option value="">Keine — alle Sprachen immer suchen</option>
                {form.target_languages.map((lang) => {
                  const label = LANGUAGE_OPTIONS.find((o) => o.value === lang)?.label ?? lang
                  return (
                    <option key={lang} value={lang}>{label}</option>
                  )
                })}
              </select>
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {form.cutoff_language
                  ? `Sobald ein ${LANGUAGE_OPTIONS.find((o) => o.value === form.cutoff_language)?.label ?? form.cutoff_language}-Untertitel vorhanden ist, werden keine weiteren Sprachen gesucht.`
                  : 'Sublarr sucht Untertitel für alle Zielsprachen — unabhängig davon, was bereits vorhanden ist.'}
              </p>
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
              {!p.is_default && (
                <button
                  onClick={() => {
                    setAsDefaultForAll.mutate(p.id, {
                      onSuccess: () => toast(`"${p.name}" als Standard für alle aktiviert`),
                      onError: () => toast('Standard konnte nicht gesetzt werden', 'error'),
                    })
                  }}
                  disabled={setAsDefaultForAll.isPending}
                  className="flex items-center gap-1 px-2 py-1 rounded text-xs transition-all duration-150"
                  style={{ border: '1px solid var(--accent-dim)', color: 'var(--accent)', backgroundColor: 'var(--accent-bg)' }}
                  title="Als Standard für alle bestehenden und neuen Serien/Filme aktivieren"
                >
                  <Star size={11} />
                  Als Standard
                </button>
              )}
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

          {/* Target languages */}
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

          {/* Subtitle preferences summary */}
          <div className="flex items-center gap-4 flex-wrap text-xs" style={{ color: 'var(--text-secondary)' }}>
            {p.forced_preference && p.forced_preference !== 'disabled' && (
              <span>
                Erzwungen: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.forced_preference}</code>
              </span>
            )}
            {p.forced_scoring && p.forced_scoring !== 'include' && (
              <span>
                Forced-Wertung: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.forced_scoring}</code>
              </span>
            )}
            {p.hi_preference && p.hi_preference !== 'include' && (
              <span>
                HI: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.hi_preference}</code>
              </span>
            )}
            {p.cutoff_language && (
              <span>
                Cutoff: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
                  {LANGUAGE_OPTIONS.find((o) => o.value === p.cutoff_language)?.label ?? p.cutoff_language}
                </code>
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
