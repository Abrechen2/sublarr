/**
 * VideoPlayer - Browser-based HTML5 video player with subtitle support.
 *
 * Features:
 * - HLS streaming for large files
 * - ASS/SRT subtitle rendering via WebVTT
 * - Timeline with subtitle cues
 * - Keyboard shortcuts
 * - Wellenform integration
 */

import { useRef, useEffect, useState, useCallback } from 'react'
import { Play, Pause, Volume2, VolumeX, Maximize2, Minimize2, SkipBack, SkipForward } from 'lucide-react'

interface VideoPlayerProps {
  videoPath: string
  subtitlePath?: string
  currentTime?: number
  onTimeUpdate?: (time: number) => void
  onSubtitleCue?: (cue: { start: number; end: number; text: string } | null) => void
  className?: string
}

export function VideoPlayer({
  videoPath,
  subtitlePath,
  currentTime,
  onTimeUpdate,
  onSubtitleCue,
  className = '',
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [volume, setVolume] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [duration, setDuration] = useState(0)
  const [currentTimeState, setCurrentTimeState] = useState(0)

  // HLS stream URL
  const hlsUrl = `/api/v1/video/stream?file_path=${encodeURIComponent(videoPath)}&format=hls`

  // WebVTT subtitle URL
  const subtitleUrl = subtitlePath
    ? `/api/v1/video/subtitles?file_path=${encodeURIComponent(subtitlePath)}&format=vtt`
    : undefined

  // Handle time update
  const handleTimeUpdate = useCallback(() => {
    if (videoRef.current) {
      const time = videoRef.current.currentTime
      setCurrentTimeState(time)
      onTimeUpdate?.(time)

      // Check for subtitle cues
      if (subtitlePath && videoRef.current.textTracks.length > 0) {
        const track = videoRef.current.textTracks[0]
        if (track.activeCues && track.activeCues.length > 0) {
          const cue = track.activeCues[0] as VTTCue
          onSubtitleCue?.({
            start: cue.startTime,
            end: cue.endTime,
            text: cue.text,
          })
        } else {
          onSubtitleCue?.(null)
        }
      }
    }
  }, [onTimeUpdate, onSubtitleCue, subtitlePath])

  // Handle play/pause
  // Fix 2: Read actual video element state to avoid stale closure on isPlaying
  const togglePlay = useCallback(() => {
    if (!videoRef.current) return
    if (videoRef.current.paused) {
      videoRef.current.play()
    } else {
      videoRef.current.pause()
    }
  }, [])

  // Handle volume
  const handleVolumeChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newVolume = parseFloat(e.target.value)
    setVolume(newVolume)
    if (videoRef.current) {
      videoRef.current.volume = newVolume
      setIsMuted(newVolume === 0)
    }
  }, [])

  // Handle mute
  const toggleMute = useCallback(() => {
    if (videoRef.current) {
      videoRef.current.muted = !isMuted
      setIsMuted(!isMuted)
    }
  }, [isMuted])

  // Handle seek
  const handleSeek = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value)
    if (videoRef.current) {
      videoRef.current.currentTime = time
      setCurrentTimeState(time)
    }
  }, [])

  // Handle fullscreen
  const toggleFullscreen = useCallback(() => {
    if (!videoRef.current) return

    if (!isFullscreen) {
      if (videoRef.current.requestFullscreen) {
        videoRef.current.requestFullscreen()
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen()
      }
    }
    setIsFullscreen(!isFullscreen)
  }, [isFullscreen])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!videoRef.current) return

      switch (e.key) {
        case ' ':
          e.preventDefault()
          togglePlay()
          break
        case 'ArrowLeft':
          e.preventDefault()
          if (videoRef.current) {
            videoRef.current.currentTime = Math.max(0, videoRef.current.currentTime - 10)
          }
          break
        case 'ArrowRight':
          e.preventDefault()
          if (videoRef.current) {
            videoRef.current.currentTime = Math.min(
              duration,
              videoRef.current.currentTime + 10,
            )
          }
          break
        case 'ArrowUp':
          e.preventDefault()
          if (videoRef.current) {
            videoRef.current.volume = Math.min(1, videoRef.current.volume + 0.1)
            setVolume(videoRef.current.volume)
          }
          break
        case 'ArrowDown':
          e.preventDefault()
          if (videoRef.current) {
            videoRef.current.volume = Math.max(0, videoRef.current.volume - 0.1)
            setVolume(videoRef.current.volume)
          }
          break
        case 'f':
          e.preventDefault()
          toggleFullscreen()
          break
        case 'm':
          e.preventDefault()
          toggleMute()
          break
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [togglePlay, toggleFullscreen, toggleMute, duration])

  // Sync external currentTime
  useEffect(() => {
    if (currentTime !== undefined && videoRef.current) {
      if (Math.abs(videoRef.current.currentTime - currentTime) > 0.5) {
        videoRef.current.currentTime = currentTime
      }
    }
  }, [currentTime])

  // Format time
  const formatTime = (seconds: number): string => {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    if (h > 0) {
      return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    }
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div className={`bg-black rounded overflow-hidden ${className}`}>
      <video
        ref={videoRef}
        className="w-full h-auto"
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={() => {
          if (videoRef.current) {
            setDuration(videoRef.current.duration)
          }
        }}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
      >
        <source src={hlsUrl} type="application/vnd.apple.mpegurl" />
        {subtitleUrl && (
          <track kind="subtitles" srcLang="en" src={subtitleUrl} default />
        )}
        Your browser does not support the video tag.
      </video>

      {/* Controls */}
      <div className="bg-gray-900 p-4">
        {/* Progress bar */}
        <div className="mb-4">
          <input
            type="range"
            min="0"
            max={duration || 0}
            value={currentTimeState}
            onChange={handleSeek}
            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>{formatTime(currentTimeState)}</span>
            <span>{formatTime(duration)}</span>
          </div>
        </div>

        {/* Control buttons */}
        <div className="flex items-center gap-4">
          <button
            onClick={togglePlay}
            className="p-2 hover:bg-gray-800 rounded"
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
          </button>

          <button
            onClick={() => {
              if (videoRef.current) {
                videoRef.current.currentTime = Math.max(0, videoRef.current.currentTime - 10)
              }
            }}
            className="p-2 hover:bg-gray-800 rounded"
            title="Skip back 10s"
          >
            <SkipBack className="w-5 h-5" />
          </button>

          <button
            onClick={() => {
              if (videoRef.current) {
                videoRef.current.currentTime = Math.min(
                  duration,
                  videoRef.current.currentTime + 10,
                )
              }
            }}
            className="p-2 hover:bg-gray-800 rounded"
            title="Skip forward 10s"
          >
            <SkipForward className="w-5 h-5" />
          </button>

          <div className="flex items-center gap-2 flex-1">
            <button
              onClick={toggleMute}
              className="p-2 hover:bg-gray-800 rounded"
              title={isMuted ? 'Unmute' : 'Mute'}
            >
              {isMuted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
            </button>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={volume}
              onChange={handleVolumeChange}
              className="w-24 h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          <button
            onClick={toggleFullscreen}
            className="p-2 hover:bg-gray-800 rounded"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? (
              <Minimize2 className="w-5 h-5" />
            ) : (
              <Maximize2 className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
