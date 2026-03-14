import { useRef, useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { PlayerSubtitleTrack } from '@/lib/types'
import { VideoPlayer, VideoPlayerHandle } from './VideoPlayer'
import { SubtitleTrackSelector } from './SubtitleTrackSelector'
import { getMediaStreamUrl } from '@/api/client'

interface Props {
  videoPath: string
  subtitleTracks: PlayerSubtitleTrack[]
  initialTrackIndex?: number
  onClose: () => void
  /** Called with a seek function so parent/sibling can seek the player */
  onSeekReady?: (seekFn: (seconds: number) => void) => void
}

export function PlayerModal({
  videoPath,
  subtitleTracks,
  initialTrackIndex = 0,
  onClose,
  onSeekReady,
}: Props) {
  const [activeIndex, setActiveIndex] = useState<number | null>(
    subtitleTracks.length > 0 ? initialTrackIndex : null,
  )
  const playerRef = useRef<VideoPlayerHandle>(null)

  const activeTrack = activeIndex !== null ? (subtitleTracks[activeIndex] ?? null) : null
  const streamUrl = getMediaStreamUrl(videoPath)

  // Expose seek to parent after mount
  useEffect(() => {
    if (!onSeekReady) return
    onSeekReady((seconds) => playerRef.current?.seek(seconds))
  }, [onSeekReady])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="player-modal-title"
        className="relative flex flex-col bg-[var(--bg-surface)] rounded-lg overflow-hidden shadow-2xl"
        style={{ width: 'min(90vw, 1200px)', maxHeight: '90vh' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-muted)]">
          <h2 id="player-modal-title" className="text-sm font-medium text-[var(--text-primary)] truncate">
            Preview
          </h2>
          <div className="flex items-center gap-4">
            {subtitleTracks.length > 0 && (
              <SubtitleTrackSelector
                tracks={subtitleTracks}
                activeIndex={activeIndex}
                onChange={setActiveIndex}
              />
            )}
            <button
              autoFocus
              onClick={onClose}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
              aria-label="Close player"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Player */}
        <div className="flex-1 bg-black flex items-center justify-center overflow-hidden">
          <VideoPlayer
            ref={playerRef}
            src={streamUrl}
            activeTrack={activeTrack}
          />
        </div>
      </div>
    </div>,
    document.body,
  )
}
