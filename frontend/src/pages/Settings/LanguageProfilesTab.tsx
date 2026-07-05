import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useLanguageProfiles,
  useCreateProfile,
  useUpdateProfile,
  useDeleteProfile,
  useSetProfileAsDefaultForAll,
  useBackends,
} from '@/hooks/useApi'
import { BackendSelect } from '@/components/settings/BackendSelect'
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

type CombineVertical = 'top' | 'middle' | 'bottom'

const EMPTY_FORM = {
  name: '',
  target_languages: [] as string[],
  forced_preference: 'disabled' as 'disabled' | 'separate' | 'auto',
  forced_scoring: 'include' as 'include' | 'prefer' | 'exclude' | 'only',
  hi_preference: 'include' as 'include' | 'prefer' | 'exclude' | 'only',
  cutoff_language: '',
  translation_backend: '',
  fallback_backend: '',
  mt_keep_seeking_original: false,
  mt_on_original_found: 'notify' as 'notify' | 'auto_replace',
  mt_min_original_score: 1,
  combine_enabled: false,
  combine_format: 'ass' as 'ass' | 'srt',
  combine_languages: [] as string[],
  combine_primary: 'bottom' as CombineVertical,
  combine_secondary: 'top' as CombineVertical,
}

// ─── Language Profiles Tab ────────────────────────────────────────────────────

