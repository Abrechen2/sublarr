import { Heart, Github, AlertCircle, Info, MessageCircle, Users } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'
import { getHealth } from '@/api/client'

// Settings Template B (FormLayout) — Codex-named reference for an info-heavy
// page. titleKeys reuse the existing about_page.*_title strings (the
// section heading and the TOC entry should always read the same).
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'version',   titleKey: 'about_page.version_title' },
  { id: 'support',   titleKey: 'about_page.support_title' },
  { id: 'community', titleKey: 'about_page.community_title' },
]

// ─── Component ────────────────────────────────────────────────────────────────

export function AboutSettings() {
  const { t } = useTranslation('settings')
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    staleTime: 60_000,
  })

  const version = health?.version ?? '—'

  return (
    <SettingsDetailLayout
      title={t('about_page.title')}
      subtitle={t('about_page.subtitle')}
    >
      <div data-testid="about-settings">
        <FormLayout sections={SECTIONS}>

        {/* ── Version ───────────────────────────────────────────────────── */}
        <section id="version" data-testid="settings.about.section-version">
        <div data-testid="section-version">
          <SettingsSection
            title={t('about_page.version_title')}
            description={t('about_page.version_desc')}
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
        </section>

        {/* ── Links ─────────────────────────────────────────────────────── */}
        <section id="support" data-testid="settings.about.section-support">
        <div data-testid="section-links">
          <SettingsSection
            title={t('about_page.support_title')}
            description={t('about_page.support_desc')}
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
                {t('about_page.star_github')}
              </a>

              {/* Donate */}
              <a
                data-testid="link-donate"
                href="https://www.paypal.com/donate?hosted_button_id=GLXYTD3FV9Y78"
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
                {t('about_page.donate')}
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
                {t('about_page.report_issue')}
              </a>
            </div>
          </SettingsSection>
        </div>
        </section>

        {/* ── Community ─────────────────────────────────────────────────── */}
        <section id="community" data-testid="settings.about.section-community">
        <div data-testid="section-community">
          <SettingsSection
            title={t('about_page.community_title')}
            description={t('about_page.community_desc')}
            icon={<Users size={16} style={{ color: 'var(--accent)' }} />}
          >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>

              {/* Discord */}
              <a
                data-testid="link-discord"
                href="https://discord.gg/WjatsKzHXz"
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
                <MessageCircle size={15} />
                {t('about_page.join_discord')}
              </a>

              {/* Reddit */}
              <a
                data-testid="link-reddit"
                href="https://www.reddit.com/r/Sublarr/"
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
                <Users size={15} />
                {t('about_page.visit_reddit')}
              </a>
            </div>
          </SettingsSection>
        </div>
        </section>

        </FormLayout>
      </div>
    </SettingsDetailLayout>
  )
}
