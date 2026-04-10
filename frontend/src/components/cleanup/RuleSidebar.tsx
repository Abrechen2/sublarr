import { Plus } from 'lucide-react'
import type { CleanupRule } from '@/types/system'

const TYPE_META: Record<string, { icon: string; label: string }> = {
  language_filter: { icon: '🌐', label: 'Sprache' },
  format_upgrade: { icon: '⬆️', label: 'Qualität' },
  orphan_files: { icon: '🗑️', label: 'Orphan' },
  orphan_db: { icon: '🗄️', label: 'Datenbank' },
  dedup: { icon: '🔍', label: 'Dedup' },
  orphaned: { icon: '🗑️', label: 'Orphan' },
  old_backups: { icon: '📦', label: 'Backups' },
}

const SCHEDULE_LABELS: Record<string, string> = {
  manual: 'Manuell',
  daily: '🕐 Täglich',
  weekly: '🕐 Wöchentlich',
  after_scan: '🕐 Nach Scan',
}

interface RuleSidebarProps {
  rules: CleanupRule[]
  selectedId: number | null
  onSelect: (id: number) => void
  onNew: () => void
}

export function RuleSidebar({ rules, selectedId, onSelect, onNew }: RuleSidebarProps) {
  return (
    <div className="flex flex-col w-full">
      <div className="flex items-center justify-between px-4 py-3">
        <span
          className="text-[10px] font-semibold uppercase tracking-wide"
          style={{ color: 'var(--text-muted)' }}
        >
          Regeln
        </span>
        <button
          onClick={onNew}
          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium"
          style={{ border: '1px solid var(--accent)', color: 'var(--accent)' }}
        >
          <Plus size={10} /> Neu
        </button>
      </div>

      <div className="flex flex-col gap-1 px-2 overflow-y-auto">
        {rules.map((rule) => {
          const meta = TYPE_META[rule.rule_type] ?? { icon: '⚙️', label: rule.rule_type }
          const isActive = rule.id === selectedId
          return (
            <button
              key={rule.id}
              onClick={() => onSelect(rule.id)}
              className="w-full text-left rounded-lg p-2.5 transition-all"
              style={{
                background: isActive ? 'var(--accent-bg)' : 'transparent',
                border: `1px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
              }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span
                  className="flex items-center justify-center rounded-md text-sm flex-shrink-0"
                  style={{ width: 28, height: 28, background: 'var(--bg-primary)' }}
                >
                  {meta.icon}
                </span>
                <span
                  className="flex-1 text-sm font-medium truncate"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {rule.name}
                </span>
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: rule.enabled ? 'var(--success)' : 'var(--border)' }}
                />
              </div>
              <div className="flex items-center gap-1.5 pl-9">
                <span
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded uppercase"
                  style={{ background: 'var(--bg-primary)', color: 'var(--accent)' }}
                >
                  {meta.label}
                </span>
                <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  {SCHEDULE_LABELS[rule.schedule] ?? rule.schedule}
                </span>
              </div>
            </button>
          )
        })}

        {rules.length === 0 && (
          <div className="px-3 py-6 text-xs text-center" style={{ color: 'var(--text-muted)' }}>
            Noch keine Regeln. Erstelle eine um loszulegen.
          </div>
        )}
      </div>
    </div>
  )
}
