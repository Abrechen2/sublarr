/**
 * Timing sync UI with offset, speed, framerate, and chapter controls.
 *
 * Four operation tabs allow adjusting subtitle timing via:
 * - Offset: shift all timestamps by N milliseconds
 * - Speed: multiply timing by a speed factor
 * - Framerate: convert between frame rates (e.g., 23.976 -> 25)
 * - Chapter: apply an offset restricted to a single chapter's time range
 *
 * Preview mode shows before/after timestamps before applying changes.
 */

import { useState } from 'react'
import { Timer, X, Loader2, Check, Eye } from 'lucide-react'
import { useAdvancedSync, useVideoChapters } from '@/hooks/useApi'
import { SyncPreview } from './SyncPreview'
import { toast } from '@/components/shared/Toast'
import type { SyncPreviewResult, SyncPreviewEvent, Chapter } from '@/lib/types'

type SyncOperation = 'offset' | 'speed' | 'framerate' | 'chapter'

const COMMON_FRAMERATES = [23.976, 24, 25, 29.97, 30]

interface SyncControlsProps {
  filePath: string
  videoPath?: string
  onSynced?: () => void
  onClose?: () => void
}

function _formatMs(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function SyncControls({ filePath, videoPath, onSynced, onClose }: SyncControlsProps) {
  const [activeTab, setActiveTab] = useState<SyncOperation>('offset')
  const [offsetMs, setOffsetMs] = useState(0)
  const [speedFactor, setSpeedFactor] = useState(1.0)
  const [inFps, setInFps] = useState(23.976)
  const [outFps, setOutFps] = useState(25)
  const [previewEvents, setPreviewEvents] = useState<SyncPreviewEvent[] | null>(null)
  const [previewOperation, setPreviewOperation] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)

  const { data: chapterData } = useVideoChapters(videoPath)
  const chapters = chapterData?.chapters ?? []
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null)

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
      case 'chapter':
        return { offset_ms: offsetMs }
    }
  }

  const handlePreview = () => {
    setPreviewEvents(null)
    syncMutation.mutate(
      { filePath, operation: activeTab === 'chapter' ? 'offset' : activeTab, params: getParams(), preview: true },
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
      { filePath, operation: activeTab === 'chapter' ? 'offset' : activeTab, params: getParams(), preview: false },
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

  function handleChapterPreview() {
    const chapter = chapters.find((c: Chapter) => c.id === selectedChapterId)
    if (!chapter) return
    syncMutation.mutate(
      {
        filePath,
        operation: 'offset',
        params: { offset_ms: offsetMs },
        chapterRange: { start_ms: chapter.start_ms, end_ms: chapter.end_ms },
        preview: true,
      },
      {
        onSuccess: (data) => {
          const result = data as SyncPreviewResult
          setPreviewEvents(result.preview)
          setPreviewOperation(result.operation)
          setShowConfirm(false)
        },
        onError: () => {
          toast('Chapter preview failed', 'error')
        },
      },
    )
  }

  function handleChapterApply() {
    const chapter = chapters.find((c: Chapter) => c.id === selectedChapterId)
    if (!chapter) return
    syncMutation.mutate(
      {
        filePath,
        operation: 'offset',
        params: { offset_ms: offsetMs },
        chapterRange: { start_ms: chapter.start_ms, end_ms: chapter.end_ms },
        preview: false,
      },
      {
        onSuccess: () => {
          toast('Chapter sync applied successfully')
          setShowConfirm(false)
          setPreviewEvents(null)
          onSynced?.()
        },
        onError: () => {
          toast('Chapter sync failed', 'error')
          setShowConfirm(false)
        },
      },
    )
  }

  const standardTabs: { key: SyncOperation; label: string }[] = [
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
        {standardTabs.map((tab) => (
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
        {chapters.length > 0 && (
          <button
            onClick={() => {
              setActiveTab('chapter')
              setPreviewEvents(null)
              setShowConfirm(false)
            }}
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

        {activeTab === 'chapter' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
                Chapter
              </label>
              <select
                value={selectedChapterId ?? ''}
                onChange={(e) => setSelectedChapterId(e.target.value === '' ? null : Number(e.target.value))}
                style={{
                  width: '100%',
                  padding: '6px 8px',
                  borderRadius: 4,
                  border: '1px solid var(--border)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  fontSize: 13,
                }}
              >
                <option value="">Select chapter…</option>
                {chapters.map((ch: Chapter) => (
                  <option key={ch.id} value={ch.id}>
                    {ch.title} ({_formatMs(ch.start_ms)} – {_formatMs(ch.end_ms)})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
                Offset (ms)
              </label>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="number"
                  value={offsetMs}
                  onChange={(e) => setOffsetMs(Number(e.target.value))}
                  style={{
                    width: 90,
                    padding: '6px 8px',
                    borderRadius: 4,
                    border: '1px solid var(--border)',
                    background: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 13,
                    fontFamily: 'var(--font-mono)',
                  }}
                />
                {[-500, -100, 100, 500].map((delta) => (
                  <button
                    key={delta}
                    onClick={() => setOffsetMs((prev) => prev + delta)}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 4,
                      border: '1px solid var(--border)',
                      background: 'var(--bg-primary)',
                      color: 'var(--text-secondary)',
                      cursor: 'pointer',
                      fontSize: 12,
                    }}
                  >
                    {delta > 0 ? `+${delta}` : delta}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button
                disabled={selectedChapterId === null || syncMutation.isPending}
                onClick={handleChapterPreview}
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
                    onClick={handleChapterApply}
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
                  disabled={selectedChapterId === null || syncMutation.isPending}
                  onClick={() => setShowConfirm(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity"
                  style={{
                    backgroundColor: 'var(--accent)',
                    opacity: selectedChapterId === null || syncMutation.isPending ? 0.5 : 1,
                  }}
                >
                  <Check size={12} />
                  Apply
                </button>
              )}
            </div>
          </div>
        )}

        {/* Action buttons (offset / speed / framerate tabs only) */}
        {activeTab !== 'chapter' && (
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
        )}

        {/* Preview results */}
        {previewEvents && (
          <SyncPreview events={previewEvents} operation={previewOperation} />
        )}
      </div>
    </div>
  )
}
