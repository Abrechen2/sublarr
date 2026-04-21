/**
 * ScoringPenaltyRules — Plan B4.
 *
 * Lists every registered PenaltyRule (label, description, default weight,
 * current weight) with an inline number input + slider to override the
 * weight. Setting a weight to 0 disables the rule in the pipeline.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Save } from 'lucide-react'

import { FormGroup } from '@/components/settings/FormGroup'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { toast } from '@/components/shared/Toast'
import type { PenaltyRule } from '@/api/settings'
import { usePenaltyRules, useUpdatePenaltyRule } from '@/hooks/useApi'
import { settingsInputStyle } from '@/styles/settingsShared'

const inputStyle: React.CSSProperties = { ...settingsInputStyle, outline: 'none' }

export function ScoringPenaltyRules() {
  const { t: tc } = useTranslation('common')
  const { data, isLoading } = usePenaltyRules()
  const updateRule = useUpdatePenaltyRule()

  // Local edit buffer — keyed by rule_id
  const [edited, setEdited] = useState<Record<string, number>>({})
  const [init, setInit] = useState(false)

  useEffect(() => {
    if (data?.rules && !init) {
      const seed: Record<string, number> = {}
      for (const r of data.rules) seed[r.rule_id] = r.current_weight
      setEdited(seed)
      setInit(true)
    }
  }, [data, init])

  if (isLoading) {
    return (
      <SettingsSection title={tc('ui.penalty_rules')} description="Loading rules...">
        <Loader2 size={14} className="animate-spin" />
      </SettingsSection>
    )
  }

  const rules: PenaltyRule[] = data?.rules ?? []

  const handleSave = (rule: PenaltyRule) => {
    const weight = edited[rule.rule_id] ?? rule.current_weight
    updateRule.mutate(
      { ruleId: rule.rule_id, weight },
      {
        onSuccess: () => toast(`Rule "${rule.label || rule.rule_id}" saved`),
        onError: () => toast('Failed to save rule weight', 'error'),
      },
    )
  }

  return (
    <SettingsSection
      title={tc('ui.penalty_rules')}
      description="Named rules that add or subtract from subtitle scores. Set a rule's weight to 0 to disable it."
    >
      {rules.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 0' }}>
          No penalty rules registered.
        </p>
      )}
      {rules.map(rule => {
        const current = edited[rule.rule_id] ?? rule.current_weight
        const isDirty = current !== rule.current_weight
        const color =
          current > 0 ? 'var(--success)' : current < 0 ? 'var(--error)' : 'var(--text-muted)'
        return (
          <FormGroup
            key={rule.rule_id}
            label={rule.label || rule.rule_id}
            hint={rule.description}
            data-testid={`form-group-penalty-rule-${rule.rule_id}`}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="range"
                min={-100}
                max={100}
                step={1}
                value={current}
                data-testid={`slider-penalty-rule-${rule.rule_id}`}
                onChange={(e) =>
                  setEdited((m) => ({ ...m, [rule.rule_id]: parseInt(e.target.value, 10) }))
                }
                style={{ width: 130, accentColor: 'var(--accent)' }}
              />
              <input
                type="number"
                min={-999}
                max={999}
                value={current}
                data-testid={`input-penalty-rule-${rule.rule_id}`}
                onChange={(e) => {
                  const n = parseInt(e.target.value, 10)
                  if (!isNaN(n)) setEdited((m) => ({ ...m, [rule.rule_id]: n }))
                }}
                style={{ ...inputStyle, width: 72, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)', color }}
              />
              <span style={{ fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                def: {rule.default_weight}
              </span>
              <button
                disabled={!isDirty || updateRule.isPending}
                data-testid={`btn-save-penalty-rule-${rule.rule_id}`}
                onClick={() => handleSave(rule)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500,
                  background: isDirty ? 'var(--accent)' : 'var(--bg-surface)',
                  color: isDirty ? '#fff' : 'var(--text-muted)',
                  border: isDirty ? 'none' : '1px solid var(--border)',
                  cursor: isDirty ? 'pointer' : 'default',
                  opacity: updateRule.isPending ? 0.6 : 1,
                }}
              >
                {updateRule.isPending ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
                Save
              </button>
            </div>
          </FormGroup>
        )
      })}
    </SettingsSection>
  )
}
