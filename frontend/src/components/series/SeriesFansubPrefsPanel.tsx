import React, { useState, useEffect } from 'react'
import { useSeriesFansubPrefs, useSetSeriesFansubPrefs, useDeleteSeriesFansubPrefs } from '../../hooks/useApi'

interface Props {
  seriesId: number
}

export function SeriesFansubPrefsPanel({ seriesId }: Props) {
  const { data: prefs, isLoading } = useSeriesFansubPrefs(seriesId)
  const save = useSetSeriesFansubPrefs(seriesId)
  const reset = useDeleteSeriesFansubPrefs(seriesId)

  const [preferred, setPreferred] = useState('')
  const [excluded, setExcluded] = useState('')
  const [bonus, setBonus] = useState(20)

  useEffect(() => {
    if (!prefs) return
    setPreferred(prefs.preferred_groups.join(', '))
    setExcluded(prefs.excluded_groups.join(', '))
    setBonus(prefs.bonus)
  }, [prefs])

  if (isLoading) return null

  const parseGroups = (raw: string) =>
    raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

  function handleSave() {
    save.mutate({
      preferred_groups: parseGroups(preferred),
      excluded_groups: parseGroups(excluded),
      bonus,
    })
  }

  function handleReset() {
    reset.mutate(undefined, {
      onSuccess: () => {
        setPreferred('')
        setExcluded('')
        setBonus(20)
      },
    })
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '6px 8px',
    borderRadius: 4,
    border: '1px solid var(--border)',
    background: 'var(--bg-input)',
    color: 'var(--text)',
    fontSize: 13,
    boxSizing: 'border-box',
  }

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: 12,
    color: 'var(--text-muted)',
    marginBottom: 4,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <label style={labelStyle}>Preferred Groups (comma-separated)</label>
        <input
          style={inputStyle}
          value={preferred}
          onChange={(e) => setPreferred(e.target.value)}
          placeholder="SubsPlease, Erai-raws"
        />
      </div>
      <div>
        <label style={labelStyle}>Excluded Groups (comma-separated)</label>
        <input
          style={inputStyle}
          value={excluded}
          onChange={(e) => setExcluded(e.target.value)}
          placeholder="HorribleSubs"
        />
      </div>
      <div>
        <label style={labelStyle}>Bonus Points for Preferred Groups</label>
        <input
          type="number"
          style={{ ...inputStyle, width: 80 }}
          value={bonus}
          min={0}
          max={999}
          onChange={(e) => setBonus(Number(e.target.value))}
        />
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={handleSave}
          disabled={save.isPending}
          style={{
            padding: '6px 16px',
            borderRadius: 4,
            border: 'none',
            background: 'var(--accent)',
            color: '#fff',
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          {save.isPending ? 'Saving\u2026' : 'Save'}
        </button>
        <button
          onClick={handleReset}
          disabled={reset.isPending}
          style={{
            padding: '6px 16px',
            borderRadius: 4,
            border: '1px solid var(--border)',
            background: 'transparent',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          Reset to Defaults
        </button>
      </div>
    </div>
  )
}
