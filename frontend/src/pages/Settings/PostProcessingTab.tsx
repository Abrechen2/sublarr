import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchOps,
  fetchConfig,
  updateTrigger,
  fetchOpConfig,
  updateOpConfig,
  type Trigger,
  type PostProcessingOp,
  type OpConfigSchemaEntry,
} from '@/api/postProcessing'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'

// Plan B6 — Post-Processing Pipeline settings tab.
//
// Lets the operator configure per-trigger op lists (after_download,
// after_translate, after_sync). Uses React Query to stay in lock-step with
// the rest of Settings and the shared API client.

const TRIGGERS: readonly Trigger[] = [
  'after_download',
  'after_translate',
  'after_sync',
] as const

function LoadingState() {
  const { t } = useTranslation('common')
  return (
    <div className="py-8 text-center text-muted">{t('post_processing_tab.loading')}</div>
  )
}

function ErrorState({ message }: { readonly message: string }) {
  return (
    <div className="py-8 text-center" style={{ color: 'var(--error)' }}>
      {message}
    </div>
  )
}

interface OpConfigFormProps {
  readonly opId: string
  readonly onClose: () => void
}

function OpConfigForm({ opId, onClose }: OpConfigFormProps) {
  const qc = useQueryClient()
  const cfgQuery = useQuery({
    queryKey: ['post-processing', 'op-config', opId],
    queryFn: () => fetchOpConfig(opId),
  })
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (cfgQuery.data) setDraft({ ...cfgQuery.data.values })
  }, [cfgQuery.data])

  const mut = useMutation({
    mutationFn: (values: Record<string, string>) => updateOpConfig(opId, values),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['post-processing', 'op-config', opId] })
      onClose()
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Save failed'
      setError(msg)
    },
  })

  if (cfgQuery.isLoading) {
    return (
      <div className="mt-2 p-3 bg-bg rounded border border-border text-xs text-muted">
        Loading…
      </div>
    )
  }
  if (cfgQuery.isError || !cfgQuery.data) {
    return (
      <div
        className="mt-2 p-3 bg-bg rounded border border-border text-xs"
        style={{ color: 'var(--error)' }}
      >
        Failed to load config
      </div>
    )
  }

  const schema: readonly OpConfigSchemaEntry[] = cfgQuery.data.schema
  if (schema.length === 0) {
    return (
      <div className="mt-2 p-3 bg-bg rounded border border-border text-xs text-muted">
        No configuration for this op.
      </div>
    )
  }

  const onFieldChange = (key: string, value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }))
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    // Submit the draft as-is. The backend preserves existing passwords
    // when the mask sentinel "***" is sent back unchanged.
    mut.mutate(draft)
  }

  return (
    <form
      className="mt-2 p-3 bg-bg rounded border border-border space-y-2"
      onSubmit={onSubmit}
      aria-label={`configure ${opId}`}
    >
      {schema.map((entry) => {
        const inputType =
          entry.type === 'password'
            ? 'password'
            : entry.type === 'number'
              ? 'number'
              : 'text'
        return (
          <div key={entry.key} className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor={`${opId}-${entry.key}`}>
              {entry.label}
              {entry.required ? ' *' : ''}
            </label>
            <input
              id={`${opId}-${entry.key}`}
              type={inputType}
              className="bg-surface border border-border rounded-md p-2 text-sm"
              value={draft[entry.key] ?? ''}
              onChange={(ev) => onFieldChange(entry.key, ev.target.value)}
              required={entry.required && entry.type !== 'password'}
              placeholder={entry.default || undefined}
              autoComplete="off"
            />
          </div>
        )
      })}
      {error && (
        <div className="text-xs" style={{ color: 'var(--error)' }}>
          {error}
        </div>
      )}
      <div className="flex gap-2">
        <button
          type="submit"
          className="text-xs px-3 py-1 rounded border border-border bg-surface hover:bg-surface-hover"
          disabled={mut.isPending}
        >
          {mut.isPending ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          className="text-xs px-3 py-1 rounded border border-border"
          onClick={onClose}
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

interface TriggerSectionProps {
  readonly trigger: Trigger
  readonly configured: readonly string[]
  readonly ops: readonly PostProcessingOp[]
  readonly onChange: (next: readonly string[]) => void
}

// Ops that have at least one field in config_schema. Kept in sync with the
// backend classes in backend/post_processing/ops/. The actual source of
// truth is the GET /ops/<id>/config response; this set just controls the
// visibility of the "Configure" button in the compact list view.
const OPS_WITH_CONFIG = new Set<string>([
  'webhook',
  'discord_notify',
  'plex_refresh',
  'emby_refresh',
  'jellyfin_refresh',
])

function TriggerSection({ trigger, configured, ops, onChange }: TriggerSectionProps) {
  const available = ops.map((op) => op.op_id)
  const opById = new Map(ops.map((op) => [op.op_id, op] as const))
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  const add = (opId: string) => {
    if (!opId) return
    if (!available.includes(opId)) return
    onChange([...configured, opId])
  }

  const remove = (idx: number) => {
    onChange(configured.filter((_, i) => i !== idx))
    if (expandedIdx === idx) setExpandedIdx(null)
  }

  const move = (idx: number, delta: number) => {
    const target = idx + delta
    if (target < 0 || target >= configured.length) return
    const next = [...configured]
    ;[next[idx], next[target]] = [next[target], next[idx]]
    onChange(next)
    if (expandedIdx === idx) setExpandedIdx(target)
    else if (expandedIdx === target) setExpandedIdx(idx)
  }

  return (
    <div className="bg-surface border border-border rounded-md p-4 mb-6">
      <h2 className="font-medium mb-3 capitalize">{trigger.replace('_', ' ')}</h2>
      {configured.length === 0 ? (
        <p className="text-muted text-sm mb-3">
          No ops configured for this trigger.
        </p>
      ) : (
        <ul className="space-y-2 mb-3">
          {configured.map((opId, idx) => {
            const meta = opById.get(opId)
            const hasConfig = OPS_WITH_CONFIG.has(opId)
            const isExpanded = expandedIdx === idx
            return (
              <li
                key={`${opId}-${idx}`}
                className="bg-bg rounded-md p-2 border border-border"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted">{idx + 1}.</span>
                  <code className="text-sm flex-1">{opId}</code>
                  {meta && (
                    <span className="text-xs text-muted hidden md:inline">
                      {meta.label}
                    </span>
                  )}
                  {hasConfig && (
                    <button
                      type="button"
                      className="text-xs px-2 py-1 rounded border border-border hover:bg-surface-hover"
                      onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                      aria-label={`configure ${opId}`}
                      aria-expanded={isExpanded}
                    >
                      {isExpanded ? 'Close' : 'Configure'}
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-xs px-2 py-1 rounded border border-border hover:bg-surface-hover"
                    onClick={() => move(idx, -1)}
                    disabled={idx === 0}
                    aria-label={`move ${opId} up`}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="text-xs px-2 py-1 rounded border border-border hover:bg-surface-hover"
                    onClick={() => move(idx, 1)}
                    disabled={idx === configured.length - 1}
                    aria-label={`move ${opId} down`}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="text-xs px-2 py-1 rounded border"
                    style={{ color: 'var(--error)', borderColor: 'var(--error)' }}
                    onClick={() => remove(idx)}
                    aria-label={`remove ${opId}`}
                  >
                    remove
                  </button>
                </div>
                {isExpanded && hasConfig && (
                  <OpConfigForm opId={opId} onClose={() => setExpandedIdx(null)} />
                )}
              </li>
            )
          })}
        </ul>
      )}
      <select
        className="bg-surface border border-border rounded-md p-2 text-sm"
        value=""
        onChange={(e) => {
          add(e.target.value)
          e.currentTarget.value = ''
        }}
        aria-label={`add op to ${trigger}`}
      >
        <option value="">+ add op…</option>
        {ops.map((op) => (
          <option key={op.op_id} value={op.op_id}>
            {op.label}
          </option>
        ))}
      </select>
    </div>
  )
}

export function PostProcessingTab() {
  const { t } = useTranslation('settings')
  const qc = useQueryClient()
  const opsQuery = useQuery({
    queryKey: ['post-processing', 'ops'],
    queryFn: fetchOps,
  })
  const cfgQuery = useQuery({
    queryKey: ['post-processing', 'config'],
    queryFn: fetchConfig,
  })
  const mut = useMutation({
    mutationFn: ({ trigger, ids }: { trigger: Trigger; ids: readonly string[] }) =>
      updateTrigger(trigger, [...ids]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['post-processing', 'config'] }),
  })

  if (opsQuery.isLoading || cfgQuery.isLoading) {
    return (
      <SettingsDetailLayout title={t('post_processing_tab.title')}>
        <LoadingState />
      </SettingsDetailLayout>
    )
  }
  if (opsQuery.isError || cfgQuery.isError) {
    return (
      <SettingsDetailLayout title={t('post_processing_tab.title')}>
        <ErrorState message="Error loading post-processing config." />
      </SettingsDetailLayout>
    )
  }

  const ops = opsQuery.data ?? []
  const cfg = cfgQuery.data!

  return (
    <SettingsDetailLayout
      title={t('post_processing_tab.title')}
      subtitle={t('post_processing_tab.subtitle')}
    >
      <div className="max-w-3xl">
        {TRIGGERS.map((trigger) => (
          <TriggerSection
            key={trigger}
            trigger={trigger}
            configured={cfg[trigger]}
            ops={ops}
            onChange={(next) => mut.mutate({ trigger, ids: next })}
          />
        ))}
      </div>
    </SettingsDetailLayout>
  )
}
