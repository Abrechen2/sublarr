import { useState } from 'react'
import { Settings2 } from 'lucide-react'
import { updateSeriesProcessingConfig } from '@/api/client'
import { toast } from '@/components/shared/Toast'

type Override = boolean | null // true=on, false=off, null=use global

interface Config {
  hi_removal?: Override
  common_fixes?: Override
  credit_removal?: Override
  auto_sync?: Override
}

interface Props {
  seriesId: number
  initialConfig: Config
}

const MOD_LABELS: Record<keyof Config, string> = {
  hi_removal: 'HI-Removal',
  common_fixes: 'Common Fixes',
  credit_removal: 'Credit-Removal',
  auto_sync: 'Auto-Sync',
}

function OverrideSelect({
  value,
  onChange,
}: {
  value: Override
  onChange: (v: Override) => void
}) {
  const raw = value === null ? 'global' : value ? 'on' : 'off'
  return (
    <select
      value={raw}
      onChange={e => {
        const v = e.target.value
        onChange(v === 'global' ? null : v === 'on')
      }}
      className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200"
    >
      <option value="global">Global (Standard)</option>
      <option value="on">Aktiviert</option>
      <option value="off">Deaktiviert</option>
    </select>
  )
}

export function SeriesProcessingOverride({ seriesId, initialConfig }: Props) {
  const [config, setConfig] = useState<Config>({
    hi_removal: initialConfig.hi_removal ?? null,
    common_fixes: initialConfig.common_fixes ?? null,
    credit_removal: initialConfig.credit_removal ?? null,
    auto_sync: initialConfig.auto_sync ?? null,
  })
  const [saving, setSaving] = useState(false)
  const [expanded, setExpanded] = useState(false)

  async function handleSave() {
    setSaving(true)
    try {
      await updateSeriesProcessingConfig(seriesId, config as Record<string, boolean | null>)
      toast('Einstellungen gespeichert', 'success')
    } catch {
      toast('Speichern fehlgeschlagen', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border border-zinc-700 rounded-lg">
      <button
        onClick={() => setExpanded(v => !v)}
        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
      >
        <Settings2 size={14} />
        <span>Processing Override</span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-zinc-700 pt-2">
          {(Object.keys(MOD_LABELS) as (keyof Config)[]).map(key => (
            <div key={key} className="flex items-center justify-between">
              <span className="text-xs text-zinc-400">{MOD_LABELS[key]}</span>
              <OverrideSelect
                value={config[key] ?? null}
                onChange={v => setConfig(prev => ({ ...prev, [key]: v }))}
              />
            </div>
          ))}
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full mt-2 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 rounded text-white disabled:opacity-50"
          >
            {saving ? 'Speichert…' : 'Speichern'}
          </button>
        </div>
      )}
    </div>
  )
}
