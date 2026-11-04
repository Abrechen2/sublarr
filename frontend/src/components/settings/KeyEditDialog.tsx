import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { ProviderKey, TestConnectionResult } from '@/api/providerKeys'
import { testConnection } from '@/api/providerKeys'

const INPUT =
  'w-full rounded border border-border bg-page px-2.5 py-1.5 text-sm text-foreground focus:outline-none'
const BUTTON = 'rounded px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50'

/** Fields beyond the key itself, for the providers whose accounts have them. */
const KEY_FIELDS: Record<string, { tier?: boolean; account?: boolean }> = {
  opensubtitles: { tier: true, account: true },
  legendasdivx: { account: true },
  turkcealtyazi: { account: true },
}

export interface KeyEditDialogProps {
  provider: string
  initial?: ProviderKey | null
  onSave: (payload: {
    label: string
    api_key: string
    tier: string
    enabled: boolean
    username?: string
    password?: string
  }) => void
  onCancel: () => void
}

export default function KeyEditDialog({
  provider,
  initial,
  onSave,
  onCancel,
}: KeyEditDialogProps) {
  const { t } = useTranslation('settings')
  const [label, setLabel] = useState(initial?.label ?? 'primary')
  const [apiKey, setApiKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [tier, setTier] = useState(initial?.tier ?? 'free')
  const [enabled, setEnabled] = useState(initial?.enabled ?? true)
  const [probeResult, setProbeResult] = useState<TestConnectionResult | null>(null)

  const handleTest = async () => {
    const res = await testConnection(provider, {
      api_key: apiKey,
      username: username || undefined,
      password: password || undefined,
    })
    setProbeResult(res)
  }

  const handleSave = () => {
    onSave({
      label,
      api_key: apiKey,
      tier,
      enabled,
      username: username || undefined,
      password: password || undefined,
    })
  }

  const canSave = label.length > 0 && apiKey.length > 0
  const fields = KEY_FIELDS[provider] ?? {}
  const probeColor = probeResult
    ? probeResult.ok
      ? 'text-success'
      : 'text-warning'
    : ''

  return (
    <div role="dialog" aria-labelledby="key-edit-title" data-testid="key-edit-dialog">
      <h3 id="key-edit-title" className="mb-4 text-sm font-semibold text-primary">
        {initial ? t('provider_keys.edit_title') : t('provider_keys.add_title')}
      </h3>
      <div className="space-y-3">
        <Field label={t('provider_keys.label_field')}>
          <input
            data-testid="field-label"
            className={INPUT}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </Field>
        <Field label={t('provider_keys.api_key_field')}>
          <input
            type="password"
            data-testid="field-api-key"
            className={INPUT}
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </Field>
        {fields.tier && (
          <Field label={t('provider_keys.tier_field')}>
            <select
              data-testid="field-tier"
              className={INPUT}
              value={tier}
              onChange={(e) => setTier(e.target.value)}
            >
              <option value="free">free</option>
              <option value="vip">vip</option>
              <option value="vip+">vip+</option>
            </select>
          </Field>
        )}
        {fields.account && (
          <>
            <Field label={t('provider_keys.username_field')}>
              <input
                data-testid="field-username"
                className={INPUT}
                autoComplete="off"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field label={t('provider_keys.password_field')}>
              <input
                type="password"
                data-testid="field-password"
                className={INPUT}
                autoComplete="off"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          </>
        )}
        <label className="flex items-center gap-2 text-sm text-secondary">
          <input
            type="checkbox"
            data-testid="field-enabled"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          {t('provider_keys.enabled_field')}
        </label>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <button
          type="button"
          onClick={handleTest}
          data-testid="test-connection"
          disabled={apiKey.length === 0}
          className={`${BUTTON} border border-border text-secondary`}
        >
          {t('provider_keys.test_connection')}
        </button>
        {probeResult && (
          <span data-testid="probe-result" className={`text-xs ${probeColor}`}>
            {probeResult.message}
          </span>
        )}
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            data-testid="cancel-key"
            className={`${BUTTON} border border-border text-secondary`}
          >
            {t('provider_keys.cancel')}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            data-testid="save-key"
            className={`${BUTTON} bg-accent font-semibold text-white`}
          >
            {t('provider_keys.save')}
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-secondary">{label}</span>
      {children}
    </label>
  )
}
