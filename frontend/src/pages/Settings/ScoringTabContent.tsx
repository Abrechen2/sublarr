/**
 * ScoringTabContent — Legacy scoring configuration (weights, provider modifiers,
 * release group filter, machine translation detection, presets).
 *
 * Extracted from EventsTab.tsx (pure file split, no functional changes).
 * This is the legacy ScoringTab — the redesigned version lives in ScoringTab.tsx.
 * Import via EventsTab.tsx barrel for LegacySettings backwards compatibility.
 */
import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useScoringWeights, useUpdateScoringWeights, useResetScoringWeights,
  useProviderModifiers, useUpdateProviderModifiers,
  useScoringPresets, useImportScoringPreset,
  useProviders,
  useConfig, useUpdateConfig,
} from '@/hooks/useApi'
import { Save, Loader2, RotateCcw, Plus, X, Download } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { SettingSection } from '@/components/shared/SettingSection'
import type { ScoringWeights, ScoringPreset } from '@/lib/types'

// ─── Release Group Section ────────────────────────────────────────────────────

function ReleaseGroupSection() {
  const { t } = useTranslation('settings')
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()

  const [prefer, setPrefer] = useState<string>('')
  const [exclude, setExclude] = useState<string>('')
  const [bonus, setBonus] = useState<number>(20)
  const [init, setInit] = useState(false)

  useEffect(() => {
    if (configData && !init) {
      const p = configData['release_group_prefer']
      const e = configData['release_group_exclude']
      const b = configData['release_group_prefer_bonus']
      if (p !== undefined) setPrefer(String(p))
      if (e !== undefined) setExclude(String(e))
      if (b !== undefined) setBonus(Number(b))
      setInit(true)
    }
  }, [configData, init])

  const handleSave = () => {
    updateConfig.mutate(
      {
        release_group_prefer: prefer,
        release_group_exclude: exclude,
        release_group_prefer_bonus: bonus,
      },
      {
        onSuccess: () => toast(t('scoring_content.toast_rg_saved')),
        onError: () => toast(t('scoring_content.toast_rg_save_failed'), 'error'),
      }
    )
  }

  return (
    <SettingSection
      title={t('scoring.release_group_filter')}
      description={t('scoring_content.rg_filter_desc')}
    >
      <div className="flex items-center justify-end -mt-1">
        <button
          onClick={handleSave}
          disabled={updateConfig.isPending}
          className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {updateConfig.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          {t('scoring_content.save')}
        </button>
      </div>
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>{t('scoring.preferred_release_groups')}</span>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {t('scoring_content.rg_prefer_hint')}
            </p>
          </div>
          <input
            type="text"
            value={prefer}
            onChange={(e) => setPrefer(e.target.value)}
            placeholder="SubsPlease,Erai-raws"
            className="w-48 px-2 py-1 rounded text-[12px]"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>{t('scoring.blocked_release_groups')}</span>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {t('scoring_content.rg_exclude_hint')}
            </p>
          </div>
          <input
            type="text"
            value={exclude}
            onChange={(e) => setExclude(e.target.value)}
            placeholder="HorribleSubs,CoalGirls"
            className="w-48 px-2 py-1 rounded text-[12px]"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>{t('scoring.prefer_bonus')}</span>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {t('scoring_content.rg_bonus_hint')}
            </p>
          </div>
          <input
            type="number"
            min={0}
            max={999}
            value={bonus}
            onChange={(e) => setBonus(Math.max(0, Math.min(999, parseInt(e.target.value) || 0)))}
            placeholder="20"
            className="w-20 px-2 py-1 rounded text-[12px] text-right"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        </div>
      </div>
    </SettingSection>
  )
}

// ─── MT Detection Section ─────────────────────────────────────────────────────

function MtDetectionSection() {
  const { t } = useTranslation('settings')
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()

  const [penalty, setPenalty] = useState<number>(-30)
  const [threshold, setThreshold] = useState<number>(50)
  const [init, setInit] = useState(false)

  useEffect(() => {
    if (configData && !init) {
      const p = configData['providers.mt_penalty']
      const t = configData['providers.mt_confidence_threshold']
      if (p !== undefined) setPenalty(Number(p))
      if (t !== undefined) setThreshold(Number(t))
      setInit(true)
    }
  }, [configData, init])

  const handleSave = () => {
    updateConfig.mutate(
      { 'providers.mt_penalty': penalty, 'providers.mt_confidence_threshold': threshold },
      {
        onSuccess: () => toast(t('scoring_content.toast_mt_saved')),
        onError: () => toast(t('scoring_content.toast_mt_save_failed'), 'error'),
      }
    )
  }

  return (
    <SettingSection
      title={t('scoring.mt_detection')}
      description={t('scoring_content.mt_detection_desc')}
    >
      <div className="flex items-center justify-end -mt-1">
        <button
          onClick={handleSave}
          disabled={updateConfig.isPending}
          className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {updateConfig.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          {t('scoring_content.save')}
        </button>
      </div>
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>{t('scoring.mt_score_penalty')}</span>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {t('scoring_content.mt_penalty_hint')}
            </p>
          </div>
          <input
            type="number"
            min={-50}
            max={0}
            value={penalty}
            onChange={(e) => setPenalty(Math.max(-50, Math.min(0, parseInt(e.target.value) || 0)))}
            className="w-20 px-2 py-1 rounded text-[12px] text-right"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>{t('scoring.mt_confidence_threshold')}</span>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {t('scoring_content.mt_threshold_hint')}
            </p>
          </div>
          <input
            type="number"
            min={0}
            max={100}
            value={threshold}
            onChange={(e) => setThreshold(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
            className="w-20 px-2 py-1 rounded text-[12px] text-right"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        </div>
      </div>
    </SettingSection>
  )
}

// ─── Scoring Tab ────────────────────────────────────────────────────────────

export function ScoringTab() {
  const { t } = useTranslation('settings')
  const { data: scoringData } = useScoringWeights()
  const { data: providers } = useProviders()
  const { data: modifiers } = useProviderModifiers()
  const { data: presets } = useScoringPresets()
  const updateWeights = useUpdateScoringWeights()
  const resetWeights = useResetScoringWeights()
  const updateModifiers = useUpdateProviderModifiers()
  const importPreset = useImportScoringPreset()

  const [episodeWeights, setEpisodeWeights] = useState<Record<string, number>>({})
  const [movieWeights, setMovieWeights] = useState<Record<string, number>>({})
  const [providerMods, setProviderMods] = useState<Record<string, number>>({})
  const [weightsInit, setWeightsInit] = useState(false)
  const [modsInit, setModsInit] = useState(false)
  const [selectedPreset, setSelectedPreset] = useState('')
  const [customPresetJson, setCustomPresetJson] = useState('')
  const [showCustomImport, setShowCustomImport] = useState(false)

  const weights: ScoringWeights | undefined = scoringData
  const providerList = useMemo(() => providers?.providers ?? [], [providers])

  useEffect(() => {
    if (weights && !weightsInit) {
      setEpisodeWeights(weights.episode)
      setMovieWeights(weights.movie)
      setWeightsInit(true)
    }
  }, [weights, weightsInit])

  useEffect(() => {
    if (modifiers && !modsInit) {
      const mods: Record<string, number> = { ...modifiers }
      for (const p of providerList) {
        if (!(p.name in mods)) mods[p.name] = 0
      }
      setProviderMods(mods)
      setModsInit(true)
    }
  }, [modifiers, providerList, modsInit])

  const handleSaveWeights = () => {
    updateWeights.mutate({ episode: episodeWeights, movie: movieWeights }, {
      onSuccess: () => toast(t('scoring_content.toast_weights_saved')),
      onError: () => toast(t('scoring_content.toast_weights_save_failed'), 'error'),
    })
  }

  const handleResetWeights = () => {
    if (!confirm(t('scoring_content.confirm_reset_weights'))) return
    resetWeights.mutate(undefined, {
      onSuccess: () => {
        setWeightsInit(false)
        toast(t('scoring_content.toast_weights_reset'))
      },
      onError: () => toast(t('scoring_content.toast_weights_reset_failed'), 'error'),
    })
  }

  const handleSaveModifiers = () => {
    const toSave: Record<string, number> = {}
    for (const [name, mod] of Object.entries(providerMods)) {
      if (mod !== 0) toSave[name] = mod
    }
    updateModifiers.mutate(toSave, {
      onSuccess: () => toast(t('scoring_content.toast_modifiers_saved')),
      onError: () => toast(t('scoring_content.toast_modifiers_save_failed'), 'error'),
    })
  }

  const handleApplyPreset = (preset: ScoringPreset) => {
    if (!confirm(t('scoring_content.confirm_apply_preset', { name: preset.name }))) return
    importPreset.mutate(preset as unknown as Record<string, unknown>, {
      onSuccess: () => {
        setWeightsInit(false)
        setModsInit(false)
        setSelectedPreset('')
        toast(t('scoring_content.toast_preset_applied', { name: preset.name }))
      },
      onError: () => toast(t('scoring_content.toast_preset_apply_failed'), 'error'),
    })
  }

  const handleImportCustom = () => {
    let parsed: ScoringPreset
    try {
      parsed = JSON.parse(customPresetJson)
    } catch {
      toast(t('scoring_content.toast_invalid_json'), 'error')
      return
    }
    handleApplyPreset(parsed)
    setCustomPresetJson('')
    setShowCustomImport(false)
  }

  const formatWeightKey = (key: string) => {
    if (key === 'format_bonus') return t('scoring_content.label_ass_format_bonus')
    if (key === 'hearing_impaired') return t('scoring_content.label_hearing_impaired')
    if (key === 'release_group') return t('scoring_content.label_release_group')
    if (key === 'audio_codec') return t('scoring_content.label_audio_codec')
    return key.charAt(0).toUpperCase() + key.slice(1)
  }

  const renderWeightTable = (
    label: string,
    currentWeights: Record<string, number>,
    setFn: (w: Record<string, number>) => void,
    defaults: Record<string, number> | undefined
  ) => (
    <div className="flex-1 min-w-[280px]">
      <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>{label}</h4>
      <div className="space-y-1">
        {Object.entries(currentWeights).map(([key, value]) => (
          <div key={key} className="flex items-center justify-between gap-2">
            <span className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>{formatWeightKey(key)}</span>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={value}
                onChange={(e) => setFn({ ...currentWeights, [key]: parseInt(e.target.value) || 0 })}
                className="w-20 px-2 py-1 rounded text-[12px] text-right"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
              />
              {defaults && (
                <span className="text-[10px] w-8 text-right" style={{ color: 'var(--text-muted)' }}>
                  {defaults[key] ?? ''}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Release Group Filter */}
      <ReleaseGroupSection />

      {/* Scoring Presets */}
      <SettingSection
        title={t('scoring.load_preset')}
        description={t('scoring_content.preset_desc')}
      >
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[160px]">
            <select
              value={selectedPreset}
              onChange={(e) => setSelectedPreset(e.target.value)}
              className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: '13px' }}
            >
              <option value="">{t('scoring.select_preset')}</option>
              {(presets ?? []).map((p: { name: string; description: string }) => (
                <option key={p.name} value={p.name}>{p.name} — {p.description}</option>
              ))}
            </select>
          </div>
          <button
            disabled={!selectedPreset || importPreset.isPending}
            onClick={() => {
              const preset = (presets ?? []).find((p: { name: string }) => p.name === selectedPreset)
              if (preset) {
                import('@/api/client').then(({ getScoringPreset }) =>
                  getScoringPreset(preset.name).then(handleApplyPreset)
                )
              }
            }}
            className="flex items-center gap-1 px-3 py-2 rounded text-xs font-medium text-white disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {importPreset.isPending ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
            {t('scoring_content.apply')}
          </button>
          <button
            onClick={() => setShowCustomImport((v) => !v)}
            className="flex items-center gap-1 px-3 py-2 rounded text-xs font-medium"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            {showCustomImport ? <X size={12} /> : <Plus size={12} />}
            {t('scoring_content.custom_json')}
          </button>
        </div>
        {showCustomImport && (
          <div className="flex flex-col gap-2 mt-2">
            <textarea
              value={customPresetJson}
              onChange={(e) => setCustomPresetJson(e.target.value)}
              placeholder='{"name":"My Preset","weights":{"episode":{...},"movie":{...}},"provider_modifiers":{}}'
              rows={5}
              className="w-full px-3 py-2 rounded-md text-xs font-mono focus:outline-none"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', resize: 'vertical' }}
            />
            <button
              onClick={handleImportCustom}
              disabled={!customPresetJson.trim() || importPreset.isPending}
              className="self-end flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              <Download size={12} /> {t('scoring_content.import_apply')}
            </button>
          </div>
        )}
      </SettingSection>

      {/* Scoring Weights */}
      <SettingSection
        title={t('scoring.scoring_weights')}
        description={t('scoring_content.weights_desc')}
      >
        <div className="flex items-center justify-end gap-2 -mt-1">
          <button
            onClick={handleResetWeights}
            disabled={resetWeights.isPending}
            className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium" style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            <RotateCcw size={11} /> {t('scoring_content.reset_to_defaults')}
          </button>
          <button
            onClick={handleSaveWeights}
            disabled={updateWeights.isPending}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white" style={{ backgroundColor: 'var(--accent)' }}
          >
            {updateWeights.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            {t('scoring_content.save')}
          </button>
        </div>
        <div className="flex flex-wrap gap-6">
          {renderWeightTable(t('scoring_content.episode_weights'), episodeWeights, setEpisodeWeights, weights?.defaults?.episode)}
          {renderWeightTable(t('scoring_content.movie_weights'), movieWeights, setMovieWeights, weights?.defaults?.movie)}
        </div>
      </SettingSection>

      {/* Provider Modifiers */}
      <SettingSection
        title={t('scoring.provider_modifiers')}
        description={t('scoring_content.modifiers_desc')}
      >
        <div className="flex items-center justify-end -mt-1">
          <button
            onClick={handleSaveModifiers}
            disabled={updateModifiers.isPending}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white" style={{ backgroundColor: 'var(--accent)' }}
          >
            {updateModifiers.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            {t('scoring_content.save_all')}
          </button>
        </div>
        <div className="space-y-2">
          {Object.entries(providerMods).sort(([a], [b]) => a.localeCompare(b)).map(([name, mod]) => (
            <div key={name} className="flex items-center justify-between gap-3">
              <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>{name}</span>
              <div className="flex items-center gap-2">
                <input
                  type="range" min={-100} max={100} value={mod}
                  onChange={(e) => setProviderMods({ ...providerMods, [name]: parseInt(e.target.value) })}
                  className="w-32"
                />
                <span className="w-10 text-right text-[12px] font-medium" style={{
                  fontFamily: 'var(--font-mono)',
                  color: mod > 0 ? 'var(--success)' : mod < 0 ? 'var(--error)' : 'var(--text-muted)',
                }}>
                  {mod > 0 ? `+${mod}` : mod}
                </span>
              </div>
            </div>
          ))}
          {Object.keys(providerMods).length === 0 && (
            <p className="text-center text-xs py-3" style={{ color: 'var(--text-muted)' }}>{t('scoring.no_providers')}</p>
          )}
        </div>
      </SettingSection>

      {/* Machine Translation Detection */}
      <MtDetectionSection />
    </div>
  )
}
