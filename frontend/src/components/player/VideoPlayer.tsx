import { useEffect, useRef, useImperativeHandle, forwardRef } from 'react'
import Plyr from 'plyr'
import 'plyr/dist/plyr.css'
import { PlayerSubtitleTrack } from '@/lib/types'
import { SubtitleOctopus, ISubtitleOctopus } from '@/lib/subtitleOctopus'

export interface VideoPlayerHandle {
  seek: (seconds: number) => void
}

interface Props {
  src: string
  activeTrack: PlayerSubtitleTrack | null
}

const PLYR_CONTROLS = [
  'play-large',
  'play',
  'progress',
  'current-time',
  'mute',
  'volume',
  'settings',
  'fullscreen',
]

export const VideoPlayer = forwardRef<VideoPlayerHandle, Props>(
  ({ src, activeTrack }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null)
    const plyrRef = useRef<Plyr | null>(null)
    const octopusRef = useRef<ISubtitleOctopus | null>(null)

    // Expose seek() to parent via Plyr's currentTime setter
    useImperativeHandle(ref, () => ({
      seek(seconds: number) {
        if (plyrRef.current) {
          plyrRef.current.currentTime = seconds
        }
      },
    }))

    // Initialise Plyr once on mount, destroy on unmount
    useEffect(() => {
      if (!videoRef.current) return

      const player = new Plyr(videoRef.current, {
        controls: PLYR_CONTROLS,
        keyboard: { focused: true, global: false },
        tooltips: { controls: false, seek: true },
        // Subtitle rendering is handled by SubtitleOctopus (libass-wasm),
        // so Plyr's built-in caption support is disabled.
        captions: { active: false },
        clickToPlay: true,
        disableContextMenu: false,
      })
      plyrRef.current = player

      return () => {
        player.destroy()
        plyrRef.current = null
      }
    }, [])

    // Reinitialise SubtitleOctopus when activeTrack changes.
    // We pass videoRef.current (the underlying <video> element) directly —
    // Plyr wraps it but does not replace it, so SubtitleOctopus attaches
    // its canvas overlay to the same element Plyr already controls.
    useEffect(() => {
      if (!videoRef.current) return

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
        className="w-full h-full"
        preload="metadata"
        playsInline
      />
    )
  },
)

VideoPlayer.displayName = 'VideoPlayer'
