import { useState } from 'react'
import { Bookmark, ChevronDown, Save, Trash2 } from 'lucide-react'
import { useFilterPresets, useCreateFilterPreset, useDeleteFilterPreset } from '@/hooks/useApi'
import type { FilterScope, FilterGroup } from '@/lib/types'

interface Props {
  scope: FilterScope
  activeFilters: { key: string; op: string; value: string }[]
  onPresetLoad: (conditions: FilterGroup) => void
}

export function FilterPresetMenu({ scope, activeFilters, onPresetLoad }: Props) {
  const [open, setOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saving, setSaving] = useState(false)
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
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        title="Filter presets"
      >
        <Bookmark className="h-3.5 w-3.5" />
        Presets
        <ChevronDown className="h-3 w-3" />
      </button>

      {open && (
        <div className="absolute right-0 top-6 z-20 bg-background border border-border rounded-lg shadow-lg p-3 min-w-52">
          {presets.length === 0 && !saving && (
            <p className="text-xs text-muted-foreground mb-2">No saved presets</p>
          )}
          {presets.map((p) => (
            <div key={p.id} className="flex items-center gap-1 group mb-1">
              <button
                onClick={() => { onPresetLoad(p.conditions); setOpen(false) }}
                className="flex-1 text-left text-sm hover:text-teal-400 truncate"
              >
                {p.name}
              </button>
              <button
                onClick={() => deletePreset.mutate(p.id)}
                className="opacity-0 group-hover:opacity-100 text-destructive"
                aria-label="Delete preset"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}

          <div className="border-t border-border mt-2 pt-2">
            {saving ? (
              <div className="flex gap-1">
                <input
                  type="text"
                  placeholder="Preset name..."
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void handleSave() }}
                  className="flex-1 text-xs bg-background border border-border rounded px-2 py-1 outline-none"
                  autoFocus
                />
                <button onClick={() => void handleSave()} className="text-teal-400 hover:text-teal-300">
                  <Save className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setSaving(true)}
                disabled={activeFilters.length === 0}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                <Save className="h-3 w-3" />
                Save current filters
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
