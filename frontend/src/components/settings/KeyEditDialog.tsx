import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ProviderKey, TestConnectionResult } from '@/api/providerKeys'
import { testConnection } from '@/api/providerKeys'

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
  const probeColor = probeResult
    ? probeResult.ok
      ? 'var(--success)'
      : 'var(--warning)'
    : undefined

  return (
    <div role="dialog" data-testid="key-edit-dialog">
      <h3>
        {initial ? t('provider_keys.edit_title') : t('provider_keys.add_title')}
      </h3>
      <label>
        {t('provider_keys.label_field')}
        <input
          data-testid="field-label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
      </label>
      <label>
        {t('provider_keys.api_key_field')}
        <input
          type="password"
          data-testid="field-api-key"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
      </label>
      <label>
        {t('provider_keys.tier_field')}
        <select
          data-testid="field-tier"
          value={tier}
          onChange={(e) => setTier(e.target.value)}
        >
          <option value="free">free</option>
          <option value="vip">vip</option>
          <option value="vip+">vip+</option>
        </select>
      </label>
      <label>
        {t('provider_keys.username_field')}
        <input
          data-testid="field-username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </label>
      <label>
        {t('provider_keys.password_field')}
        <input
          type="password"
          data-testid="field-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <label>
        {t('provider_keys.enabled_field')}
        <input
          type="checkbox"
          data-testid="field-enabled"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
      </label>
      <div>
        <button
          onClick={handleTest}
          data-testid="test-connection"
          disabled={apiKey.length === 0}
        >
          {t('provider_keys.test_connection')}
        </button>
        {probeResult && (
          <span data-testid="probe-result" style={{ color: probeColor }}>
            {probeResult.message}
          </span>
        )}
      </div>
      <button
        onClick={handleSave}
        disabled={!canSave}
        data-testid="save-key"
      >
        {t('provider_keys.save')}
      </button>
      <button onClick={onCancel} data-testid="cancel-key">
        {t('provider_keys.cancel')}
      </button>
    </div>
  )
}
