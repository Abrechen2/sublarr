/**
 * ScoringTab — Redesigned for approachability.
 *
 * UX hierarchy:
 * 1. Preset buttons — one-click "good default" profiles
 * 2. What Matters Most — plain-language toggles for the things users actually care about
 * 3. Release Group Filter — visible by default (most commonly configured)
 * 4. Advanced — full weight sliders + provider modifiers, collapsed by default
 */
import { useState, useEffect, useMemo } from 'react'
import { Save, Loader2, RotateCcw, ChevronDown, ChevronUp } from 'lucide-react'
import {
  useScoringWeights, useUpdateScoringWeights, useResetScoringWeights,
  useProviderModifiers, useUpdateProviderModifiers,
  useScoringPresets, useImportScoringPreset,
  useProviders,
  useConfig, useUpdateConfig,
} from '@/hooks/useApi'
import { FormGroup } from '@/components/settings/FormGroup'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'
import type { ScoringWeights, ScoringPreset } from '@/lib/types'

// ─── Shared styles ────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '6px',
  padding: '7px 12px',
  fontSize: '13px',
  fontFamily: 'var(--font-body)',
  outline: 'none',
}

// ─── Weight display names ─────────────────────────────────────────────────────

const WEIGHT_LABELS: Record<string, string> = {
  words:            'Word Count',
  season:           'Season Match',
  episode:          'Episode Match',
  year:             'Year Match',
  resolution:       'Resolution',
  source:           'Source',
  audio_codec:      'Audio Codec',
  video_codec:      'Video Codec',
  release_group:    'Release Group',
  hearing_impaired: 'Hearing Impaired',
  format_bonus:     'ASS Format Bonus',
}

const WEIGHT_HINTS: Record<string, string> = {
  words:            'Score based on subtitle word count similarity.',
  season:           'Bonus when the subtitle season number matches.',
  episode:          'Bonus when the subtitle episode number matches exactly.',
  year:             'Bonus for matching the release year.',
  resolution:       'Bonus for matching video resolution (e.g. 1080p).',
  source:           'Bonus for matching the media source (BluRay, WEB-DL, etc.).',
  audio_codec:      'Bonus for matching the audio codec.',
  video_codec:      'Bonus for matching the video codec.',
  release_group:    'Bonus when the subtitle release group matches.',
  hearing_impaired: 'Score adjustment for HI-tagged subtitles.',
  format_bonus:     'Extra points for ASS/SSA over plain SRT.',
}

