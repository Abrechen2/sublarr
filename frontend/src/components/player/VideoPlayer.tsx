import { useEffect, useRef, useImperativeHandle, forwardRef } from 'react'
import type { PlayerSubtitleTrack } from '@/lib/types'
import { SubtitleOctopus, type ISubtitleOctopus } from '@/lib/subtitleOctopus'
import { getMediaStreamUrl } from '@/api/client'

export interface VideoPlayerHandle {
  seek: (seconds: number) => void
}

interface Props {
  src: string
  activeTrack: PlayerSubtitleTrack | null
}

export const VideoPlayer = forwardRef<VideoPlayerHandle, Props>(
  ({ src, activeTrack }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null)
    const octopusRef = useRef<ISubtitleOctopus | null>(null)

    // Expose seek() to parent
    useImperativeHandle(ref, () => ({
      seek(seconds: number) {
        if (videoRef.current) {
          videoRef.current.currentTime = seconds
        }
      },
    }))

    // Reinitialise SubtitleOctopus when activeTrack changes
    useEffect(() => {
      if (!videoRef.current) return

      // Dispose previous instance
      if (octopusRef.current) {
        octopusRef.current.dispose()
        octopusRef.current = null
      }

      if (!activeTrack) return

      const video = videoRef.current
      let cancelled = false

      // Fetch subtitle content via the API client (which includes auth headers/params).
      // We pass subContent instead of subUrl so the libass-wasm worker never needs to
      // make its own unauthenticated HTTP request.
      fetch(getMediaStreamUrl(activeTrack.path))
        .then((r) => r.text())
        .then((content) => {
          if (cancelled || !video) return

          const instance = new SubtitleOctopus({
            video,
            subContent: content,
            workerUrl: '/subtitles-octopus-worker.js',
            legacyWorkerUrl: '/subtitles-octopus-worker-legacy.js',
            onError: () => {
              octopusRef.current = null
            },
          })
          octopusRef.current = instance
        })
        .catch(() => {
          // Subtitle fetch failed — player continues without subtitles
        })

      return () => {
        cancelled = true
        if (octopusRef.current) {
          octopusRef.current.dispose()
          octopusRef.current = null
        }
      }
    }, [activeTrack])

    // The outer div must be `position: relative` so that libass-wasm inserts its
    // canvasParent sibling inside this wrapper rather than directly in the
    // PlayerModal's flex container. Without this, canvasParent becomes an extra
    // flex item which misaligns the canvas overlay over the video.
    return (
      <div className="relative w-full">
        <video
          ref={videoRef}
          src={src}
          controls
          className="block w-full"
          style={{ maxHeight: '70vh', objectFit: 'contain', backgroundColor: 'black' }}
          preload="metadata"
        />
      </div>
    )
  },
)

VideoPlayer.displayName = 'VideoPlayer'
