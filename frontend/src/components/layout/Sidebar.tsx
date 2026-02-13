import { useState } from 'react'
import { NavLink } from 'react-router-dom'
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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useHealth } from '@/hooks/useApi'

interface NavItem {
  to: string
  label: string
  icon: typeof LayoutDashboard
}

interface NavGroup {
  title: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    title: 'Content',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/library', label: 'Library', icon: Tv },
      { to: '/wanted', label: 'Wanted', icon: Search },
    ],
  },
  {
    title: 'Activity',
    items: [
      { to: '/activity', label: 'Activity', icon: Activity },
      { to: '/queue', label: 'Queue', icon: ListOrdered },
    ],
  },
  {
    title: 'System',
    items: [
      { to: '/settings', label: 'Settings', icon: Settings },
      { to: '/logs', label: 'Logs', icon: ScrollText },
    ],
  },
]

export function Sidebar() {
  const { data: health } = useHealth()
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
          <img src="/favicon.svg" alt="Sublarr" className="w-8 h-8" />
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
            <div key={group.title} className="mb-3">
              <div
                className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: 'var(--text-muted)' }}
              >
                {group.title}
              </div>
              {group.items.map(({ to, label, icon: Icon }) => (
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
                      {label}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-4 py-3" style={{ borderTop: '1px solid var(--border)' }}>
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
              {isHealthy ? 'Online' : 'Offline'}
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
