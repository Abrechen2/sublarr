import { useState, useRef, useEffect } from 'react'
import { Bookmark, ChevronDown, Save, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useFilterPresets, useCreateFilterPreset, useDeleteFilterPreset } from '@/hooks/useApi'
import type { FilterScope, FilterGroup } from '@/lib/types'

interface Props {
  scope: FilterScope
  activeFilters: { key: string; op: string; value: string }[]
  onPresetLoad: (conditions: FilterGroup) => void
}

export function FilterPresetMenu({ scope, activeFilters, onPresetLoad }: Props) {
  const { t } = useTranslation('common')
  const [open, setOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saving, setSaving] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
        setSaving(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])
  const { data: presets = [] } = useFilterPresets(scope)
  const createPreset = useCreateFilterPreset()
  const deletePreset = useDeleteFilterPreset(scope)

  const handleSave = async () => {
    if (!saveName.trim()) return
    const conditions: FilterGroup = {
      logic: 'AND',
      conditions: activeFilters.map((f) => ({
        field: f.key,
        op: f.op as 'eq',
        value: f.value,
      })),
    }
    await createPreset.mutateAsync({ name: saveName.trim(), scope, conditions, is_default: false })
    setSaveName('')
    setSaving(false)
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 text-xs transition-colors"
        style={{ color: open ? 'var(--accent)' : 'var(--text-muted)' }}
        title={t('filters.presets')}
      >
        <Bookmark className="h-3.5 w-3.5" />
        {t('filters.presets')}
        <ChevronDown className="h-3 w-3" />
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            right: 0,
            top: '1.75rem',
            zIndex: 9999,
            minWidth: '210px',
            padding: '10px',
            borderRadius: '8px',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--accent-dim)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
          }}
        >
          {presets.length === 0 && !saving && (
            <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>{t('filters.noPresets')}</p>
          )}
          {presets.map((p) => (
            <div key={p.id} className="flex items-center gap-1 group mb-1">
              <button
                onClick={() => { onPresetLoad(p.conditions); setOpen(false) }}
                className="flex-1 text-left text-sm truncate"
                style={{ color: 'var(--text-primary)' }}
              >
                {p.name}
              </button>
              <button
                onClick={() => deletePreset.mutate(p.id)}
                className="opacity-0 group-hover:opacity-100"
                style={{ color: 'var(--danger)' }}
                aria-label="Delete preset"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}

          <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
            {saving ? (
              <div className="flex gap-1">
                <input
                  type="text"
                  placeholder={t('filters.presetName')}
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void handleSave() }}
                  className="flex-1 text-xs rounded px-2 py-1 outline-none"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                  autoFocus
                />
                <button onClick={() => void handleSave()} style={{ color: 'var(--accent)' }}>
                  <Save className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setSaving(true)}
                disabled={activeFilters.length === 0}
                className="flex items-center gap-1 text-xs disabled:opacity-40 transition-colors"
                style={{ color: 'var(--text-muted)' }}
              >
                <Save className="h-3 w-3" />
                {t('filters.saveCurrentFilters')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
