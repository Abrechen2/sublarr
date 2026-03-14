import { useEffect, useRef, useImperativeHandle, forwardRef } from 'react'
import { PlayerSubtitleTrack } from '@/lib/types'
import { SubtitleOctopus, ISubtitleOctopus } from '@/lib/subtitleOctopus'

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
        subUrl: `/api/v1/media/stream?path=${encodeURIComponent(activeTrack.path)}`,
        workerUrl: '/subtitles-octopus-worker.js',
        legacyWorkerUrl: '/subtitles-octopus-worker-legacy.js',
      })
      octopusRef.current = instance

      return () => {
        instance.dispose()
        octopusRef.current = null
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