function wLabel(key: string) {
  return WEIGHT_LABELS[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

// ─── WeightSliderRow ──────────────────────────────────────────────────────────

interface WeightSliderRowProps {
  weightKey: string
  value: number
  defaultValue?: number
  onChange: (v: number) => void
}

function WeightSliderRow({ weightKey, value, defaultValue, onChange }: WeightSliderRowProps) {
  const color = value > 0 ? 'var(--success)' : value < 0 ? 'var(--error)' : 'var(--text-muted)'
  return (
    <FormGroup
      label={wLabel(weightKey)}
      hint={WEIGHT_HINTS[weightKey] ?? ''}
      data-testid={`form-group-weight-${weightKey}`}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input
          type="range"
          min={-200}
          max={200}
          step={5}
          value={value}
          data-testid={`slider-weight-${weightKey}`}
          onChange={(e) => onChange(Number(e.target.value))}
          style={{ width: 130, accentColor: 'var(--accent)' }}
        />
        <input
          type="number"
          min={-200}
          max={200}
          value={value}
          data-testid={`input-weight-${weightKey}`}
          onChange={(e) => onChange(parseInt(e.target.value) || 0)}
          style={{ ...inputStyle, width: 62, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)', color }}
        />
        {defaultValue !== undefined && defaultValue !== value && (
          <span style={{ fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
            def: {defaultValue}
          </span>
        )}
      </div>
    </FormGroup>
  )
}

// ─── ScoringTab ───────────────────────────────────────────────────────────────

export function ScoringTab() {
  const { data: scoringData } = useScoringWeights()
  const { data: providers } = useProviders()
  const { data: modifiers } = useProviderModifiers()
  const { data: presets } = useScoringPresets()
  const { data: configData } = useConfig()
  const updateWeights = useUpdateScoringWeights()
  const resetWeights = useResetScoringWeights()
  const updateModifiers = useUpdateProviderModifiers()
  const importPreset = useImportScoringPreset()
  const updateConfig = useUpdateConfig()

  // Weight state
  const [episodeWeights, setEpisodeWeights] = useState<Record<string, number>>({})
  const [movieWeights, setMovieWeights] = useState<Record<string, number>>({})
  const [weightsInit, setWeightsInit] = useState(false)

  // Provider modifier state
  const [providerMods, setProviderMods] = useState<Record<string, number>>({})
  const [modsInit, setModsInit] = useState(false)

  // Release group state
  const [rgPrefer, setRgPrefer] = useState('')
  const [rgExclude, setRgExclude] = useState('')
  const [rgBonus, setRgBonus] = useState(20)
  const [rgInit, setRgInit] = useState(false)

  // MT Detection state
  const [mtPenalty, setMtPenalty] = useState(-30)
  const [mtThreshold, setMtThreshold] = useState(50)
  const [mtInit, setMtInit] = useState(false)

  // Advanced panel
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Applying preset
  const [applyingPreset, setApplyingPreset] = useState<string | null>(null)

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

  useEffect(() => {
    if (configData && !rgInit) {
      const p = configData['release_group_prefer']
      const e = configData['release_group_exclude']
      const b = configData['release_group_prefer_bonus']
      if (p !== undefined) setRgPrefer(String(p))
      if (e !== undefined) setRgExclude(String(e))
      if (b !== undefined) setRgBonus(Number(b))
      setRgInit(true)
    }
  }, [configData, rgInit])

  useEffect(() => {
    if (configData && !mtInit) {
      const p = configData['providers.mt_penalty']
      const t = configData['providers.mt_confidence_threshold']
      if (p !== undefined) setMtPenalty(Number(p))
      if (t !== undefined) setMtThreshold(Number(t))
      setMtInit(true)
    }
  }, [configData, mtInit])

  // ── Derived "what matters" values ──────────────────────────────────────────

  const preferAssFormat = (episodeWeights['format_bonus'] ?? 0) > 0
  const penalizeMt = mtPenalty < 0
  const hasRgPrefer = rgPrefer.trim().length > 0

  const togglePreferAss = (v: boolean) => {
    const val = v ? 30 : 0
    setEpisodeWeights((w) => ({ ...w, format_bonus: val }))
    setMovieWeights((w) => ({ ...w, format_bonus: val }))
    updateWeights.mutate(
      { episode: { ...episodeWeights, format_bonus: val }, movie: { ...movieWeights, format_bonus: val } },
      { onSuccess: () => toast('ASS format preference saved') },
    )
  }

  const togglePenalizeMt = (v: boolean) => {
    const penalty = v ? -30 : 0
    setMtPenalty(penalty)
    updateConfig.mutate(
      { 'providers.mt_penalty': penalty },
      { onSuccess: () => toast('MT penalty updated') },
    )
  }

  // ── Preset apply ───────────────────────────────────────────────────────────

  const handleApplyPreset = (preset: ScoringPreset) => {
    setApplyingPreset(preset.name)
    importPreset.mutate(preset as unknown as Record<string, unknown>, {
      onSuccess: () => {
        setWeightsInit(false)
        setModsInit(false)
        setApplyingPreset(null)
        toast(`Preset "${preset.name}" applied`)
      },
      onError: () => { setApplyingPreset(null); toast('Failed to apply preset', 'error') },
    })
  }

  const handlePresetClick = (presetMeta: { name: string }) => {
    import('@/api/client').then(({ getScoringPreset }) =>
      getScoringPreset(presetMeta.name).then(handleApplyPreset)
    )
  }

  // ── Save helpers ───────────────────────────────────────────────────────────

  const saveWeights = () => {
    updateWeights.mutate(
      { episode: episodeWeights, movie: movieWeights },
      { onSuccess: () => toast('Scoring weights saved'), onError: () => toast('Failed to save', 'error') },
    )
  }

  const resetAllWeights = () => {
    if (!confirm('Reset all scoring weights to factory defaults?')) return
    resetWeights.mutate(undefined, {
      onSuccess: () => { setWeightsInit(false); toast('Weights reset to defaults') },
      onError: () => toast('Failed to reset', 'error'),
    })
  }

  const saveModifiers = () => {
    const toSave: Record<string, number> = {}
    for (const [name, mod] of Object.entries(providerMods)) {
      if (mod !== 0) toSave[name] = mod
    }
    updateModifiers.mutate(toSave, {
      onSuccess: () => toast('Provider modifiers saved'),
      onError: () => toast('Failed to save', 'error'),
    })
  }

  const saveReleaseGroup = () => {
    updateConfig.mutate(
      { release_group_prefer: rgPrefer, release_group_exclude: rgExclude, release_group_prefer_bonus: rgBonus },
      { onSuccess: () => toast('Release group settings saved'), onError: () => toast('Failed to save', 'error') },
    )
  }

  const saveMt = () => {
    updateConfig.mutate(
      { 'providers.mt_penalty': mtPenalty, 'providers.mt_confidence_threshold': mtThreshold },
      { onSuccess: () => toast('MT settings saved'), onError: () => toast('Failed to save', 'error') },
    )
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div data-testid="scoring-tab" className="space-y-4">

      {/* ── 1. Presets ─────────────────────────────────────────────────── */}
      {(presets ?? []).length > 0 && (
        <SettingsSection
          title="Quick Start: Apply a Preset"
          description="One click to apply a tuned scoring profile. Your current weights will be replaced."
        >
          <div
            data-testid="preset-buttons"
            style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}
          >
            {(presets ?? []).map((p: { name: string; description: string }) => {
              const isBusy = applyingPreset === p.name
              return (
                <button
                  key={p.name}
                  data-testid={`btn-preset-${p.name.toLowerCase().replace(/\s+/g, '-')}`}
                  onClick={() => handlePresetClick(p)}
                  disabled={importPreset.isPending}
                  title={p.description}
                  style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                    gap: 2, padding: '10px 14px', borderRadius: 8, cursor: 'pointer',
                    border: '1px solid var(--border)', background: 'var(--bg-elevated)',
                    minWidth: 120, opacity: importPreset.isPending ? 0.6 : 1,
                    transition: 'border-color 0.15s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
                >
                  {isBusy ? (
                    <Loader2 size={13} className="animate-spin" style={{ color: 'var(--accent)' }} />
                  ) : (
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {p.name}
                    </span>
                  )}
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{p.description}</span>
                </button>
              )
            })}
          </div>
        </SettingsSection>
      )}

      {/* ── 2. What Matters Most ───────────────────────────────────────── */}
      <SettingsSection
        title="What Matters Most"
        description="The most impactful settings for subtitle quality. Change these first."
      >
        <FormGroup
          label="Prefer ASS/SSA format"
          hint="Gives a +30 score bonus to ASS and SSA subtitles over plain SRT. Recommended for anime."
          data-testid="form-group-prefer-ass"
        >
          <Toggle
            checked={preferAssFormat}
            onChange={togglePreferAss}
            disabled={updateWeights.isPending}
          />
        </FormGroup>

        <FormGroup
          label="Penalize machine-translated subtitles"
          hint="Applies a −30 score penalty to subtitles flagged as machine-translated."
          data-testid="form-group-penalize-mt"
        >
          <Toggle
            checked={penalizeMt}
            onChange={togglePenalizeMt}
            disabled={updateConfig.isPending}
          />
        </FormGroup>
      </SettingsSection>

      {/* ── 3. Release Group ──────────────────────────────────────────── */}
      <SettingsSection
        title="Release Group Preferences"
        description="Prefer subtitles from specific groups (score bonus) or block groups you dislike."
      >
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
          <button
            data-testid="btn-save-release-group"
            onClick={saveReleaseGroup}
            disabled={updateConfig.isPending}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 500,
              background: 'var(--accent)', color: '#fff',
              border: 'none', cursor: 'pointer', opacity: updateConfig.isPending ? 0.6 : 1,
            }}
          >
            {updateConfig.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            Save
          </button>
        </div>

        <FormGroup
          label="Preferred Groups"
          hint={`Comma-separated release groups that receive a +${rgBonus} score bonus (e.g. SubsPlease, Erai-raws). Leave empty to disable.`}
          data-testid="form-group-rg-prefer"
        >
          <input
            id="rg-prefer"
            type="text"
            data-testid="input-rg-prefer"
            value={rgPrefer}
            onChange={(e) => setRgPrefer(e.target.value)}
            placeholder="SubsPlease,Erai-raws"
            style={{ ...inputStyle, width: 240 }}
          />
        </FormGroup>

        <FormGroup
          label="Blocked Groups"
          hint="Comma-separated groups to exclude from all results entirely."
          data-testid="form-group-rg-exclude"
        >
          <input
            id="rg-exclude"
            type="text"
            data-testid="input-rg-exclude"
            value={rgExclude}
            onChange={(e) => setRgExclude(e.target.value)}
            placeholder="HorribleSubs"
            style={{ ...inputStyle, width: 240 }}
          />
        </FormGroup>

        {hasRgPrefer && (
          <FormGroup
            label="Prefer Bonus (score pts)"
            hint="Extra score points for subtitles matching a preferred group."
            data-testid="form-group-rg-bonus"
          >
            <input
              id="rg-bonus"
              type="number"
              data-testid="input-rg-bonus"
              min={0}
              max={999}
              value={rgBonus}
              onChange={(e) => setRgBonus(Math.max(0, Math.min(999, parseInt(e.target.value) || 0)))}
              style={{ ...inputStyle, width: 90 }}
            />
          </FormGroup>
        )}
      </SettingsSection>

      {/* ── 4. Advanced ────────────────────────────────────────────────── */}
      <div
        data-testid="advanced-scoring"
        style={{
          border: '1px solid var(--border)',
          borderRadius: 10,
          overflow: 'hidden',
        }}
      >
        {/* Toggle header */}
        <button
          data-testid="btn-toggle-advanced"
          onClick={() => setShowAdvanced((v) => !v)}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '12px 16px', background: 'var(--bg-surface)',
            border: 'none', cursor: 'pointer',
          }}
        >
          <div style={{ textAlign: 'left' }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
              Advanced: Fine-tune Weights
            </span>
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              Adjust individual scoring criteria for episodes and movies
            </p>
          </div>
          {showAdvanced
            ? <ChevronUp size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            : <ChevronDown size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
        </button>

        {showAdvanced && (
          <div
            data-testid="advanced-scoring-content"
            style={{ padding: '16px', borderTop: '1px solid var(--border)', background: 'var(--bg-elevated)' }}
          >

            {/* Weight controls */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginBottom: 12 }}>
              <button
                data-testid="btn-reset-weights"
                onClick={resetAllWeights}
                disabled={resetWeights.isPending}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                  border: '1px solid var(--border)', color: 'var(--text-muted)',
                  background: 'transparent', cursor: 'pointer', opacity: resetWeights.isPending ? 0.5 : 1,
                }}
              >
                <RotateCcw size={11} /> Reset to Defaults
              </button>
              <button
                data-testid="btn-save-weights"
                onClick={saveWeights}
                disabled={updateWeights.isPending}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                  background: 'var(--accent)', color: '#fff',
                  border: 'none', cursor: 'pointer', opacity: updateWeights.isPending ? 0.6 : 1,
                }}
              >
                {updateWeights.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                Save Weights
              </button>
            </div>

            <div
              data-testid="weight-tables"
              style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 24 }}
            >
              <div data-testid="episode-weights">
                <h4 style={{
                  fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                  letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 8,
                }}>
                  Episode Weights
                </h4>
                {Object.entries(episodeWeights).map(([key, val]) => (
                  <WeightSliderRow
                    key={key}
                    weightKey={key}
                    value={val}
                    defaultValue={weights?.defaults?.episode?.[key]}
                    onChange={(v) => setEpisodeWeights((w) => ({ ...w, [key]: v }))}
                  />
                ))}
              </div>

              <div data-testid="movie-weights">
                <h4 style={{
                  fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                  letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 8,
                }}>
                  Movie Weights
                </h4>
                {Object.entries(movieWeights).map(([key, val]) => (
                  <WeightSliderRow
                    key={key}
                    weightKey={key}
                    value={val}
                    defaultValue={weights?.defaults?.movie?.[key]}
                    onChange={(v) => setMovieWeights((w) => ({ ...w, [key]: v }))}
                  />
                ))}
              </div>
            </div>

            {/* Provider modifiers */}
            <div style={{ marginTop: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <div>
                  <h4 style={{
                    fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                    letterSpacing: '0.08em', color: 'var(--text-muted)',
                  }}>
                    Provider Modifiers
                  </h4>
                  <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    Bonus or penalty applied to every result from a specific provider.
                  </p>
                </div>
                <button
                  data-testid="btn-save-modifiers"
                  onClick={saveModifiers}
                  disabled={updateModifiers.isPending}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                    background: 'var(--accent)', color: '#fff',
                    border: 'none', cursor: 'pointer', opacity: updateModifiers.isPending ? 0.6 : 1,
                    flexShrink: 0,
                  }}
                >
                  {updateModifiers.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  Save
                </button>
              </div>

              <div data-testid="provider-modifiers">
                {Object.entries(providerMods)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([name, mod]) => {
                    const color = mod > 0 ? 'var(--success)' : mod < 0 ? 'var(--error)' : 'var(--text-muted)'
                    return (
                      <FormGroup
                        key={name}
                        label={name}
                        hint={`Score modifier for all ${name} results.`}
                        data-testid={`form-group-modifier-${name}`}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <input
                            type="range"
                            min={-100}
                            max={100}
                            step={5}
                            value={mod}
                            data-testid={`slider-modifier-${name}`}
                            onChange={(e) => setProviderMods((m) => ({ ...m, [name]: parseInt(e.target.value) }))}
                            style={{ width: 130, accentColor: 'var(--accent)' }}
                          />
                          <span
                            data-testid={`value-modifier-${name}`}
                            style={{ width: 36, textAlign: 'right', fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono, monospace)', color }}
                          >
                            {mod > 0 ? `+${mod}` : mod}
                          </span>
                        </div>
                      </FormGroup>
                    )
                  })}
                {Object.keys(providerMods).length === 0 && (
                  <p style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 0' }}>
                    No providers configured.
                  </p>
                )}
              </div>
            </div>

            {/* MT Detection */}
            <div style={{ marginTop: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <div>
                  <h4 style={{
                    fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                    letterSpacing: '0.08em', color: 'var(--text-muted)',
                  }}>
                    MT Detection Thresholds
                  </h4>
                  <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    Fine-tune the penalty and confidence threshold for machine-translation detection.
                  </p>
                </div>
                <button
                  data-testid="btn-save-mt"
                  onClick={saveMt}
                  disabled={updateConfig.isPending}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                    background: 'var(--accent)', color: '#fff',
                    border: 'none', cursor: 'pointer', opacity: updateConfig.isPending ? 0.6 : 1,
                    flexShrink: 0,
                  }}
                >
                  {updateConfig.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  Save
                </button>
              </div>
              <div data-testid="mt-detection-controls">
                <FormGroup
                  label="MT Score Penalty"
                  hint="Penalty applied to machine-translated subtitles (−50 to 0; 0 = disabled)."
                  data-testid="form-group-mt-penalty"
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="range" min={-50} max={0} step={1}
                      value={mtPenalty}
                      data-testid="slider-mt-penalty"
                      onChange={(e) => setMtPenalty(parseInt(e.target.value))}
                      style={{ width: 130, accentColor: 'var(--accent)' }}
                    />
                    <input
                      type="number" min={-50} max={0}
                      value={mtPenalty}
                      data-testid="input-mt-penalty"
                      onChange={(e) => setMtPenalty(Math.max(-50, Math.min(0, parseInt(e.target.value) || 0)))}
                      style={{ ...inputStyle, width: 62, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}
                    />
                  </div>
                </FormGroup>
                <FormGroup
                  label="MT Confidence Threshold"
                  hint="Minimum confidence % (0–100) to flag a subtitle as machine-translated."
                  data-testid="form-group-mt-threshold"
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="range" min={0} max={100} step={1}
                      value={mtThreshold}
                      data-testid="slider-mt-threshold"
                      onChange={(e) => setMtThreshold(parseInt(e.target.value))}
                      style={{ width: 130, accentColor: 'var(--accent)' }}
                    />
                    <input
                      type="number" min={0} max={100}
                      value={mtThreshold}
                      data-testid="input-mt-threshold"
                      onChange={(e) => setMtThreshold(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
                      style={{ ...inputStyle, width: 62, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}
                    />
                  </div>
                </FormGroup>
              </div>
            </div>

          </div>
        )}
      </div>

    </div>
  )
}
