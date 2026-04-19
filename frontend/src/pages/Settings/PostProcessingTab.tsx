import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchOps,
  fetchConfig,
  updateTrigger,
  type Trigger,
  type PostProcessingOp,
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
  return (
    <div className="py-8 text-center text-muted">Loading post-processing config…</div>
  )
}

function ErrorState({ message }: { readonly message: string }) {
  return (
    <div className="py-8 text-center" style={{ color: 'var(--error)' }}>
      {message}
    </div>
  )
}

interface TriggerSectionProps {
  readonly trigger: Trigger
  readonly configured: readonly string[]
  readonly ops: readonly PostProcessingOp[]
  readonly onChange: (next: readonly string[]) => void
}

function TriggerSection({ trigger, configured, ops, onChange }: TriggerSectionProps) {
  const available = ops.map((op) => op.op_id)
  const opById = new Map(ops.map((op) => [op.op_id, op] as const))

  const add = (opId: string) => {
    if (!opId) return
    if (!available.includes(opId)) return
    onChange([...configured, opId])
  }

  const remove = (idx: number) => {
    onChange(configured.filter((_, i) => i !== idx))
  }

  const move = (idx: number, delta: number) => {
    const target = idx + delta
    if (target < 0 || target >= configured.length) return
    const next = [...configured]
    ;[next[idx], next[target]] = [next[target], next[idx]]
    onChange(next)
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
            return (
              <li
                key={`${opId}-${idx}`}
                className="flex items-center gap-2 bg-bg rounded-md p-2 border border-border"
              >
                <span className="text-xs text-muted">{idx + 1}.</span>
                <code className="text-sm flex-1">{opId}</code>
                {meta && (
                  <span className="text-xs text-muted hidden md:inline">
                    {meta.label}
                  </span>
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
      <SettingsDetailLayout title="Post-Processing Pipeline">
        <LoadingState />
      </SettingsDetailLayout>
    )
  }
  if (opsQuery.isError || cfgQuery.isError) {
    return (
      <SettingsDetailLayout title="Post-Processing Pipeline">
        <ErrorState message="Error loading post-processing config." />
      </SettingsDetailLayout>
    )
  }

  const ops = opsQuery.data ?? []
  const cfg = cfgQuery.data!

  return (
    <SettingsDetailLayout
      title="Post-Processing Pipeline"
      subtitle="Run actions after a subtitle is downloaded, translated, or synced."
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
