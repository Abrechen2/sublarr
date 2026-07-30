/**
 * ScoringCustomRules — user-defined regex scoring rules.
 *
 * Sonarr-style release-profile conditions: each rule's regex is matched
 * case-insensitively against a candidate's release_info during scoring;
 * a hit adds the rule's signed weight to the score.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Plus, Trash2 } from 'lucide-react'

import { SettingsSection } from '@/components/settings/SettingsSection'
import { toast } from '@/components/shared/Toast'
import type { CustomScoringRule } from '@/api/settings'
import {
  useCreateCustomScoringRule,
  useCustomScoringRules,
  useDeleteCustomScoringRule,
  useUpdateCustomScoringRule,
} from '@/hooks/useApi'
import { settingsInputStyle } from '@/styles/settingsShared'

const inputStyle: React.CSSProperties = { ...settingsInputStyle, outline: 'none' }

function extractApiError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { data?: { error?: string } } }).response
    return resp?.data?.error ?? null
  }
  return null
}

export function ScoringCustomRules() {
  const { t: tc } = useTranslation('common')
  const { data, isLoading } = useCustomScoringRules()
  const createRule = useCreateCustomScoringRule()
  const updateRule = useUpdateCustomScoringRule()
  const deleteRule = useDeleteCustomScoringRule()

  const [name, setName] = useState('')
  const [pattern, setPattern] = useState('')
  const [weight, setWeight] = useState(10)

  if (isLoading) {
    return (
      <SettingsSection
        title={tc('settings:scoring_custom.title')}
        description={tc('settings:scoring_custom.loading')}
      >
        <Loader2 size={14} className="animate-spin" />
      </SettingsSection>
    )
  }

  const rules: CustomScoringRule[] = data?.rules ?? []

  const handleAdd = () => {
    createRule.mutate(
      { name: name.trim(), pattern, weight, enabled: true },
      {
        onSuccess: () => {
          setName('')
          setPattern('')
          setWeight(10)
          toast(tc('settings:scoring_custom.toast_created'))
        },
        onError: (err) =>
          toast(
            extractApiError(err) ?? tc('settings:scoring_custom.toast_create_failed'),
            'error',
          ),
      },
    )
  }

  const handleToggle = (rule: CustomScoringRule) => {
    updateRule.mutate(
      { ...rule, enabled: !rule.enabled },
      {
        onError: () => toast(tc('settings:scoring_custom.toast_update_failed'), 'error'),
      },
    )
  }

  const handleDelete = (rule: CustomScoringRule) => {
    deleteRule.mutate(rule.id, {
      onSuccess: () => toast(tc('settings:scoring_custom.toast_deleted', { name: rule.name })),
      onError: () => toast(tc('settings:scoring_custom.toast_delete_failed'), 'error'),
    })
  }

  const canAdd = name.trim().length > 0 && pattern.trim().length > 0

  return (
    <SettingsSection
      title={tc('settings:scoring_custom.title')}
      description={tc('settings:scoring_custom.section_desc')}
    >
      {rules.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 0' }}>
          {tc('settings:scoring_custom.empty')}
        </p>
      )}

      {rules.map((rule) => (
        <div
          key={rule.id}
          data-testid={`custom-rule-row-${rule.id}`}
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '6px 0', borderBottom: '1px solid var(--border)',
            opacity: rule.enabled ? 1 : 0.55,
          }}
        >
          <input
            type="checkbox"
            checked={rule.enabled}
            data-testid={`custom-rule-toggle-${rule.id}`}
            aria-label={tc('settings:scoring_custom.toggle')}
            onChange={() => handleToggle(rule)}
            style={{ accentColor: 'var(--accent)' }}
          />
          <span style={{ flex: '0 1 160px', fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {rule.name}
          </span>
          <code
            style={{
              flex: 1, fontSize: 11, color: 'var(--text-muted)',
              fontFamily: 'var(--font-mono, monospace)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
            title={rule.pattern}
          >
            {rule.pattern}
          </code>
          <span
            style={{
              fontSize: 11, fontFamily: 'var(--font-mono, monospace)', whiteSpace: 'nowrap',
              color: rule.weight > 0 ? 'var(--success)' : rule.weight < 0 ? 'var(--error)' : 'var(--text-muted)',
            }}
          >
            {rule.weight > 0 ? `+${rule.weight}` : rule.weight}
          </span>
          <button
            aria-label={tc('settings:scoring_custom.delete')}
            data-testid={`custom-rule-delete-${rule.id}`}
            onClick={() => handleDelete(rule)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 24, height: 24, borderRadius: 5, padding: 0,
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              color: 'var(--error)', cursor: 'pointer',
            }}
          >
            <Trash2 size={12} />
          </button>
        </div>
      ))}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
        <input
          type="text"
          value={name}
          data-testid="input-custom-rule-name"
          placeholder={tc('settings:scoring_custom.name_placeholder')}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
          style={{ ...inputStyle, width: 150 }}
        />
        <input
          type="text"
          value={pattern}
          data-testid="input-custom-rule-pattern"
          placeholder={tc('settings:scoring_custom.pattern_placeholder')}
          maxLength={500}
          onChange={(e) => setPattern(e.target.value)}
          style={{ ...inputStyle, flex: 1, minWidth: 160, fontFamily: 'var(--font-mono, monospace)' }}
        />
        <input
          type="number"
          value={weight}
          min={-999}
          max={999}
          data-testid="input-custom-rule-weight"
          onChange={(e) => {
            const n = parseInt(e.target.value, 10)
            if (!isNaN(n)) setWeight(Math.max(-999, Math.min(999, n)))
          }}
          style={{ ...inputStyle, width: 72, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)' }}
        />
        <button
          data-testid="btn-custom-rule-add"
          onClick={handleAdd}
          disabled={!canAdd || createRule.isPending}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500,
            background: canAdd ? 'var(--accent)' : 'var(--bg-surface)',
            color: canAdd ? '#fff' : 'var(--text-muted)',
            border: canAdd ? 'none' : '1px solid var(--border)',
            cursor: canAdd ? 'pointer' : 'default',
            opacity: createRule.isPending ? 0.6 : 1,
          }}
        >
          {createRule.isPending ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
          {tc('settings:scoring_custom.add')}
        </button>
      </div>

      <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
        {tc('settings:scoring_custom.hint')}
      </p>
    </SettingsSection>
  )
}
