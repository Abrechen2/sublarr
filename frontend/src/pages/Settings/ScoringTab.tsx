/**
 * ScoringTab — Scoring weights, provider modifiers, release group filter,
 * and MT detection settings.
 *
 * Redesigned for clarity:
 * - Visual sliders for all weight/modifier controls
 * - Human-readable labels with contextual hints
 * - Single explicit Save per section
 * - Consistent SettingsSection + FormGroup pattern
 */
import { useState, useEffect, useMemo } from 'react'
import { Save, Loader2, RotateCcw, Download, Plus, X } from 'lucide-react'
import {
  useScoringWeights, useUpdateScoringWeights, useResetScoringWeights,
  useProviderModifiers, useUpdateProviderModifiers,
  useScoringPresets, useImportScoringPreset,
  useProviders,
  useConfig, useUpdateConfig,
} from '@/hooks/useApi'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { toast } from '@/components/shared/Toast'
import type { ScoringWeights, ScoringPreset } from '@/lib/types'

// ─── Weight metadata ──────────────────────────────────────────────────────────

interface WeightMeta {
  label: string
  hint: string
}

const WEIGHT_META: Record<string, WeightMeta> = {
  words:           { label: 'Word Count',       hint: 'Score based on subtitle word count similarity to the expected length.' },
  season:          { label: 'Season Match',     hint: 'Bonus when the subtitle season number matches the episode.' },
  episode:         { label: 'Episode Match',    hint: 'Bonus when the subtitle episode number matches exactly.' },
  year:            { label: 'Year Match',       hint: 'Bonus for matching the release year of the content.' },
  resolution:      { label: 'Resolution',       hint: 'Bonus when the subtitle source resolution matches (e.g. 1080p).' },
  source:          { label: 'Source',           hint: 'Bonus for matching the media source (BluRay, WEB-DL, HDTV, etc.).' },
  audio_codec:     { label: 'Audio Codec',      hint: 'Bonus for matching the audio codec (DTS, AAC, FLAC, etc.).' },
  video_codec:     { label: 'Video Codec',      hint: 'Bonus for matching the video codec (x264, x265, AV1, etc.).' },
  release_group:   { label: 'Release Group',    hint: 'Bonus when the subtitle release group matches the media release group.' },
  hearing_impaired:{ label: 'Hearing Impaired', hint: 'Score adjustment for subtitles tagged as hearing-impaired.' },
  format_bonus:    { label: 'ASS Format Bonus', hint: 'Extra score awarded to ASS/SSA subtitles over plain SRT.' },
}

function weightLabel(key: string): WeightMeta {
  return WEIGHT_META[key] ?? {
    label: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    hint: '',
  }
}

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

// ─── WeightRow ────────────────────────────────────────────────────────────────

interface WeightRowProps {
  weightKey: string
  value: number
  defaultValue?: number
  onChange: (v: number) => void
}

