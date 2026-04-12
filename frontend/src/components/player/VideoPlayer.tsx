import { useEffect, useRef, useImperativeHandle, forwardRef } from 'react'
import type { PlayerSubtitleTrack } from '@/lib/types'
import { SubtitleOctopus, type ISubtitleOctopus } from '@/lib/subtitleOctopus'
import { getMediaStreamUrl } from '@/api/client'
import { isSrt, srtToAss, isFirefox, assToVtt, srtToVtt } from '@/lib/subtitleUtils'

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
    const trackBlobRef = useRef<string | null>(null)

    // Expose seek() to parent
    useImperativeHandle(ref, () => ({
      seek(seconds: number) {
        if (videoRef.current) {
          videoRef.current.currentTime = seconds
        }
      },
    }))

    // Clean up any previously created blob URL
    const revokeTrackBlob = () => {
      if (trackBlobRef.current) {
        URL.revokeObjectURL(trackBlobRef.current)
        trackBlobRef.current = null
      }
    }

    // Firefox fallback: use native <track> with WebVTT since libass-wasm
    // createTrack/createTrackMem both crash in Firefox (ass_read_file returns NULL).
    // ASS styling features are lost, but subtitles render correctly.
    useEffect(() => {
      if (!isFirefox) return
      if (!videoRef.current) return

      // Remove any existing track elements
      revokeTrackBlob()
      const video = videoRef.current
      for (const track of Array.from(video.querySelectorAll('track'))) {
        track.remove()
      }

      if (!activeTrack) return

      const url = getMediaStreamUrl(activeTrack.path)
      const controller = new AbortController()

      const loadVtt = async () => {
        try {
          const resp = await fetch(url, { signal: controller.signal })
          const raw = await resp.text()
          const vtt = isSrt(raw) ? srtToVtt(raw) : assToVtt(raw)

          const blob = new Blob([vtt], { type: 'text/vtt' })
          const blobUrl = URL.createObjectURL(blob)
          trackBlobRef.current = blobUrl

          const track = document.createElement('track')
          track.kind = 'subtitles'
          track.label = 'Subtitles'
          track.srclang = 'und'
          track.src = blobUrl
          track.default = true
          video.appendChild(track)

          // Activate the track
          if (video.textTracks.length > 0) {
            video.textTracks[0].mode = 'showing'
          }
        } catch (err) {
          if ((err as Error).name !== 'AbortError') {
            // subtitle load failed silently
          }
        }
      }

      loadVtt()
      return () => {
        controller.abort()
      }
    }, [activeTrack])

    // Non-Firefox: use SubtitleOctopus (libass-wasm) for full ASS rendering.
    //
    // Manage subtitle track changes without restarting the worker.
    // Fetch content client-side so we can detect SRT and convert to ASS before
    // passing to libass-wasm (which only supports ASS/SSA).
    //
    // On first load: create instance with a placeholder ASS (so worker init succeeds),
    //   then immediately call setTrack() with the converted content.
    // On toggle-off: freeTrack() — worker stays alive (~instant).
    // On toggle-on: instance already exists → setTrack() with new content.
    // After onError clears the ref: fall through to create a fresh instance.
    useEffect(() => {
      if (isFirefox) return
      if (!videoRef.current) return

      if (!activeTrack) {
        octopusRef.current?.freeTrack()
        return
      }

      const video = videoRef.current
      const url = getMediaStreamUrl(activeTrack.path)
      const controller = new AbortController()

      const loadTrack = async () => {
        try {
          const resp = await fetch(url, { signal: controller.signal })
          const raw = await resp.text()
          const content = isSrt(raw) ? srtToAss(raw) : raw

          if (!octopusRef.current) {
            octopusRef.current = new SubtitleOctopus({
              video,
              subContent: WORKER_INIT_ASS,
              workerUrl: '/subtitles-octopus-worker.js',
              legacyWorkerUrl: '/subtitles-octopus-worker-legacy.js',
              onError: () => {
                octopusRef.current = null
              },
            })
          }
          octopusRef.current.setTrack(content)
        } catch (err) {
          if ((err as Error).name !== 'AbortError') {
            // subtitle load failed — worker stays alive without a track
          }
        }
      }

      loadTrack()
      return () => controller.abort()
    }, [activeTrack])

    // Dispose the worker when the video source changes or the component unmounts.
    useEffect(() => {
      return () => {
        octopusRef.current?.dispose()
        octopusRef.current = null
        revokeTrackBlob()
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
