/**
 * Tab navigation bar for the SyncControls component.
 */

import type { Chapter } from '@/lib/types'

type SyncOperation = 'offset' | 'speed' | 'framerate' | 'chapter'

const STANDARD_TABS: { key: SyncOperation; label: string }[] = [
  { key: 'offset', label: 'Offset' },
  { key: 'speed', label: 'Speed' },
  { key: 'framerate', label: 'Framerate' },
]

interface SyncTabBarProps {
  activeTab: SyncOperation
  chapters: Chapter[]
  onTabChange: (tab: SyncOperation) => void
}

export function SyncTabBar({ activeTab, chapters, onTabChange }: SyncTabBarProps) {
  return (
    <div
      className="flex gap-1 px-4 py-2"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      {STANDARD_TABS.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onTabChange(tab.key)}
          className="px-3 py-1.5 rounded text-xs font-medium transition-colors"
          style={{
            backgroundColor: activeTab === tab.key ? 'var(--accent-bg)' : 'transparent',
            color: activeTab === tab.key ? 'var(--accent)' : 'var(--text-muted)',
            border: activeTab === tab.key ? '1px solid var(--accent-dim)' : '1px solid transparent',
          }}
        >
          {tab.label}
        </button>
      ))}
      {chapters.length > 0 && (
        <button
          onClick={() => onTabChange('chapter')}
          className="px-3 py-1.5 rounded text-xs font-medium transition-colors"
          style={{
            backgroundColor: activeTab === 'chapter' ? 'var(--accent-bg)' : 'transparent',
            color: activeTab === 'chapter' ? 'var(--accent)' : 'var(--text-muted)',
            border: activeTab === 'chapter' ? '1px solid var(--accent-dim)' : '1px solid transparent',
          }}
        >
          Chapter
        </button>
      )}
    </div>
  )
}
