import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard,
  Activity,
  Search,
  ListOrdered,
  Settings,
  ScrollText,
  Menu,
  X,
  Tv,
  Clock,
  Ban,
  BarChart3,
  ListChecks,
  Heart,
  Star,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useHealth } from '@/hooks/useApi'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { LanguageSwitcher } from '@/components/shared/LanguageSwitcher'
import { ScanProgressIndicator } from '@/components/shared/ScanProgressIndicator'

interface NavItem {
  to: string
  labelKey: string
  icon: typeof LayoutDashboard
}

interface NavGroup {
  titleKey: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    titleKey: 'nav_groups.content',
    items: [
      { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard },
      { to: '/library', labelKey: 'nav.library', icon: Tv },
      { to: '/wanted', labelKey: 'nav.wanted', icon: Search },
    ],
  },
  {
    titleKey: 'nav_groups.activity',
    items: [
      { to: '/activity', labelKey: 'nav.activity', icon: Activity },
      { to: '/queue', labelKey: 'nav.queue', icon: ListOrdered },
      { to: '/history', labelKey: 'nav.history', icon: Clock },
      { to: '/blacklist', labelKey: 'nav.blacklist', icon: Ban },
    ],
  },
  {
    titleKey: 'nav_groups.system',
    items: [
      { to: '/settings', labelKey: 'nav.settings', icon: Settings },
      { to: '/statistics', labelKey: 'nav.statistics', icon: BarChart3 },
      { to: '/tasks', labelKey: 'nav.tasks', icon: ListChecks },
      { to: '/logs', labelKey: 'nav.logs', icon: ScrollText },
    ],
  },
]

export function Sidebar() {
  const { data: health } = useHealth()
  const { t } = useTranslation('common')
  const [mobileOpen, setMobileOpen] = useState(false)
  const isHealthy = health?.status === 'healthy'

  return (
    <>
      {/* Mobile Hamburger */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="fixed top-3 left-3 z-50 md:hidden p-2 rounded"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
        }}
        aria-label="Toggle menu"
      >
        {mobileOpen ? <X size={18} /> : <Menu size={18} />}
      </button>

      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          style={{ backgroundColor: 'rgba(0, 0, 0, 0.6)' }}
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        data-testid="sidebar"
        className={cn(
          'fixed md:sticky left-0 top-0 h-screen w-56 md:w-60 flex flex-col z-40 md:z-auto shrink-0 transition-transform duration-200',
          mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        )}
        style={{
          backgroundColor: 'var(--bg-surface)',
          borderRight: '1px solid var(--border)',
        }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-4 py-3.5" style={{ borderBottom: '1px solid var(--border)' }}>
          <img src="/logo-192.png" alt="Sublarr" className="w-7 h-7 rounded" />
          <span
            className="text-base font-bold tracking-tight"
            style={{ color: 'var(--accent)' }}
          >
            Sublarr
          </span>
        </div>

        {/* Search Trigger — styled as real input */}
        <div className="px-3 py-2.5" style={{ borderBottom: '1px solid var(--border)' }}>
          <button
            data-testid="sidebar-search-trigger"
            onClick={() => {
              document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }))
            }}
            className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-[12px] transition-colors duration-150"
            style={{
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-muted)',
              border: '1px solid var(--border)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-hover)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border)'
            }}
          >
            <Search size={13} strokeWidth={1.8} />
            <span className="flex-1 text-left">{t('search.placeholder', 'Suchen...')}</span>
            <kbd
              className="text-[9px] px-1 py-0.5 rounded hidden sm:inline"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border-hover)',
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-muted)',
                lineHeight: 1.4,
              }}
            >
              {navigator.platform?.includes('Mac') ? '⌘K' : 'Ctrl+K'}
            </kbd>
          </button>
        </div>

        {/* Navigation */}
        <nav data-testid="sidebar-nav" className="flex-1 px-2 py-2 overflow-y-auto">
          {navGroups.map((group) => (
            <div key={group.titleKey} className="mb-1">
              <div
                className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: 'var(--text-muted)' }}
              >
                {t(group.titleKey)}
              </div>
              {group.items.map(({ to, labelKey, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  data-testid={`nav-link-${to === '/' ? 'dashboard' : to.slice(1)}`}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2.5 px-3 py-[7px] text-[13px] font-medium transition-colors duration-100 mb-px relative',
                      !isActive && 'hover:text-[var(--text-primary)]'
                    )
                  }
                  style={({ isActive }) => ({
                    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                    backgroundColor: isActive ? 'rgba(29, 184, 212, 0.06)' : 'transparent',
                    borderRadius: '4px',
                  })}
                >
                  {({ isActive }) => (
                    <>
                      {/* Active indicator bar */}
                      {isActive && (
                        <div
                          className="absolute left-0 top-[5px] bottom-[5px] w-[3px] rounded-r-sm"
                          style={{ backgroundColor: 'var(--accent)' }}
                        />
                      )}
                      <Icon
                        size={15}
                        strokeWidth={isActive ? 2.2 : 1.8}
                        style={{ marginLeft: isActive ? 2 : 0 }}
                      />
                      {t(labelKey)}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-3 py-2.5" style={{ borderTop: '1px solid var(--border)' }}>
          {/* Scan progress */}
          <ScanProgressIndicator />

          {/* Donate + Star */}
          <div className="flex gap-1.5 mb-2">
            <a
              href="https://www.paypal.com/donate?hosted_button_id=GLXYTD3FV9Y78"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-1.5 flex-1 py-1 rounded text-[11px] font-medium transition-colors duration-150"
              style={{
                color: 'var(--text-muted)',
                border: '1px solid var(--border)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = '#e85d8a'
                e.currentTarget.style.color = '#e85d8a'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border)'
                e.currentTarget.style.color = 'var(--text-muted)'
              }}
            >
              <Heart size={11} style={{ color: '#e85d8a' }} />
              Donate
            </a>
            <a
              href="https://github.com/Abrechen2/sublarr"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-1.5 flex-1 py-1 rounded text-[11px] font-medium transition-colors duration-150"
              style={{
                color: 'var(--text-muted)',
                border: '1px solid var(--border)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = '#f5a623'
                e.currentTarget.style.color = '#f5a623'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border)'
                e.currentTarget.style.color = 'var(--text-muted)'
              }}
            >
              <Star size={11} style={{ color: '#f5a623' }} />
              Star
            </a>
          </div>

          <div className="flex items-center justify-end gap-1 mb-1.5">
            <ThemeToggle />
            <LanguageSwitcher />
          </div>

          <div className="flex items-center gap-2 text-[11px]" style={{ color: 'var(--text-secondary)' }}>
            <div
              data-testid="health-indicator"
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{
                backgroundColor: isHealthy ? 'var(--success)' : 'var(--error)',
                animation: 'dotGlow 2s ease-in-out infinite',
              }}
            />
            <span className="truncate">
              {isHealthy ? t('app.online') : t('app.offline')}
            </span>
            <span
              className="ml-auto tabular-nums"
              style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}
            >
              v{health?.version || '0.1.0'}
            </span>
          </div>
        </div>
      </aside>
    </>
  )
}
