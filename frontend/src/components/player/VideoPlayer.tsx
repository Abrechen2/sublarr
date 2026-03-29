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

    // Create the SubtitleOctopus worker once per video src.
    // The worker is kept alive so track switches use freeTrack()/setTrack()
    // instead of a full worker restart (~10–20 s due to WASM init + font load).
    useEffect(() => {
      if (!videoRef.current) return

      const instance = new SubtitleOctopus({
        video: videoRef.current,
        workerUrl: '/subtitles-octopus-worker.js',
        legacyWorkerUrl: '/subtitles-octopus-worker-legacy.js',
        onError: () => {
          octopusRef.current = null
        },
      })
      octopusRef.current = instance

      return () => {
        instance.dispose()
        octopusRef.current = null
      }
    }, [src])

    // Switch subtitle track without restarting the worker.
    // Fetch content on the main thread (authenticated) then hand it to the worker.
    useEffect(() => {
      const octopus = octopusRef.current
      if (!octopus) return

      if (!activeTrack) {
        octopus.freeTrack()
        return
      }

      let cancelled = false

      fetch(getMediaStreamUrl(activeTrack.path))
        .then((r) => r.text())
        .then((content) => {
          if (cancelled) return
          octopusRef.current?.setTrack(content)
        })
        .catch(() => {
          // Subtitle fetch failed — player continues without subtitles
        })

      return () => {
        cancelled = true
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