function WeightRow({ weightKey, value, defaultValue, onChange }: WeightRowProps) {
  const { label, hint } = weightLabel(weightKey)
  const color =
    value > 0 ? 'var(--success)' : value < 0 ? 'var(--error)' : 'var(--text-muted)'

  return (
    <FormGroup
      label={label}
      hint={hint}
      data-testid={`form-group-weight-${weightKey}`}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <input
          type="range"
          min={-200}
          max={200}
          step={5}
          value={value}
          data-testid={`slider-weight-${weightKey}`}
          onChange={(e) => onChange(parseInt(e.target.value))}
          style={{ width: 140, accentColor: 'var(--accent)' }}
        />
        <input
          type="number"
          min={-200}
          max={200}
          value={value}
          data-testid={`input-weight-${weightKey}`}
          onChange={(e) => onChange(parseInt(e.target.value) || 0)}
          style={{ ...inputStyle, width: 64, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)', color }}
        />
        {defaultValue !== undefined && defaultValue !== value && (
          <span
            title={`Default: ${defaultValue}`}
            style={{ fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}
          >
            (def: {defaultValue})
          </span>
        )}
      </div>
    </FormGroup>
  )
}

// ─── ModifierRow ──────────────────────────────────────────────────────────────

interface ModifierRowProps {
  name: string
  value: number
  onChange: (v: number) => void
}

function ModifierRow({ name, value, onChange }: ModifierRowProps) {
  const color =
    value > 0 ? 'var(--success)' : value < 0 ? 'var(--error)' : 'var(--text-muted)'

  return (
    <FormGroup
      label={name}
      hint={`Add a bonus (positive) or penalty (negative) to every result from ${name}.`}
      data-testid={`form-group-modifier-${name}`}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <input
          type="range"
          min={-100}
          max={100}
          step={5}
          value={value}
          data-testid={`slider-modifier-${name}`}
          onChange={(e) => onChange(parseInt(e.target.value))}
          style={{ width: 140, accentColor: 'var(--accent)' }}
        />
        <span
          data-testid={`value-modifier-${name}`}
          style={{
            width: 40,
            textAlign: 'right',
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'var(--font-mono, monospace)',
            color,
          }}
        >
          {value > 0 ? `+${value}` : value}
        </span>
      </div>
    </FormGroup>
  )
}

// ─── SectionSaveBar ───────────────────────────────────────────────────────────

interface SectionSaveBarProps {
  onSave: () => void
  onReset?: () => void
  isPending: boolean
  isResetPending?: boolean
}

function SectionSaveBar({ onSave, onReset, isPending, isResetPending }: SectionSaveBarProps) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginBottom: 4 }}>
      {onReset && (
        <button
          onClick={onReset}
          disabled={isResetPending}
          data-testid="btn-reset-weights"
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 12px', borderRadius: 6, fontSize: 12, fontWeight: 500,
            border: '1px solid var(--border)', color: 'var(--text-muted)',
            background: 'transparent', cursor: 'pointer', opacity: isResetPending ? 0.5 : 1,
          }}
        >
          <RotateCcw size={11} /> Reset to Defaults
        </button>
      )}
      <button
        onClick={onSave}
        disabled={isPending}
        data-testid="btn-save-weights"
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 500,
          background: 'var(--accent)', color: '#fff',
          border: 'none', cursor: 'pointer', opacity: isPending ? 0.6 : 1,
        }}
      >
        {isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
        Save
      </button>
    </div>
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

  const [episodeWeights, setEpisodeWeights] = useState<Record<string, number>>({})
  const [movieWeights, setMovieWeights] = useState<Record<string, number>>({})
  const [providerMods, setProviderMods] = useState<Record<string, number>>({})
  const [weightsInit, setWeightsInit] = useState(false)
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

  // Preset state
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

  const handleSaveWeights = () => {
    updateWeights.mutate(
      { episode: episodeWeights, movie: movieWeights },
      {
        onSuccess: () => toast('Scoring weights saved'),
        onError: () => toast('Failed to save weights', 'error'),
      },
    )
  }

  const handleResetWeights = () => {
    if (!confirm('Reset all scoring weights to defaults?')) return
    resetWeights.mutate(undefined, {
      onSuccess: () => { setWeightsInit(false); toast('Scoring weights reset to defaults') },
      onError: () => toast('Failed to reset weights', 'error'),
    })
  }

  const handleSaveModifiers = () => {
    const toSave: Record<string, number> = {}
    for (const [name, mod] of Object.entries(providerMods)) {
      if (mod !== 0) toSave[name] = mod
    }
    updateModifiers.mutate(toSave, {
      onSuccess: () => toast('Provider modifiers saved'),
      onError: () => toast('Failed to save modifiers', 'error'),
    })
  }

  const handleApplyPreset = (preset: ScoringPreset) => {
    if (!confirm(`Apply preset "${preset.name}"? This will overwrite the current scoring weights.`)) return
    importPreset.mutate(preset as unknown as Record<string, unknown>, {
      onSuccess: () => {
        setWeightsInit(false)
        setModsInit(false)
        setSelectedPreset('')
        toast(`Preset "${preset.name}" applied`)
      },
      onError: () => toast('Failed to apply preset', 'error'),
    })
  }

  const handleImportCustom = () => {
    let parsed: ScoringPreset
    try {
      parsed = JSON.parse(customPresetJson)
    } catch {
      toast('Invalid JSON', 'error')
      return
    }
    handleApplyPreset(parsed)
    setCustomPresetJson('')
    setShowCustomImport(false)
  }

  const handleSaveReleaseGroup = () => {
    updateConfig.mutate(
      { release_group_prefer: rgPrefer, release_group_exclude: rgExclude, release_group_prefer_bonus: rgBonus },
      {
        onSuccess: () => toast('Release group settings saved'),
        onError: () => toast('Failed to save', 'error'),
      },
    )
  }

  const handleSaveMt = () => {
    updateConfig.mutate(
      { 'providers.mt_penalty': mtPenalty, 'providers.mt_confidence_threshold': mtThreshold },
      {
        onSuccess: () => toast('MT detection settings saved'),
        onError: () => toast('Failed to save', 'error'),
      },
    )
  }

  return (
    <div data-testid="scoring-tab" className="space-y-4">

      {/* ── Load Preset ──────────────────────────────────────────────────── */}
      <SettingsSection
        title="Load Preset"
        description="Apply a bundled scoring profile to quickly adjust all weights at once."
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: 8 }}>
          <select
            data-testid="select-preset"
            value={selectedPreset}
            onChange={(e) => setSelectedPreset(e.target.value)}
            style={{ ...inputStyle, flex: '1 1 180px' }}
          >
            <option value="">Select a preset…</option>
            {(presets ?? []).map((p: { name: string; description: string }) => (
              <option key={p.name} value={p.name}>{p.name} — {p.description}</option>
            ))}
          </select>
          <button
            data-testid="btn-apply-preset"
            disabled={!selectedPreset || importPreset.isPending}
            onClick={() => {
              const preset = (presets ?? []).find((p: { name: string }) => p.name === selectedPreset)
              if (preset) {
                import('@/api/client').then(({ getScoringPreset }) =>
                  getScoringPreset(preset.name).then(handleApplyPreset)
                )
              }
            }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '7px 16px', borderRadius: 6, fontSize: 13, fontWeight: 500,
              background: 'var(--accent)', color: '#fff',
              border: 'none', cursor: 'pointer', opacity: (!selectedPreset || importPreset.isPending) ? 0.5 : 1,
            }}
          >
            {importPreset.isPending ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            Apply
          </button>
          <button
            data-testid="btn-toggle-custom-import"
            onClick={() => setShowCustomImport((v) => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '7px 14px', borderRadius: 6, fontSize: 13,
              border: '1px solid var(--border)', color: 'var(--text-muted)',
              background: 'transparent', cursor: 'pointer',
            }}
          >
            {showCustomImport ? <X size={13} /> : <Plus size={13} />}
            Custom JSON
          </button>
        </div>
        {showCustomImport && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
            <textarea
              data-testid="textarea-custom-preset"
              value={customPresetJson}
              onChange={(e) => setCustomPresetJson(e.target.value)}
              placeholder='{"name":"My Preset","weights":{"episode":{...},"movie":{...}},"provider_modifiers":{}}'
              rows={4}
              style={{
                ...inputStyle,
                width: '100%',
                resize: 'vertical',
                fontFamily: 'var(--font-mono, monospace)',
                fontSize: 12,
              }}
            />
            <button
              data-testid="btn-import-custom-preset"
              onClick={handleImportCustom}
              disabled={!customPresetJson.trim() || importPreset.isPending}
              style={{
                alignSelf: 'flex-end', display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                background: 'var(--accent)', color: '#fff',
                border: 'none', cursor: 'pointer', opacity: (!customPresetJson.trim() || importPreset.isPending) ? 0.5 : 1,
              }}
            >
              <Download size={12} /> Import & Apply
            </button>
          </div>
        )}
      </SettingsSection>

      {/* ── Scoring Weights ───────────────────────────────────────────────── */}
      <SettingsSection
        title="Scoring Weights"
        description="Higher value = more important criteria. Sliders range from −200 (strong penalty) to +200 (strong bonus). Grey shows the factory default."
      >
        <SectionSaveBar
          onSave={handleSaveWeights}
          onReset={handleResetWeights}
          isPending={updateWeights.isPending}
          isResetPending={resetWeights.isPending}
        />

        <div
          data-testid="weight-tables"
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 24 }}
        >
          {/* Episode Weights */}
          <div data-testid="episode-weights">
            <h4
              style={{
                fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 8,
              }}
            >
              Episode
            </h4>
            {Object.entries(episodeWeights).map(([key, val]) => (
              <WeightRow
                key={key}
                weightKey={key}
                value={val}
                defaultValue={weights?.defaults?.episode?.[key]}
                onChange={(v) => setEpisodeWeights({ ...episodeWeights, [key]: v })}
              />
            ))}
          </div>

          {/* Movie Weights */}
          <div data-testid="movie-weights">
            <h4
              style={{
                fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 8,
              }}
            >
              Movie
            </h4>
            {Object.entries(movieWeights).map(([key, val]) => (
              <WeightRow
                key={key}
                weightKey={key}
                value={val}
                defaultValue={weights?.defaults?.movie?.[key]}
                onChange={(v) => setMovieWeights({ ...movieWeights, [key]: v })}
              />
            ))}
          </div>
        </div>
      </SettingsSection>

      {/* ── Provider Score Modifiers ──────────────────────────────────────── */}
      <SettingsSection
        title="Provider Modifiers"
        description="Adjust the score of every result from a specific provider. Use this to favour or downrank individual providers."
      >
        <SectionSaveBar
          onSave={handleSaveModifiers}
          isPending={updateModifiers.isPending}
        />
        <div data-testid="provider-modifiers">
          {Object.entries(providerMods)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([name, mod]) => (
              <ModifierRow
                key={name}
                name={name}
                value={mod}
                onChange={(v) => setProviderMods({ ...providerMods, [name]: v })}
              />
            ))}
          {Object.keys(providerMods).length === 0 && (
            <p style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '12px 0' }}>
              No providers configured.
            </p>
          )}
        </div>
      </SettingsSection>

      {/* ── Release Group Filter ──────────────────────────────────────────── */}
      <SettingsSection
        title="Release Group Filter"
        description="Prefer or block specific release groups. Preferred groups receive a score bonus; blocked groups are excluded entirely."
      >
        <SectionSaveBar onSave={handleSaveReleaseGroup} isPending={updateConfig.isPending} />

        <FormGroup
          label="Preferred Groups"
          hint="Comma-separated release groups that receive a score bonus (e.g. SubsPlease,Erai-raws). Leave empty to disable."
          data-testid="form-group-rg-prefer"
        >
          <input
            id="rg-prefer"
            type="text"
            data-testid="input-rg-prefer"
            value={rgPrefer}
            onChange={(e) => setRgPrefer(e.target.value)}
            placeholder="SubsPlease,Erai-raws"
            style={{ ...inputStyle, width: 220 }}
          />
        </FormGroup>

        <FormGroup
          label="Blocked Groups"
          hint="Comma-separated release groups to exclude from all search results."
          data-testid="form-group-rg-exclude"
        >
          <input
            id="rg-exclude"
            type="text"
            data-testid="input-rg-exclude"
            value={rgExclude}
            onChange={(e) => setRgExclude(e.target.value)}
            placeholder="HorribleSubs,CoalGirls"
            style={{ ...inputStyle, width: 220 }}
          />
        </FormGroup>

        <FormGroup
          label="Prefer Bonus (score pts)"
          hint="Extra score points awarded to subtitles matching a preferred release group."
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
      </SettingsSection>

      {/* ── MT Detection (advanced) ───────────────────────────────────────── */}
      <SettingsSection
        title="Machine Translation Detection"
        description="Subtitles detected as machine-translated receive a score penalty."
        advanced={
          <div data-testid="mt-detection-advanced">
            <SectionSaveBar onSave={handleSaveMt} isPending={updateConfig.isPending} />
            <FormGroup
              label="MT Score Penalty"
              hint="Score penalty applied to machine-translated subtitles. Set to 0 to disable. Range: −50 to 0."
              data-testid="form-group-mt-penalty"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <input
                  type="range"
                  min={-50}
                  max={0}
                  step={1}
                  value={mtPenalty}
                  data-testid="slider-mt-penalty"
                  onChange={(e) => setMtPenalty(parseInt(e.target.value))}
                  style={{ width: 140, accentColor: 'var(--accent)' }}
                />
                <input
                  type="number"
                  min={-50}
                  max={0}
                  value={mtPenalty}
                  data-testid="input-mt-penalty"
                  onChange={(e) => setMtPenalty(Math.max(-50, Math.min(0, parseInt(e.target.value) || 0)))}
                  style={{ ...inputStyle, width: 64, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}
                />
              </div>
            </FormGroup>
            <FormGroup
              label="MT Confidence Threshold"
              hint="Minimum confidence percentage (0–100) required to flag a subtitle as machine-translated."
              data-testid="form-group-mt-threshold"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={mtThreshold}
                  data-testid="slider-mt-threshold"
                  onChange={(e) => setMtThreshold(parseInt(e.target.value))}
                  style={{ width: 140, accentColor: 'var(--accent)' }}
                />
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={mtThreshold}
                  data-testid="input-mt-threshold"
                  onChange={(e) => setMtThreshold(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
                  style={{ ...inputStyle, width: 64, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}
                />
              </div>
            </FormGroup>
          </div>
        }
      >
        <p style={{ fontSize: 12, color: 'var(--text-muted)', padding: '4px 0' }}>
          When enabled, results flagged as machine-translated (above the confidence threshold) receive a score penalty before ranking.
        </p>
      </SettingsSection>

    </div>
  )
}
