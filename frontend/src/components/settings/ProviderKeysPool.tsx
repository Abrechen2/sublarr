import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import KeysList from './KeysList'
import KeyEditDialog from './KeyEditDialog'
import {
  listKeys,
  addKey,
  updateKey,
  deleteKey,
  type ProviderKey,
} from '@/api/providerKeys'
import { toast } from '@/components/shared/Toast'

/** Providers that authenticate with API keys and therefore support a key pool. */
const KEY_PROVIDERS = [
  'opensubtitles',
  'subdl',
  'jimaku',
  'legendasdivx',
  'turkcealtyazi',
] as const

export interface ProviderKeysPoolProps {
  readonly providerName: string
}

/**
 * Multi-key pool wrapper mounted in ProviderEditModal.
 *
 * Fetches the provider's keys via react-query, renders KeysList, and shows
 * KeyEditDialog in a modal overlay for add/edit. On save/delete the
 * ['provider-keys', providerName] and ['system', 'budget'] query caches are
 * invalidated so the dashboard budget widget picks up the change live.
 *
 * Renders `null` for providers that don't use API keys (so it's safe to always
 * mount it in the modal regardless of provider type).
 */
export default function ProviderKeysPool({ providerName }: ProviderKeysPoolProps) {
  const { t } = useTranslation('settings')
  const qc = useQueryClient()
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editing, setEditing] = useState<ProviderKey | null>(null)

  const supported = (KEY_PROVIDERS as readonly string[]).includes(providerName)

  const keysQuery = useQuery({
    queryKey: ['provider-keys', providerName],
    queryFn: () => listKeys(providerName),
    enabled: supported,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['provider-keys', providerName] })
    void qc.invalidateQueries({ queryKey: ['system', 'budget'] })
  }

  const addMut = useMutation({
    mutationFn: (payload: Parameters<typeof addKey>[1]) => addKey(providerName, payload),
    onSuccess: () => {
      invalidate()
      setIsDialogOpen(false)
      setEditing(null)
      toast(t('provider_keys.save'))
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Save failed'
      toast(msg, 'error')
    },
  })

  const updateMut = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number
      payload: Parameters<typeof updateKey>[2]
    }) => updateKey(providerName, id, payload),
    onSuccess: () => {
      invalidate()
      setIsDialogOpen(false)
      setEditing(null)
      toast(t('provider_keys.save'))
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Save failed'
      toast(msg, 'error')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteKey(providerName, id),
    onSuccess: () => {
      invalidate()
      toast(t('provider_keys.delete'))
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Delete failed'
      toast(msg, 'error')
    },
  })

  if (!supported) return null

  const handleAdd = () => {
    setEditing(null)
    setIsDialogOpen(true)
  }

  const handleEdit = (k: ProviderKey) => {
    setEditing(k)
    setIsDialogOpen(true)
  }

  const handleDelete = (k: ProviderKey) => {
    deleteMut.mutate(k.id)
  }

  const handleCancel = () => {
    setIsDialogOpen(false)
    setEditing(null)
  }

  const handleSave = (payload: {
    label: string
    api_key: string
    tier: string
    enabled: boolean
    username?: string
    password?: string
  }) => {
    if (editing) {
      updateMut.mutate({ id: editing.id, payload })
    } else {
      addMut.mutate(payload)
    }
  }

  return (
    <div
      className="pt-1"
      style={{ borderTop: '1px solid var(--border)' }}
      data-testid={`provider-keys-pool-${providerName}`}
    >
      <h4 style={{ margin: '12px 0 6px', fontSize: '13px', color: 'var(--text-primary)' }}>
        {t('provider_keys.title')}
      </h4>
      <KeysList
        provider={providerName}
        keys={keysQuery.data ?? []}
        onAdd={handleAdd}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />

      {isDialogOpen && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4"
          style={{ backgroundColor: 'rgba(0,0,0,0.65)' }}
          onClick={(e) => {
            if (e.target === e.currentTarget) handleCancel()
          }}
        >
          <div
            className="w-full max-w-md rounded-lg p-4"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <KeyEditDialog
              provider={providerName}
              initial={editing}
              onSave={handleSave}
              onCancel={handleCancel}
            />
          </div>
        </div>
      )}
    </div>
  )
}
