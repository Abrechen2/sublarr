import { Heart, Github, AlertCircle, Info } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { getHealth } from '@/api/client'

// ─── Component ────────────────────────────────────────────────────────────────

export function AboutSettings() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    staleTime: 60_000,
  })

  const version = health?.version ?? '—'

  return (
    <SettingsDetailLayout
      title="About"
      subtitle="Version, support, and project links"
    >
      <div data-testid="about-settings" className="space-y-4">

        {/* ── Version ───────────────────────────────────────────────────── */}
        <div data-testid="section-version">
          <SettingsSection
            title="Version"
            description="Currently running Sublarr build"
            icon={<Info size={16} style={{ color: 'var(--accent)' }} />}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '10px 14px',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                width: 'fit-content',
              }}
            >
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Sublarr</span>
              <span
                data-testid="version-badge"
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--accent)',
                  fontFamily: 'var(--font-mono, monospace)',
                }}
              >
                {version}
              </span>
            </div>
          </SettingsSection>
        </div>

        {/* ── Links ─────────────────────────────────────────────────────── */}
        <div data-testid="section-links">
          <SettingsSection
            title="Support the Project"
            description="Star the repo, report issues, or buy a coffee"
            icon={<Heart size={16} style={{ color: 'var(--accent)' }} />}
          >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>

              {/* GitHub Star */}
              <a
                data-testid="link-github"
                href="https://github.com/abrechen2/sublarr"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 16px',
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 500,
                  color: 'var(--text-primary)',
                  textDecoration: 'none',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s, color 0.15s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'var(--accent)'
                  e.currentTarget.style.color = 'var(--accent)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                  e.currentTarget.style.color = 'var(--text-primary)'
                }}
              >
                <Github size={15} />
                Star on GitHub
              </a>

              {/* Donate */}
              <a
                data-testid="link-donate"
                href="https://ko-fi.com/sublarr"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 16px',
                  background: 'var(--accent)',
                  border: '1px solid var(--accent)',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 500,
                  color: '#fff',
                  textDecoration: 'none',
                  cursor: 'pointer',
                  transition: 'opacity 0.15s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.85' }}
                onMouseLeave={(e) => { e.currentTarget.style.opacity = '1' }}
              >
                <Heart size={15} />
                Donate
              </a>

              {/* Report Issue */}
              <a
                data-testid="link-issues"
                href="https://github.com/abrechen2/sublarr/issues"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 16px',
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 500,
                  color: 'var(--text-primary)',
                  textDecoration: 'none',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s, color 0.15s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'var(--accent)'
                  e.currentTarget.style.color = 'var(--accent)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                  e.currentTarget.style.color = 'var(--text-primary)'
                }}
              >
                <AlertCircle size={15} />
                Report Issue
              </a>
            </div>
          </SettingsSection>
        </div>

      </div>
    </SettingsDetailLayout>
  )
}
