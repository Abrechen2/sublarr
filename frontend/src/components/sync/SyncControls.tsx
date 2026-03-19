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
import { Timer, X } from 'lucide-react'
import { useAdvancedSync, useVideoChapters } from '@/hooks/useApi'
import { SyncPreview } from './SyncPreview'
import { OffsetTab } from './OffsetTab'
import { SpeedTab } from './SpeedTab'
import { FramerateTab } from './FramerateTab'
import { ChapterTab } from './ChapterTab'
import { StandardActions } from './StandardActions'
import { SyncTabBar } from './SyncTabBar'
import { toast } from '@/components/shared/Toast'
import type { SyncPreviewResult, SyncPreviewEvent, Chapter } from '@/lib/types'

type SyncOperation = 'offset' | 'speed' | 'framerate' | 'chapter'

interface SyncControlsProps {
  filePath: string
  videoPath?: string
  onSynced?: () => void
  onClose?: () => void
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
  const chapters: Chapter[] = chapterData?.chapters ?? []
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
      <SyncTabBar
        activeTab={activeTab}
        chapters={chapters}
        onTabChange={(tab) => {
          setActiveTab(tab)
          setPreviewEvents(null)
          setShowConfirm(false)
        }}
      />

      {/* Tab content */}
      <div className="px-4 py-3 space-y-3">
        {activeTab === 'offset' && (
          <OffsetTab offsetMs={offsetMs} onOffsetChange={setOffsetMs} />
        )}

        {activeTab === 'speed' && (
          <SpeedTab speedFactor={speedFactor} onSpeedChange={setSpeedFactor} />
        )}

        {activeTab === 'framerate' && (
          <FramerateTab
            inFps={inFps}
            outFps={outFps}
            onInFpsChange={setInFps}
            onOutFpsChange={setOutFps}
          />
        )}

        {activeTab === 'chapter' && (
          <ChapterTab
            chapters={chapters}
            selectedChapterId={selectedChapterId}
            offsetMs={offsetMs}
            isPending={syncMutation.isPending}
            showConfirm={showConfirm}
            onChapterSelect={setSelectedChapterId}
            onOffsetChange={setOffsetMs}
            onPreview={handleChapterPreview}
            onApply={handleChapterApply}
            onShowConfirm={() => setShowConfirm(true)}
            onCancelConfirm={() => setShowConfirm(false)}
          />
        )}

        {/* Action buttons (offset / speed / framerate tabs only) */}
        {activeTab !== 'chapter' && (
          <StandardActions
            isPending={syncMutation.isPending}
            showConfirm={showConfirm}
            onPreview={handlePreview}
            onApply={handleApply}
            onShowConfirm={() => setShowConfirm(true)}
            onCancelConfirm={() => setShowConfirm(false)}
          />
        )}

        {/* Preview results */}
        {previewEvents && (
          <SyncPreview events={previewEvents} operation={previewOperation} />
        )}
      </div>
    </div>
  )
}
