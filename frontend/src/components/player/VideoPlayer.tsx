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

      const instance = new SubtitleOctopus({
        video: videoRef.current,
        subUrl: getMediaStreamUrl(activeTrack.path),
        workerUrl: '/subtitles-octopus-worker.js',
        legacyWorkerUrl: '/subtitles-octopus-worker-legacy.js',
        onError: () => {
          // libass-wasm calls dispose() internally on error — clear ref so cleanup skips it
          octopusRef.current = null
        },
      })
      octopusRef.current = instance

      return () => {
        // Guard: libass-wasm may have already disposed on worker error
        if (octopusRef.current === instance) {
          instance.dispose()
          octopusRef.current = null
        }
      }
    }, [activeTrack])

    return (
      <video
        ref={videoRef}
        src={src}
        controls
        className="w-full h-full object-contain bg-black"
        style={{ maxHeight: '70vh' }}
        preload="metadata"
      />
    )
  },
)

VideoPlayer.displayName = 'VideoPlayer'
