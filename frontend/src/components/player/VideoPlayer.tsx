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

    // Manage subtitle track changes without restarting the worker.
    //
    // On first load: create instance with subContent so the worker starts hot.
    // On toggle-off: freeTrack() — worker stays alive (~instant).
    // On toggle-on: instance already exists → setTrack() — just the HTTP fetch (~100 ms).
    // After onError clears the ref: fall through to create a fresh instance.
    useEffect(() => {
      if (!videoRef.current) return

      if (!activeTrack) {
        octopusRef.current?.freeTrack()
        return
      }

      const video = videoRef.current
      let cancelled = false

      fetch(getMediaStreamUrl(activeTrack.path))
        .then((r) => r.text())
        .then((content) => {
          if (cancelled) return

          if (octopusRef.current) {
            octopusRef.current.setTrack(content)
          } else {
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
          }
        })
        .catch(() => {
          // Subtitle fetch failed — player continues without subtitles
        })

      return () => {
        cancelled = true
      }
    }, [activeTrack])

    // Dispose the worker when the video source changes or the component unmounts.
    useEffect(() => {
      return () => {
        octopusRef.current?.dispose()
        octopusRef.current = null
      }
    }, [src])

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
