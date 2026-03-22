import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { SettingRow } from '@/components/shared/SettingRow'
import { useFfprobeStats, useFfprobeCleanup, useDbVacuum } from '@/hooks/useSystemApi'

// ─── CacheTab ─────────────────────────────────────────────────────────────────

export function CacheTab() {
  const { data: stats } = useFfprobeStats()
  const cleanup = useFfprobeCleanup()
  const vacuum = useDbVacuum()
  const [showVacuumConfirm, setShowVacuumConfirm] = useState(false)

  return (
    <div>
      {/* ffprobe cache */}
      <SettingRow
        label="ffprobe cache"
        description={`${stats?.count ?? '…'} entries cached`}
      >
        <button
          className="btn-secondary flex items-center gap-1.5 text-sm px-3 py-1.5 rounded"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            cursor: cleanup.isPending ? 'not-allowed' : 'pointer',
          }}
          onClick={() => cleanup.mutate()}
          disabled={cleanup.isPending}
          data-testid="ffprobe-cleanup-btn"
        >
          {cleanup.isPending && <Loader2 size={13} className="animate-spin" />}
          Clean up stale entries
        </button>
      </SettingRow>

      {/* DB vacuum */}
      <SettingRow
        label="Database vacuum"
        description="Reclaim unused space and defragment the SQLite database."
      >
        <button
          className="btn-secondary flex items-center gap-1.5 text-sm px-3 py-1.5 rounded"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            cursor: vacuum.isPending ? 'not-allowed' : 'pointer',
          }}
          onClick={() => setShowVacuumConfirm(true)}
          disabled={vacuum.isPending}
          data-testid="db-vacuum-btn"
        >
          {vacuum.isPending && <Loader2 size={13} className="animate-spin" />}
          Run VACUUM
        </button>
      </SettingRow>

      {/* Vacuum confirm dialog */}
      {showVacuumConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-sm mx-4 rounded-xl p-5 space-y-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
              Run database VACUUM?
            </h3>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              This may take a moment on large databases. The app remains available.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                className="btn-secondary text-sm px-3 py-1.5 rounded"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'transparent' }}
                onClick={() => setShowVacuumConfirm(false)}
                data-testid="vacuum-cancel-btn"
              >
                Cancel
              </button>
              <button
                className="text-sm px-3 py-1.5 rounded"
                style={{ backgroundColor: 'var(--accent)', color: 'white', border: 'none', cursor: 'pointer' }}
                onClick={() => { vacuum.mutate(); setShowVacuumConfirm(false) }}
                data-testid="vacuum-confirm-btn"
              >
                Run VACUUM
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