export function LanguageProfilesTab() {
  const { t } = useTranslation('settings')
  const { data: profiles, isLoading } = useLanguageProfiles()
  const createProfile = useCreateProfile()
  const updateProfile = useUpdateProfile()
  const deleteProfile = useDeleteProfile()
  const setAsDefaultForAll = useSetProfileAsDefaultForAll()
  const { data: backendsData } = useBackends()
  const backends = backendsData?.backends ?? []
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_FORM })

  const resetForm = () => {
    setForm({ ...EMPTY_FORM })
    setEditingId(null)
    setShowAdd(false)
  }

  const startEdit = (p: LanguageProfile) => {
    setForm({
      ...EMPTY_FORM,
      name: p.name,
      target_languages: p.target_languages,
      forced_preference: p.forced_preference || 'disabled',
      forced_scoring: p.forced_scoring || 'include',
      hi_preference: p.hi_preference || 'include',
      cutoff_language: p.cutoff_language || '',
      translation_backend: p.translation_backend && p.translation_backend !== '' ? p.translation_backend : '',
      fallback_backend: (p.fallback_chain ?? []).filter((b) => b && b !== p.translation_backend)[0] ?? '',
      mt_keep_seeking_original: p.mt_keep_seeking_original ?? false,
      mt_on_original_found: p.mt_on_original_found ?? 'notify',
      mt_min_original_score: p.mt_min_original_score ?? 1,
      combine_enabled: p.combine_enabled ?? false,
      combine_format: p.combine_format ?? 'ass',
      combine_languages: p.combine_languages ?? [],
      combine_primary: p.combine_position?.primary ?? 'bottom',
      combine_secondary: p.combine_position?.secondary ?? 'top',
    })
    setEditingId(p.id)
    setShowAdd(false)
  }

  const handleSave = () => {
    const targetLangs = form.target_languages
    const targetNames = targetLangs.map(getLangLabel)
    if (!form.name || targetLangs.length === 0) {
      toast(t('language_profiles.name_and_lang_required'), 'error')
      return
    }

    const primary = form.translation_backend
    const fallback = primary ? form.fallback_backend : ''
    const fallback_chain = primary
      ? (fallback && fallback !== primary ? [primary, fallback] : [primary])
      : []

    // Combine languages are always a subset of the target languages.
    const combineLangs = form.combine_languages.filter((l) => targetLangs.includes(l))
    if (form.combine_enabled && combineLangs.length < 2) {
      toast(t('language_profiles.combine_languages_min'), 'error')
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
      translation_backend: primary,
      fallback_chain,
      mt_keep_seeking_original: form.mt_keep_seeking_original,
      mt_on_original_found: form.mt_on_original_found,
      mt_min_original_score: form.mt_min_original_score,
      combine_enabled: form.combine_enabled,
      combine_format: form.combine_format,
      combine_languages: combineLangs,
      combine_position: { primary: form.combine_primary, secondary: form.combine_secondary },
    }

    if (editingId) {
      updateProfile.mutate({ id: editingId, data: payload }, {
        onSuccess: () => { toast(t('language_profiles.saved')); resetForm() },
        onError: () => toast(t('language_profiles.save_failed'), 'error'),
      })
    } else {
      createProfile.mutate(payload as Omit<LanguageProfile, 'id' | 'is_default'>, {
        onSuccess: () => { toast(t('language_profiles.created')); resetForm() },
        onError: () => toast(t('language_profiles.create_failed'), 'error'),
      })
    }
  }

  const handleDelete = (id: number) => {
    deleteProfile.mutate(id, {
      onSuccess: () => toast(t('language_profiles.deleted')),
      onError: () => toast(t('language_profiles.delete_default_failed'), 'error'),
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
          {t('language_profiles.intro')}
        </span>
        <button
          onClick={() => {
            setShowAdd(true)
            setEditingId(null)
            setForm({ ...EMPTY_FORM })
          }}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
          style={{ border: '1px solid var(--accent-dim)', color: 'var(--accent)', backgroundColor: 'var(--accent-bg)' }}
        >
          <Plus size={12} />
          {t('language_profiles.add_profile')}
        </button>
      </div>

      {/* Add/Edit Form */}
      {(showAdd || editingId !== null) && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? t('language_profiles.edit_title') : t('language_profiles.new_title')}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">

            {/* Profile name */}
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{t('language_profiles.profile_name')}</label>
              <input
                type="text" value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder={t('language_profiles.profile_name_placeholder')}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              />
            </div>

            {/* Target languages */}
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                {t('language_profiles.target_languages')}
                <span className="ml-1.5 text-[10px] font-normal" style={{ color: 'var(--text-muted)' }}>
                  {t('language_profiles.target_languages_order')}
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
                placeholder={t('language_profiles.add_language')}
              />
              <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                {t('language_profiles.target_languages_help')}
              </p>
            </div>

            {/* Forced Subtitles Preference */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{t('language_profiles.forced_subtitles')}</label>
              <select
                value={form.forced_preference}
                onChange={(e) => setForm((f) => ({ ...f, forced_preference: e.target.value as 'disabled' | 'separate' | 'auto' }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="disabled">{t('language_profiles.forced_disabled')}</option>
                <option value="separate">{t('language_profiles.forced_separate')}</option>
                <option value="auto">{t('language_profiles.forced_auto_detect')}</option>
              </select>
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {form.forced_preference === 'disabled' && t('language_profiles.forced_pref_disabled_desc')}
                {form.forced_preference === 'separate' && t('language_profiles.forced_pref_separate_desc')}
                {form.forced_preference === 'auto' && t('language_profiles.forced_pref_auto_desc')}
              </p>
            </div>

            {/* Forced Subtitles Scoring */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{t('language_profiles.forced_scoring')}</label>
              <select
                value={form.forced_scoring}
                onChange={(e) => setForm((f) => ({ ...f, forced_scoring: e.target.value as 'include' | 'prefer' | 'exclude' | 'only' }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="include">{t('language_profiles.include')}</option>
                <option value="prefer">{t('language_profiles.prefer')}</option>
                <option value="exclude">{t('language_profiles.exclude')}</option>
                <option value="only">{t('language_profiles.only_forced')}</option>
              </select>
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {form.forced_scoring === 'include' && t('language_profiles.forced_scoring_include_desc')}
                {form.forced_scoring === 'prefer' && t('language_profiles.forced_scoring_prefer_desc')}
                {form.forced_scoring === 'exclude' && t('language_profiles.forced_scoring_exclude_desc')}
                {form.forced_scoring === 'only' && t('language_profiles.forced_scoring_only_desc')}
              </p>
            </div>

            {/* HI Subtitles Preference */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{t('language_profiles.hi_subtitles')}</label>
              <select
                value={form.hi_preference}
                onChange={(e) => setForm((f) => ({ ...f, hi_preference: e.target.value as 'include' | 'prefer' | 'exclude' | 'only' }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="include">{t('language_profiles.include')}</option>
                <option value="prefer">{t('language_profiles.prefer')}</option>
                <option value="exclude">{t('language_profiles.exclude')}</option>
                <option value="only">{t('language_profiles.only_hi')}</option>
              </select>
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {form.hi_preference === 'include' && t('language_profiles.hi_pref_include_desc')}
                {form.hi_preference === 'prefer' && t('language_profiles.hi_pref_prefer_desc')}
                {form.hi_preference === 'exclude' && t('language_profiles.hi_pref_exclude_desc')}
                {form.hi_preference === 'only' && t('language_profiles.hi_pref_only_desc')}
              </p>
            </div>

            {/* Cutoff Language */}
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                {t('language_profiles.cutoff_language_label')}
              </label>
              <select
                value={form.cutoff_language}
                onChange={(e) => setForm((f) => ({ ...f, cutoff_language: e.target.value }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                disabled={form.target_languages.length === 0}
              >
                <option value="">{t('language_profiles.no_filter')}</option>
                {form.target_languages.map((lang) => {
                  const label = LANGUAGE_OPTIONS.find((o) => o.value === lang)?.label ?? lang
                  return (
                    <option key={lang} value={lang}>{label}</option>
                  )
                })}
              </select>
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {form.cutoff_language
                  ? t('language_profiles.cutoff_active_desc', { language: LANGUAGE_OPTIONS.find((o) => o.value === form.cutoff_language)?.label ?? form.cutoff_language })
                  : t('language_profiles.cutoff_inactive_desc')}
              </p>
            </div>

            {/* Translation Backend override */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-secondary">{t('language_profiles.translation_backend_label')}</label>
              <BackendSelect
                data-testid="profile-backend"
                value={form.translation_backend}
                backends={backends}
                inheritLabel={t('language_profiles.translation_backend_inherit')}
                unconfiguredLabel={t('language_profiles.translation_backend_unconfigured')}
                onChange={(name) => setForm((f) => ({ ...f, translation_backend: name, fallback_backend: name ? f.fallback_backend : '' }))}
              />
              <p className="text-[11px] text-muted">{t('language_profiles.translation_backend_help')}</p>
              {form.translation_backend &&
                form.translation_backend !== 'ollama' &&
                !backends.find((b) => b.name === form.translation_backend)?.configured && (
                  <p className="text-[11px]" style={{ color: 'var(--warning)' }}>
                    {t('language_profiles.translation_backend_unconfigured_warn')}
                  </p>
              )}
            </div>
            {form.translation_backend && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-secondary">{t('language_profiles.translation_backend_fallback')}</label>
                <BackendSelect
                  data-testid="profile-fallback"
                  value={form.fallback_backend}
                  backends={backends}
                  noneLabel={t('language_profiles.translation_backend_none')}
                  unconfiguredLabel={t('language_profiles.translation_backend_unconfigured')}
                  onChange={(name) => setForm((f) => ({ ...f, fallback_backend: name }))}
                />
              </div>
            )}

            {/* Provisional machine-translation (V1.6 #8) — keep the wanted item
                alive after an MT so a later pass can seek the human original. */}
            {form.translation_backend && (
              <div className="space-y-1 md:col-span-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    data-testid="profile-mt-keep-seeking"
                    checked={form.mt_keep_seeking_original}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, mt_keep_seeking_original: e.target.checked }))
                    }
                    style={{ accentColor: 'var(--accent)' }}
                  />
                  <span className="text-xs font-medium text-secondary">
                    {t('language_profiles.mt_keep_seeking_label')}
                  </span>
                </label>
                <p className="text-[11px] text-muted">
                  {t('language_profiles.mt_keep_seeking_help')}
                </p>

                {form.mt_keep_seeking_original && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pl-1 pt-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-secondary">
                        {t('language_profiles.mt_on_original_found_label')}
                      </label>
                      <select
                        data-testid="profile-mt-on-original-found"
                        value={form.mt_on_original_found}
                        onChange={(e) =>
                          setForm((f) => ({
                            ...f,
                            mt_on_original_found: e.target.value as 'notify' | 'auto_replace',
                          }))
                        }
                        className="w-full px-2.5 py-1.5 rounded text-xs bg-page border border-border text-foreground"
                      >
                        <option value="notify">{t('language_profiles.mt_on_original_found_notify')}</option>
                        <option value="auto_replace">{t('language_profiles.mt_on_original_found_auto_replace')}</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-secondary">
                        {t('language_profiles.mt_min_original_score_label')}
                      </label>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        data-testid="profile-mt-min-original-score"
                        value={form.mt_min_original_score}
                        onChange={(e) =>
                          setForm((f) => ({
                            ...f,
                            mt_min_original_score: Math.max(0, parseInt(e.target.value, 10) || 0),
                          }))
                        }
                        className="w-full px-2.5 py-1.5 rounded text-xs bg-page border border-border text-foreground"
                      />
                      <p className="text-[11px] text-muted">
                        {t('language_profiles.mt_min_original_score_help')}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Combined / bilingual subtitles (V1.6 #1) */}
            <div className="space-y-2 md:col-span-2 pt-1" style={{ borderTop: '1px solid var(--border)' }}>
              <label className="flex items-center gap-2 cursor-pointer pt-2">
                <input
                  type="checkbox"
                  checked={form.combine_enabled}
                  onChange={(e) => setForm((f) => ({ ...f, combine_enabled: e.target.checked }))}
                  style={{ accentColor: 'var(--accent)' }}
                />
                <span className="text-xs font-medium text-secondary">
                  {t('language_profiles.combine_title')} — {t('language_profiles.combine_enabled_label')}
                </span>
              </label>
              <p className="text-[11px] text-muted">{t('language_profiles.combine_enabled_help')}</p>

              {form.combine_enabled && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pl-1 pt-1">
                  {/* Format */}
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-secondary">{t('language_profiles.combine_format_label')}</label>
                    <select
                      value={form.combine_format}
                      onChange={(e) => setForm((f) => ({ ...f, combine_format: e.target.value as 'ass' | 'srt' }))}
                      className="w-full px-2.5 py-1.5 rounded text-xs"
                      style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                    >
                      <option value="ass">ASS</option>
                      <option value="srt">SRT</option>
                    </select>
                  </div>

                  {/* Languages to combine (subset of target languages) */}
                  <div className="space-y-1 md:col-span-2">
                    <label className="text-xs font-medium text-secondary">{t('language_profiles.combine_languages_label')}</label>
                    <LanguagePillSelector
                      value={form.combine_languages.filter((l) => form.target_languages.includes(l))}
                      options={form.target_languages.map((l) => ({ value: l, label: getLangLabel(l) }))}
                      onChange={(langs) => setForm((f) => ({ ...f, combine_languages: langs }))}
                    />
                    <p className="text-[11px] text-muted">{t('language_profiles.combine_languages_help')}</p>
                  </div>

                  {/* ASS positioning */}
                  {form.combine_format === 'ass' && (
                    <div className="space-y-1 md:col-span-2">
                      <label className="text-xs font-medium text-secondary">{t('language_profiles.combine_position_label')}</label>
                      <div className="flex flex-wrap gap-3">
                        {([
                          ['combine_primary', 'combine_position_primary', form.combine_primary] as const,
                          ['combine_secondary', 'combine_position_secondary', form.combine_secondary] as const,
                        ]).map(([field, labelKey, value]) => (
                          <div key={field} className="flex items-center gap-1.5">
                            <span className="text-[11px] text-muted">{t(`language_profiles.${labelKey}`)}</span>
                            <select
                              value={value}
                              onChange={(e) => setForm((f) => ({ ...f, [field]: e.target.value as CombineVertical }))}
                              className="px-2 py-1 rounded text-xs"
                              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                            >
                              <option value="top">{t('language_profiles.combine_position_top')}</option>
                              <option value="middle">{t('language_profiles.combine_position_middle')}</option>
                              <option value="bottom">{t('language_profiles.combine_position_bottom')}</option>
                            </select>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
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
              {t('language_profiles.save')}
            </button>
            <button onClick={resetForm} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
              <X size={12} /> {t('language_profiles.cancel')}
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
                  {t('language_profiles.default_badge')}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              {!p.is_default && (
                <button
                  onClick={() => {
                    setAsDefaultForAll.mutate(p.id, {
                      onSuccess: () => toast(t('language_profiles.set_default_success', { name: p.name })),
                      onError: () => toast(t('language_profiles.set_default_failed'), 'error'),
                    })
                  }}
                  disabled={setAsDefaultForAll.isPending}
                  className="flex items-center gap-1 px-2 py-1 rounded text-xs transition-all duration-150"
                  style={{ border: '1px solid var(--accent-dim)', color: 'var(--accent)', backgroundColor: 'var(--accent-bg)' }}
                  title={t('language_profiles.set_default')}
                >
                  <Star size={11} />
                  {t('language_profiles.set_default_short', 'Als Standard')}
                </button>
              )}
              <button
                onClick={() => startEdit(p)}
                className="p-1.5 rounded transition-all duration-150"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
                title={t('language_profiles.edit_profile')}
              >
                <Edit2 size={12} />
              </button>
              {!p.is_default && (
                <button
                  onClick={() => handleDelete(p.id)}
                  disabled={deleteProfile.isPending}
                  className="p-1.5 rounded transition-all duration-150"
                  style={{ border: '1px solid var(--border)', color: 'var(--error)', backgroundColor: 'var(--bg-primary)' }}
                  title={t('language_profiles.delete_profile')}
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>

          {/* Target languages */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{t('language_profiles.target_languages')}</span>
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
                {t('language_profiles.summary_forced')} <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.forced_preference}</code>
              </span>
            )}
            {p.forced_scoring && p.forced_scoring !== 'include' && (
              <span>
                {t('language_profiles.summary_forced_scoring')} <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.forced_scoring}</code>
              </span>
            )}
            {p.hi_preference && p.hi_preference !== 'include' && (
              <span>
                {t('language_profiles.summary_hi')} <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.hi_preference}</code>
              </span>
            )}
            {p.cutoff_language && (
              <span>
                {t('language_profiles.summary_cutoff')} <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
                  {LANGUAGE_OPTIONS.find((o) => o.value === p.cutoff_language)?.label ?? p.cutoff_language}
                </code>
              </span>
            )}
          </div>
        </div>
      ))}

      {(!profiles || profiles.length === 0) && !showAdd && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          {t('language_profiles.empty')}
        </div>
      )}
    </div>
  )
}
