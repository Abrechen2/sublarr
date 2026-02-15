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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useHealth } from '@/hooks/useApi'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { LanguageSwitcher } from '@/components/shared/LanguageSwitcher'

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
        className="fixed top-3 left-3 z-50 md:hidden p-2 rounded-md"
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
        className={cn(
          'fixed md:sticky left-0 top-0 h-screen w-56 md:w-60 flex flex-col z-40 md:z-auto shrink-0 transition-transform duration-200',
          mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        )}
        style={{
          backgroundColor: 'var(--bg-surface)',
          borderRight: '1px solid var(--border)',
        }}
      >
        {/* Accent bar at top */}
        <div
          className="h-[2px] w-full shrink-0"
          style={{ background: 'linear-gradient(90deg, var(--accent), var(--accent-dim))' }}
        />

        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-4">
          <img src="/logo-192.png" alt="Sublarr" className="w-8 h-8 rounded-md" />
          <span
            className="text-lg font-bold tracking-tight"
            style={{ color: 'var(--accent)' }}
          >
            Sublarr
          </span>
        </div>

        {/* Divider */}
        <div className="mx-4 mb-1" style={{ borderTop: '1px solid var(--border)' }} />

        {/* Navigation */}
        <nav className="flex-1 px-3 py-1 overflow-y-auto">
          {navGroups.map((group) => (
            <div key={group.titleKey} className="mb-3">
              <div
                className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: 'var(--text-muted)' }}
              >
                {t(group.titleKey)}
              </div>
              {group.items.map(({ to, labelKey, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 px-3 py-2 rounded-md text-[13px] font-medium transition-all duration-150 mb-0.5 relative',
                      isActive ? '' : 'hover:bg-[var(--bg-surface-hover)]'
                    )
                  }
                  style={({ isActive }) => ({
                    backgroundColor: isActive ? 'var(--accent-bg)' : 'transparent',
                    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                  })}
                >
                  {({ isActive }) => (
                    <>
                      {/* Active indicator bar */}
                      {isActive && (
                        <div
                          className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full"
                          style={{ backgroundColor: 'var(--accent)' }}
                        />
                      )}
                      <Icon size={16} strokeWidth={isActive ? 2.2 : 1.8} />
                      {t(labelKey)}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-4 py-3" style={{ borderTop: '1px solid var(--border)' }}>
          <div className="flex items-center justify-end gap-1.5 mb-2">
            <ThemeToggle />
            <LanguageSwitcher />
          </div>
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <div
              className="w-2 h-2 rounded-full shrink-0"
              style={{
                backgroundColor: isHealthy ? 'var(--success)' : 'var(--error)',
                color: isHealthy ? 'var(--success)' : 'var(--error)',
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
