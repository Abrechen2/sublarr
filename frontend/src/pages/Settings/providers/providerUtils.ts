import type { ProviderInfo } from '@/lib/types'

export function getStatusColor(provider: ProviderInfo): string {
  if (!provider.enabled) return 'var(--text-muted)'
  if (provider.stats?.auto_disabled) return 'var(--warning)'
  if (!provider.initialized) return 'var(--warning)'
  return provider.healthy ? 'var(--success)' : 'var(--error)'
}

export function getStatusLabel(provider: ProviderInfo): string {
  if (!provider.enabled) return 'Disabled'
  if (provider.stats?.auto_disabled) return 'Auto-disabled'
  if (!provider.initialized) return 'Not initialized'
  return provider.healthy ? 'Healthy' : 'Error'
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

export function getFieldDescription(key: string, label: string): string {
  const byKey: Record<string, string> = {
    opensubtitles_api_key: 'REST API-Key von opensubtitles.com (nicht .org) — unter Account Settings',
    opensubtitles_username: 'OpenSubtitles.org Benutzername (kostenlos registrieren)',
    opensubtitles_password: 'OpenSubtitles.org Passwort',
    subdl_api_key: 'API-Schlüssel von subdl.com — unter Account → API',
    jimaku_api_key: 'API-Schlüssel von jimaku.net — unter Einstellungen → API Token',
  }
  if (byKey[key]) return byKey[key]

  const lbl = label.toLowerCase()
  if (lbl.includes('api key') || lbl.includes('api-key') || lbl.includes('api token')) {
    return 'API-Schlüssel für die Authentifizierung beim Provider'
  }
  if (lbl.includes('username') || lbl.includes('benutzername')) {
    return 'Benutzername des Provider-Kontos'
  }
  if (lbl.includes('password') || lbl.includes('passwort')) {
    return 'Passwort des Provider-Kontos'
  }
  if (lbl.includes('url') || lbl.includes('endpoint')) {
    return 'Basis-URL der Provider-Instanz inkl. Port, ohne abschließenden Slash'
  }
  if (lbl.includes('timeout')) {
    return 'Maximale Wartezeit in Sekunden bis eine Anfrage abgebrochen wird'
  }
  if (lbl.includes('priority') || lbl.includes('priorität')) {
    return 'Niedrigere Zahl = höhere Priorität bei der Provider-Auswahl'
  }
  if (lbl.includes('score') || lbl.includes('threshold') || lbl.includes('schwellenwert')) {
    return 'Mindest-Qualitätsscore für akzeptable Untertitel (0–10)'
  }
  return `Konfigurationswert für „${label}"`
}
