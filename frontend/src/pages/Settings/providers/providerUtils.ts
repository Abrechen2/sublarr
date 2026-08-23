import type { ProviderInfo } from '@/lib/types'

/** Minimal i18next-style translator the helpers need. Avoids tying us to the
 * concrete `TFunction` generic and lets any namespace be passed in. */
export type TFn = (key: string, opts?: Record<string, unknown>) => string

/** Reorder a provider priority list — returns a new array (immutable). */
export function reorderProviders(items: string[], fromIndex: number, toIndex: number): string[] {
  if (fromIndex === toIndex) return [...items]
  const next = [...items]
  const [moved] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, moved)
  return next
}

export function getStatusColor(provider: ProviderInfo): string {
  if (!provider.enabled) return 'var(--text-muted)'
  if (provider.stats?.auto_disabled) return 'var(--warning)'
  if (!provider.initialized) return 'var(--warning)'
  return provider.healthy ? 'var(--success)' : 'var(--error)'
}

export function getStatusLabel(provider: ProviderInfo, t: TFn): string {
  if (!provider.enabled) return t('providers_tab.disabled')
  if (provider.stats?.auto_disabled) return t('providers_tab.auto_disabled')
  if (!provider.initialized) return t('providers_tab.editor.not_configured')
  return provider.healthy ? t('providers_tab.healthy') : t('providers_tab.error')
}

export function getStatusBorderColor(provider: ProviderInfo): string {
  if (!provider.enabled) return 'var(--border)'
  if (provider.stats?.auto_disabled) return 'var(--warning)'
  if (!provider.initialized) return 'var(--warning)'
  return provider.healthy ? 'var(--success)' : 'var(--error)'
}

export function getStatusBg(provider: ProviderInfo): string {
  if (!provider.enabled) return 'rgba(124,130,147,0.08)'
  if (provider.stats?.auto_disabled) return 'color-mix(in srgb, var(--warning) 12%, transparent)'
  if (!provider.initialized) return 'color-mix(in srgb, var(--warning) 12%, transparent)'
  return provider.healthy
    ? 'color-mix(in srgb, var(--success) 12%, transparent)'
    : 'color-mix(in srgb, var(--error) 12%, transparent)'
}

export function getSuccessRateColor(rate: number): string {
  if (rate > 0.8) return 'var(--success)'
  if (rate > 0.5) return 'var(--warning)'
  return 'var(--error)'
}

export type CredentialType = 'free' | 'api_key' | 'login'

const CREDENTIAL_TYPES: Record<string, CredentialType> = {
  opensubtitles: 'api_key',
  opensubtitles_com: 'api_key',
  opensubtitlesvip: 'login',
  podnapisi: 'free',
  subdl: 'api_key',
  zimuku: 'free',
  jimaku: 'api_key',
  assrt: 'free',
  gestdown: 'free',
  animetosho: 'free',
  kitsunekko: 'free',
  napisy24: 'free',
  titrari: 'free',
  legendasdivx: 'login',
  whisper_subgen: 'api_key',
  whisperai: 'free',
  addic7ed: 'login',
  tvsubtitles: 'free',
  turkcealtyazi: 'login',
  titlovi: 'login',
}

export function getCredentialBadge(providerName: string): CredentialType {
  return CREDENTIAL_TYPES[providerName] ?? 'free'
}

const KNOWN_DESCRIPTION_KEYS = new Set(Object.keys(CREDENTIAL_TYPES))

export function getProviderDescription(providerName: string, t: TFn): string {
  if (KNOWN_DESCRIPTION_KEYS.has(providerName)) {
    return t(`providers_tab.descriptions.${providerName}`)
  }
  return t('providers_tab.descriptions.fallback')
}

const FIELD_HELP_BY_KEY = new Set([
  'opensubtitles_api_key',
  'opensubtitles_username',
  'opensubtitles_password',
  'subdl_api_key',
  'jimaku_api_key',
])

export function getFieldDescription(key: string, label: string, t: TFn): string {
  if (FIELD_HELP_BY_KEY.has(key)) {
    return t(`providers_tab.field_help.${key}`)
  }

  const lbl = label.toLowerCase()
  if (lbl.includes('api key') || lbl.includes('api-key') || lbl.includes('api token')) {
    return t('providers_tab.field_help.api_key_generic')
  }
  if (lbl.includes('username') || lbl.includes('benutzername')) {
    return t('providers_tab.field_help.username_generic')
  }
  if (lbl.includes('password') || lbl.includes('passwort')) {
    return t('providers_tab.field_help.password_generic')
  }
  if (lbl.includes('url') || lbl.includes('endpoint')) {
    return t('providers_tab.field_help.url_generic')
  }
  if (lbl.includes('timeout')) {
    return t('providers_tab.field_help.timeout_generic')
  }
  if (lbl.includes('priority') || lbl.includes('priorität')) {
    return t('providers_tab.field_help.priority_generic')
  }
  if (lbl.includes('score') || lbl.includes('threshold') || lbl.includes('schwellenwert')) {
    return t('providers_tab.field_help.score_generic')
  }
  return t('providers_tab.field_help.fallback', { label })
}
