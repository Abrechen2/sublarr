import { useTranslation } from 'react-i18next'
import type { ProviderKey } from '@/api/providerKeys'

export interface KeysListProps {
  provider: string
  keys: ProviderKey[]
  onAdd: () => void
  onEdit: (key: ProviderKey) => void
  onDelete: (key: ProviderKey) => void
}

export default function KeysList({ provider, keys, onAdd, onEdit, onDelete }: KeysListProps) {
  const { t } = useTranslation('settings')
  const isLast = keys.length === 1

  return (
    <div data-testid={`keys-list-${provider}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: 0 }}>{t('provider_keys.title')}</h4>
        <button onClick={onAdd} data-testid="add-key">
          {t('provider_keys.add')}
        </button>
      </div>
      {keys.length === 0 && (
        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{t('provider_keys.empty')}</p>
      )}
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {keys.map((k) => (
          <li
            key={k.id}
            data-testid={`key-row-${k.id}`}
            style={{
              display: 'flex',
              gap: '8px',
              alignItems: 'center',
              padding: '8px 0',
              borderBottom: '1px solid var(--border)',
            }}
          >
            <span style={{ flex: '1' }}>{k.label}</span>
            <span style={{ color: 'var(--text-secondary)' }}>{k.tier}</span>
            <span style={{ color: k.enabled ? 'var(--success)' : 'var(--warning)' }}>
              {k.enabled ? t('provider_keys.enabled') : t('provider_keys.disabled')}
            </span>
            <button onClick={() => onEdit(k)} data-testid={`edit-key-${k.id}`}>
              {t('provider_keys.edit')}
            </button>
            <button
              onClick={() => onDelete(k)}
              data-testid={`delete-key-${k.id}`}
              aria-label={isLast ? t('provider_keys.delete_last_aria') : t('provider_keys.delete_aria')}
            >
              {t('provider_keys.delete')}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
