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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useHealth } from '@/hooks/useApi'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/activity', label: 'Activity', icon: Activity },
  { to: '/wanted', label: 'Wanted', icon: Search },
  { to: '/queue', label: 'Queue', icon: ListOrdered },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/logs', label: 'Logs', icon: ScrollText },
]

export function Sidebar() {
  const { data: health } = useHealth()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <>
      {/* Mobile Hamburger Button */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="fixed top-4 left-4 z-50 md:hidden p-2 rounded-lg transition-all duration-200 hover:bg-opacity-10"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
        }}
        aria-label="Toggle menu"
      >
        {mobileOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed md:sticky left-0 top-0 h-screen w-56 md:w-64 flex flex-col z-40 md:z-auto shrink-0 transition-transform duration-200 shadow-lg",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        )}
        style={{ backgroundColor: 'var(--bg-surface)', borderRight: '1px solid var(--border)' }}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-5">
          <img src="/favicon.svg" alt="Sublarr" className="w-9 h-9 md:w-10 md:h-10" />
          <span className="text-xl md:text-2xl font-bold" style={{ color: 'var(--accent)' }}>
            Sublarr
          </span>
        </div>

      {/* Divider */}
      <div className="mx-4 mb-2" style={{ borderTop: '1px solid var(--border)' }} />

      {/* Navigation */}
      <nav className="flex-1 px-3 overflow-y-auto">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 mb-0.5',
                isActive
                  ? ''
                  : 'hover:bg-[rgba(29,184,212,0.05)]'
              )
            }
            style={({ isActive }) => ({
              backgroundColor: isActive ? 'rgba(29, 184, 212, 0.15)' : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
            })}
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <div
            className="w-2 h-2 rounded-full animate-pulse"
            style={{
              backgroundColor: health?.status === 'healthy' ? 'var(--success)' : 'var(--error)',
            }}
          />
          <span className="truncate">System: {health?.status === 'healthy' ? 'Healthy' : 'Unhealthy'}</span>
        </div>
        <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
          v{health?.version || '0.1.0'}
        </div>
      </div>
    </aside>
    </>
  )
}
