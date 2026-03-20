import { useEffect, useRef, useState } from 'react'
import {
  useSeriesFansubPrefs,
  useSetSeriesFansubPrefs,
  useDeleteSeriesFansubPrefs,
} from '@/hooks/useApi'

interface Props {
  seriesId: number
  open: boolean
  onClose: () => void
}

export function FansubOverrideModal({ seriesId, open, onClose }: Props) {
  const { data: prefs, isLoading } = useSeriesFansubPrefs(seriesId)
  const setPrefs = useSetSeriesFansubPrefs(seriesId)
  const deletePrefs = useDeleteSeriesFansubPrefs(seriesId)

  const [preferred, setPreferred] = useState('')
  const [excluded, setExcluded] = useState('')
  const [bonus, setBonus] = useState(20)

  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) {
      dialogRef.current?.focus()
    }
  }, [open])

  // Include `open` so re-opening with cached prefs still resets fields
  useEffect(() => {
    if (prefs) {
      setPreferred(prefs.preferred_groups.join(', '))
      setExcluded(prefs.excluded_groups.join(', '))
      setBonus(prefs.bonus)
    }
  }, [prefs, open])

  if (!open) return null

  const parseGroups = (s: string) =>
    s.split(',').map((g) => g.trim()).filter(Boolean)

  const handleSave = () => {
    setPrefs.mutate(
      { preferred_groups: parseGroups(preferred), excluded_groups: parseGroups(excluded), bonus },
      {
        onSuccess: onClose,
        onError: (err) => console.error('Failed to save fansub preferences', err),
      },
    )
  }

  const handleReset = () => {
    deletePrefs.mutate(undefined, {
      onSuccess: onClose,
      onError: (err) => console.error('Failed to reset fansub preferences', err),
    })
  }

  const hasOverride =
    (prefs?.preferred_groups.length ?? 0) > 0 ||
    (prefs?.excluded_groups.length ?? 0) > 0

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000,
        }}
      />
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="fansub-modal-title"
        style={{
          position: 'fixed', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 8, padding: 20, zIndex: 1001, width: 400, maxWidth: '90vw',
        }}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
      >
        <h3 id="fansub-modal-title" style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>
          Fansub Preferences
        </h3>

        {isLoading ? (
          <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>Loading…</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label style={{ fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Preferred Groups (comma-separated)
              </span>
              <input
                type="text"
                value={preferred}
                onChange={(e) => setPreferred(e.target.value)}
                placeholder="SubsPlease, Erai-raws"
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  borderRadius: 4, padding: '6px 8px', color: 'var(--text)', fontSize: 12,
                }}
              />
            </label>

            <label style={{ fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Excluded Groups (comma-separated)
              </span>
              <input
                type="text"
                value={excluded}
                onChange={(e) => setExcluded(e.target.value)}
                placeholder="HorribleSubs, CoalGirls"
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  borderRadius: 4, padding: '6px 8px', color: 'var(--text)', fontSize: 12,
                }}
              />
            </label>

            <label style={{ fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Bonus Points (score)
              </span>
              <input
                type="number"
                value={bonus}
                min={0}
                max={999}
                onChange={(e) => setBonus(Math.max(0, Math.min(999, parseInt(e.target.value, 10) || 0)))}
                style={{
                  width: 80,
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  borderRadius: 4, padding: '6px 8px', color: 'var(--text)', fontSize: 12,
                }}
              />
            </label>

            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <button
                onClick={handleSave}
                disabled={setPrefs.isPending}
                style={{
                  background: 'var(--accent)', color: '#fff',
                  border: 'none', borderRadius: 4, padding: '6px 14px',
                  fontSize: 12, cursor: 'pointer', fontWeight: 600,
                }}
              >
                {setPrefs.isPending ? 'Saving…' : 'Save'}
              </button>
              {hasOverride && (
                <button
                  onClick={handleReset}
                  disabled={deletePrefs.isPending}
                  style={{
                    background: 'transparent', color: 'var(--text-muted)',
                    border: '1px solid var(--border)', borderRadius: 4,
                    padding: '6px 14px', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  {deletePrefs.isPending ? '…' : 'Reset to Global'}
                </button>
              )}
              <button
                onClick={onClose}
                style={{
                  marginLeft: 'auto', background: 'transparent',
                  color: 'var(--text-muted)', border: 'none',
                  fontSize: 12, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
