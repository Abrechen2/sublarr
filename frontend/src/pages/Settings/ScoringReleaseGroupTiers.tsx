/**
 * ScoringReleaseGroupTiers — global release-group tier ranking.
 *
 * Ordered list of release/fansub groups (best first). During wanted-search
 * scoring, a result matching the group at position i of N tiers earns
 * step * (N - i) bonus points, so higher-ranked groups win ties.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowUp, Loader2, Plus, Save, X } from 'lucide-react'

import { FormGroup } from '@/components/settings/FormGroup'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { toast } from '@/components/shared/Toast'
import { useReleaseGroupTiers, useUpdateReleaseGroupTiers } from '@/hooks/useApi'
import { settingsInputStyle } from '@/styles/settingsShared'

const inputStyle: React.CSSProperties = { ...settingsInputStyle, outline: 'none' }

const iconBtnStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 24, height: 24, borderRadius: 5,
  background: 'var(--bg-surface)', border: '1px solid var(--border)',
  color: 'var(--text-muted)', cursor: 'pointer', padding: 0,
}

export function ScoringReleaseGroupTiers() {
  const { t: tc } = useTranslation('common')
  const { data, isLoading } = useReleaseGroupTiers()
  const updateTiers = useUpdateReleaseGroupTiers()

  const [tiers, setTiers] = useState<string[]>([])
  const [step, setStep] = useState(10)
  const [newGroup, setNewGroup] = useState('')
  const [init, setInit] = useState(false)

  useEffect(() => {
    if (data && !init) {
      setTiers(data.tiers)
      setStep(data.step)
      setInit(true)
    }
  }, [data, init])

  if (isLoading) {
    return (
      <SettingsSection
        title={tc('settings:scoring_tiers.title')}
        description={tc('settings:scoring_tiers.loading')}
      >
        <Loader2 size={14} className="animate-spin" />
      </SettingsSection>
    )
  }

  const isDirty =
    init && (step !== (data?.step ?? 10) || JSON.stringify(tiers) !== JSON.stringify(data?.tiers ?? []))

  const addGroup = () => {
    const name = newGroup.trim()
    if (!name) return
    if (tiers.some(g => g.toLowerCase() === name.toLowerCase())) {
      toast(tc('settings:scoring_tiers.toast_duplicate', { name }), 'error')
      return
    }
    setTiers(t => [...t, name])
    setNewGroup('')
  }

  const move = (idx: number, dir: -1 | 1) => {
    setTiers(t => {
      const next = [...t]
      const swap = idx + dir
      if (swap < 0 || swap >= next.length) return t
      ;[next[idx], next[swap]] = [next[swap], next[idx]]
      return next
    })
  }

  const handleSave = () => {
    updateTiers.mutate(
      { tiers, step },
      {
        onSuccess: (saved) => {
          setTiers(saved.tiers)
          setStep(saved.step)
          toast(tc('settings:scoring_tiers.toast_saved'))
        },
        onError: () => toast(tc('settings:scoring_tiers.toast_save_failed'), 'error'),
      },
    )
  }

  const n = tiers.length

  return (
    <SettingsSection
      title={tc('settings:scoring_tiers.title')}
      description={tc('settings:scoring_tiers.section_desc')}
    >
      {tiers.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 0' }}>
          {tc('settings:scoring_tiers.empty')}
        </p>
      )}

      {tiers.map((group, idx) => (
        <div
          key={group.toLowerCase()}
          data-testid={`tier-row-${idx}`}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '6px 0', borderBottom: '1px solid var(--border)',
          }}
        >
          <span
            style={{
              width: 26, textAlign: 'right', fontSize: 11,
              color: 'var(--text-muted)', fontFamily: 'var(--font-mono, monospace)',
            }}
          >
            {idx + 1}.
          </span>
          <span style={{ flex: 1, fontSize: 13 }}>{group}</span>
          <span
            style={{
              fontSize: 11, color: 'var(--success)',
              fontFamily: 'var(--font-mono, monospace)', whiteSpace: 'nowrap',
            }}
          >
            +{step * (n - idx)}
          </span>
          <button
            aria-label={tc('settings:scoring_tiers.move_up')}
            data-testid={`tier-up-${idx}`}
            disabled={idx === 0}
            onClick={() => move(idx, -1)}
            style={{ ...iconBtnStyle, opacity: idx === 0 ? 0.35 : 1 }}
          >
            <ArrowUp size={12} />
          </button>
          <button
            aria-label={tc('settings:scoring_tiers.move_down')}
            data-testid={`tier-down-${idx}`}
            disabled={idx === n - 1}
            onClick={() => move(idx, 1)}
            style={{ ...iconBtnStyle, opacity: idx === n - 1 ? 0.35 : 1 }}
          >
            <ArrowDown size={12} />
          </button>
          <button
            aria-label={tc('settings:scoring_tiers.remove')}
            data-testid={`tier-remove-${idx}`}
            onClick={() => setTiers(t => t.filter((_, i) => i !== idx))}
            style={{ ...iconBtnStyle, color: 'var(--error)' }}
          >
            <X size={12} />
          </button>
        </div>
      ))}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
        <input
          type="text"
          value={newGroup}
          data-testid="input-tier-add"
          placeholder={tc('settings:scoring_tiers.add_placeholder')}
          maxLength={100}
          onChange={(e) => setNewGroup(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') addGroup() }}
          style={{ ...inputStyle, flex: 1 }}
        />
        <button
          data-testid="btn-tier-add"
          onClick={addGroup}
          disabled={!newGroup.trim()}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500,
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            color: 'var(--text)', cursor: newGroup.trim() ? 'pointer' : 'default',
            opacity: newGroup.trim() ? 1 : 0.5,
          }}
        >
          <Plus size={11} />
          {tc('settings:scoring_tiers.add')}
        </button>
      </div>

      <FormGroup
        label={tc('settings:scoring_tiers.step_label')}
        hint={tc('settings:scoring_tiers.step_hint')}
        data-testid="form-group-tier-step"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="number"
            min={1}
            max={500}
            value={step}
            data-testid="input-tier-step"
            onChange={(e) => {
              const v = parseInt(e.target.value, 10)
              if (!isNaN(v)) setStep(Math.max(1, Math.min(500, v)))
            }}
            style={{ ...inputStyle, width: 72, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}
          />
          <button
            disabled={!isDirty || updateTiers.isPending}
            data-testid="btn-save-tiers"
            onClick={handleSave}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500,
              background: isDirty ? 'var(--accent)' : 'var(--bg-surface)',
              color: isDirty ? '#fff' : 'var(--text-muted)',
              border: isDirty ? 'none' : '1px solid var(--border)',
              cursor: isDirty ? 'pointer' : 'default',
              opacity: updateTiers.isPending ? 0.6 : 1,
            }}
          >
            {updateTiers.isPending ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
            {tc('settings:scoring_tiers.save')}
          </button>
        </div>
      </FormGroup>
    </SettingsSection>
  )
}
