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

// Minimal valid ASS used to initialize the worker without a real subtitle.
// The worker's onRuntimeInitialized always calls createTrack("/sub.ass"); passing
// a valid placeholder avoids a crash (ass_read_file returning NULL on an empty FS).
// The real track is loaded immediately after via setTrackByUrl(), which runs
// post-initialization through the worker's message buffer.
const WORKER_INIT_ASS =
  '[Script Info]\r\nScriptType: v4.00+\r\n\r\n[Events]\r\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\n'

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
    // On first load: create instance with a placeholder ASS (so worker init succeeds),
    //   then immediately queue setTrackByUrl() — processed after onRuntimeInitialized.
    // On toggle-off: freeTrack() — worker stays alive (~instant).
    // On toggle-on: instance already exists → setTrackByUrl() — worker fetches internally.
    // After onError clears the ref: fall through to create a fresh instance.
    useEffect(() => {
      if (!videoRef.current) return

      if (!activeTrack) {
        octopusRef.current?.freeTrack()
        return
      }

      const video = videoRef.current
      const url = getMediaStreamUrl(activeTrack.path)

      if (octopusRef.current) {
        octopusRef.current.setTrackByUrl(url)
      } else {
        const instance = new SubtitleOctopus({
          video,
          subContent: WORKER_INIT_ASS,
          workerUrl: '/subtitles-octopus-worker.js',
          legacyWorkerUrl: '/subtitles-octopus-worker-legacy.js',
          onError: () => {
            octopusRef.current = null
          },
        })
        instance.setTrackByUrl(url)
        octopusRef.current = instance
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
