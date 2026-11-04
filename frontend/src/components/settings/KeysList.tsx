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
      <div className="flex items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-medium text-foreground">{t('provider_keys.title')}</h4>
          <p className="mt-0.5 text-xs text-muted">{t('provider_keys.hint')}</p>
        </div>
        <button
          type="button"
          onClick={onAdd}
          data-testid="add-key"
          className="shrink-0 rounded border border-border px-3 py-1.5 text-xs text-secondary hover:bg-surface-hover"
        >
          {t('provider_keys.add')}
        </button>
      </div>
      {keys.length === 0 && <p className="mt-2 text-xs text-muted">{t('provider_keys.empty')}</p>}
      <ul className="mt-2">
        {keys.map((k) => (
          <li
            key={k.id}
            data-testid={`key-row-${k.id}`}
            className="flex items-center gap-3 border-b border-border py-2 text-sm"
          >
            <span className="flex-1 text-foreground">{k.label}</span>
            <span className="text-xs text-secondary">{k.tier}</span>
            <span className={`text-xs ${k.enabled ? 'text-success' : 'text-warning'}`}>
              {k.enabled ? t('provider_keys.enabled') : t('provider_keys.disabled')}
            </span>
            <button
              type="button"
              onClick={() => onEdit(k)}
              data-testid={`edit-key-${k.id}`}
              className="text-xs text-accent hover:underline"
            >
              {t('provider_keys.edit')}
            </button>
            <button
              type="button"
              onClick={() => onDelete(k)}
              data-testid={`delete-key-${k.id}`}
              aria-label={isLast ? t('provider_keys.delete_last_aria') : t('provider_keys.delete_aria')}
              className="text-xs text-error hover:underline"
            >
              {t('provider_keys.delete')}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
