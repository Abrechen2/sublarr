import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LayoutDashboard, BookOpen, Bell, Settings } from 'lucide-react'
import { useWantedSummary } from '@/hooks/useWantedApi'

interface BottomNavItem {
  readonly to: string
  readonly labelKey: string
  readonly icon: typeof LayoutDashboard
  readonly testId: string
  readonly showBadge?: boolean
}

const navItems: readonly BottomNavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, testId: 'bottom-nav-dashboard' },
  { to: '/library', labelKey: 'nav.library', icon: BookOpen, testId: 'bottom-nav-library' },
  { to: '/activity', labelKey: 'nav.activity', icon: Bell, testId: 'bottom-nav-activity', showBadge: true },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings, testId: 'bottom-nav-settings' },
] as const

export function BottomNav() {
  const { t } = useTranslation('common')
  const { data: wantedSummary } = useWantedSummary()

  const wantedCount = wantedSummary?.total ?? 0

  return (
    <nav
      data-testid="bottom-nav"
      className="fixed bottom-0 left-0 right-0 z-50 flex md:hidden"
      style={{
        backgroundColor: 'var(--bg-primary)',
        borderTop: '1px solid var(--border)',
      }}
    >
      {navItems.map(({ to, labelKey, icon: Icon, testId, showBadge }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          data-testid={testId}
          aria-label={t(labelKey)}
          className="flex-1 flex flex-col items-center gap-0.5 py-2 relative transition-colors duration-100"
          style={({ isActive }) => ({
            color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
          })}
        >
          {({ isActive }) => (
            <>
              {/* Active indicator bar at top */}
              {isActive && (
                <div
                  className="absolute top-0 left-4 right-4 h-[2px] rounded-b-sm"
                  style={{ backgroundColor: 'var(--accent)' }}
                />
              )}
              <div className="relative">
                <Icon size={22} strokeWidth={isActive ? 2.2 : 1.8} />
                {showBadge && wantedCount > 0 && (
                  <span
                    data-testid="bottom-nav-badge"
                    className="absolute -top-1 -right-2 text-[9px] font-semibold px-1 min-w-[14px] text-center rounded-full"
                    style={{
                      backgroundColor: 'var(--warning-bg)',
                      color: 'var(--warning)',
                    }}
                  >
                    {wantedCount > 99 ? '99+' : wantedCount}
                  </span>
                )}
              </div>
              <span className="text-[10px] font-medium">{t(labelKey)}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
