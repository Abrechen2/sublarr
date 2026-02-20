/**
 * Timing sync UI with offset, speed, and framerate controls.
 *
 * Three operation tabs allow adjusting subtitle timing via:
 * - Offset: shift all timestamps by N milliseconds
 * - Speed: multiply timing by a speed factor
 * - Framerate: convert between frame rates (e.g., 23.976 -> 25)
 *
 * Preview mode shows before/after timestamps before applying changes.
 */

import { useState } from 'react'
import { Timer, X, Loader2, Check, Eye } from 'lucide-react'
import { useAdvancedSync } from '@/hooks/useApi'
import { SyncPreview } from './SyncPreview'
import { toast } from '@/components/shared/Toast'
import type { SyncPreviewResult, SyncPreviewEvent } from '@/lib/types'

type SyncOperation = 'offset' | 'speed' | 'framerate'

const COMMON_FRAMERATES = [23.976, 24, 25, 29.97, 30]

interface SyncControlsProps {
  filePath: string
  onSynced?: () => void
  onClose?: () => void
}

export function SyncControls({ filePath, onSynced, onClose }: SyncControlsProps) {
  const [activeTab, setActiveTab] = useState<SyncOperation>('offset')
  const [offsetMs, setOffsetMs] = useState(0)
  const [speedFactor, setSpeedFactor] = useState(1.0)
  const [inFps, setInFps] = useState(23.976)
  const [outFps, setOutFps] = useState(25)
  const [previewEvents, setPreviewEvents] = useState<SyncPreviewEvent[] | null>(null)
  const [previewOperation, setPreviewOperation] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)

  const syncMutation = useAdvancedSync()

  const fileName = filePath.split('/').pop() ?? filePath

  const getParams = (): Record<string, number> => {
    switch (activeTab) {
      case 'offset':
        return { offset_ms: offsetMs }
      case 'speed':
        return { speed_factor: speedFactor }
      case 'framerate':
        return { in_fps: inFps, out_fps: outFps }
    }
  }

  const handlePreview = () => {
    setPreviewEvents(null)
    syncMutation.mutate(
      { filePath, operation: activeTab, params: getParams(), preview: true },
      {
        onSuccess: (data) => {
          const result = data as SyncPreviewResult
          setPreviewEvents(result.preview)
          setPreviewOperation(result.operation)
        },
        onError: () => {
          toast('Preview failed', 'error')
        },
      }
    )
  }

  const handleApply = () => {
    syncMutation.mutate(
      { filePath, operation: activeTab, params: getParams(), preview: false },
      {
        onSuccess: () => {
          toast('Sync applied successfully')
          setPreviewEvents(null)
          setShowConfirm(false)
          onSynced?.()
        },
        onError: () => {
          toast('Sync failed', 'error')
          setShowConfirm(false)
        },
      }
    )
  }

  const tabs: { key: SyncOperation; label: string }[] = [
    { key: 'offset', label: 'Offset' },
    { key: 'speed', label: 'Speed' },
    { key: 'framerate', label: 'Framerate' },
  ]

  return (
    <div
      className="rounded-lg overflow-hidden flex flex-col"
      style={{ border: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2.5 shrink-0"
        style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      >
        <div className="flex items-center gap-2">
          <Timer size={16} style={{ color: 'var(--accent)' }} />
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            Sync Timing
          </span>
          <span className="text-xs truncate max-w-[200px]" style={{ color: 'var(--text-muted)' }}>
            {fileName}
          </span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="rounded p-1.5 transition-colors"
            style={{ color: 'var(--text-muted)' }}
            title="Close"
            onMouseEnter={(e) => {
              e.currentTarget.style.color = 'var(--error)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'var(--text-muted)'
            }}
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Tab buttons */}
      <div
        className="flex gap-1 px-4 py-2"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => {
              setActiveTab(tab.key)
              setPreviewEvents(null)
              setShowConfirm(false)
            }}
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
      </div>

      {/* Tab content */}
      <div className="px-4 py-3 space-y-3">
        {activeTab === 'offset' && (
          <div className="space-y-2">
            <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
              Offset (milliseconds)
            </label>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setOffsetMs((v) => v - 100)}
                className="px-2 py-1 rounded text-xs font-bold"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-secondary)',
                }}
              >
                -100
              </button>
              <input
                type="number"
                value={offsetMs}
                onChange={(e) => setOffsetMs(Number(e.target.value))}
                className="flex-1 px-3 py-1.5 rounded text-sm tabular-nums text-center"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                }}
              />
              <button
                onClick={() => setOffsetMs((v) => v + 100)}
                className="px-2 py-1 rounded text-xs font-bold"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-secondary)',
                }}
              >
                +100
              </button>
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>ms</span>
            </div>
          </div>
        )}

        {activeTab === 'speed' && (
          <div className="space-y-2">
            <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
              Speed Factor
            </label>
            <div className="space-y-2">
              <input
                type="number"
                value={speedFactor}
                onChange={(e) => setSpeedFactor(Number(e.target.value))}
                min={0.5}
                max={2.0}
                step={0.01}
                className="w-full px-3 py-1.5 rounded text-sm tabular-nums text-center"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                }}
              />
              <div className="flex gap-2">
                {[0.95, 1.0, 1.05].map((preset) => (
                  <button
                    key={preset}
                    onClick={() => setSpeedFactor(preset)}
                    className="flex-1 px-2 py-1 rounded text-xs font-medium tabular-nums transition-colors"
                    style={{
                      backgroundColor: speedFactor === preset ? 'var(--accent-bg)' : 'var(--bg-primary)',
                      border: `1px solid ${speedFactor === preset ? 'var(--accent-dim)' : 'var(--border)'}`,
                      color: speedFactor === preset ? 'var(--accent)' : 'var(--text-secondary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {preset.toFixed(2)}x
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'framerate' && (
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium block mb-1" style={{ color: 'var(--text-secondary)' }}>
                  Source FPS
                </label>
                <select
                  value={inFps}
                  onChange={(e) => setInFps(Number(e.target.value))}
                  className="w-full px-3 py-1.5 rounded text-sm"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {COMMON_FRAMERATES.map((fps) => (
                    <option key={fps} value={fps}>
                      {fps}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium block mb-1" style={{ color: 'var(--text-secondary)' }}>
                  Target FPS
                </label>
                <select
                  value={outFps}
                  onChange={(e) => setOutFps(Number(e.target.value))}
                  className="w-full px-3 py-1.5 rounded text-sm"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {COMMON_FRAMERATES.map((fps) => (
                    <option key={fps} value={fps}>
                      {fps}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={handlePreview}
            disabled={syncMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
            }}
          >
            {syncMutation.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Eye size={12} />
            )}
            Preview
          </button>

          {showConfirm ? (
            <div className="flex items-center gap-2">
              <span className="text-xs" style={{ color: 'var(--warning)' }}>
                This will modify the file. A backup will be created.
              </span>
              <button
                onClick={handleApply}
                disabled={syncMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {syncMutation.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Check size={12} />
                )}
                Confirm
              </button>
              <button
                onClick={() => setShowConfirm(false)}
                className="px-2 py-1.5 rounded text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowConfirm(true)}
              disabled={syncMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity"
              style={{
                backgroundColor: 'var(--accent)',
                opacity: syncMutation.isPending ? 0.5 : 1,
              }}
            >
              <Check size={12} />
              Apply
            </button>
          )}
        </div>

        {/* Preview results */}
        {previewEvents && (
          <SyncPreview events={previewEvents} operation={previewOperation} />
        )}
      </div>
    </div>
  )
}
