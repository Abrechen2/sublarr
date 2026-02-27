/**
 * AudioWaveform - Waveform visualization component for subtitle timing adjustments.
 *
 * Displays audio waveform from video file with clickable timeline for precise
 * cue positioning. Integrates with SubtitleEditor for timing adjustments.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { useWaveform } from '@/hooks/useApi'
import { Loader2, ZoomIn, ZoomOut, Maximize2, Minimize2 } from 'lucide-react'

interface AudioWaveformProps {
  videoPath: string | null
  audioTrackIndex?: number
  currentTime?: number
  duration?: number
  onTimeSelect?: (time: number) => void
  className?: string
}

export function AudioWaveform({
  videoPath,
  audioTrackIndex,
  currentTime = 0,
  duration: _duration,
  onTimeSelect,
  className = '',
}: AudioWaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const { data: waveformData, isLoading, error } = useWaveform(
    null,
    videoPath,
    audioTrackIndex,
    !!videoPath,
  )

  // Draw waveform on canvas
  useEffect(() => {
    if (!waveformData || !canvasRef.current) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const container = containerRef.current
    if (!container) return

    const width = container.clientWidth
    const height = 200 // Fixed height for waveform
    canvas.width = width
    canvas.height = height

    // Clear canvas
    ctx.fillStyle = '#1a1a1a' // Dark background
    ctx.fillRect(0, 0, width, height)

    if (waveformData.data.length === 0) return

    // Calculate visible range based on zoom and pan
    const totalDuration = waveformData.duration
    const visibleDuration = totalDuration / zoom
    const startTime = Math.max(0, Math.min(pan, totalDuration - visibleDuration))
    const endTime = startTime + visibleDuration

    // Draw waveform
    ctx.strokeStyle = '#1DB8D4' // Sublarr teal
    ctx.lineWidth = 2
    ctx.beginPath()

    const centerY = height / 2
    const timeToX = (time: number) => {
      const ratio = (time - startTime) / visibleDuration
      return ratio * width
    }

    let pathStarted = false
    for (const point of waveformData.data) {
      if (point.time < startTime || point.time > endTime) continue

      const x = timeToX(point.time)
      const amplitude = point.amplitude
      const y = centerY - (amplitude - 0.5) * height * 0.8

      if (!pathStarted) {
        ctx.moveTo(x, y)
        pathStarted = true
      } else {
        ctx.lineTo(x, y)
      }
    }

    ctx.stroke()

    // Draw center line
    ctx.strokeStyle = '#666'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, centerY)
    ctx.lineTo(width, centerY)
    ctx.stroke()

    // Draw current time indicator
    if (currentTime >= startTime && currentTime <= endTime) {
      const x = timeToX(currentTime)
      ctx.strokeStyle = '#ff6b6b'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, height)
      ctx.stroke()
    }

    // Draw time markers
    ctx.fillStyle = '#999'
    ctx.font = '12px monospace'
    ctx.textAlign = 'center'
    const markerInterval = visibleDuration / 10
    for (let i = 0; i <= 10; i++) {
      const time = startTime + i * markerInterval
      if (time > endTime) break
      const x = timeToX(time)
      const timeStr = formatTime(time)
      ctx.fillText(timeStr, x, height - 5)
    }
  }, [waveformData, zoom, pan, currentTime, isFullscreen])


  // Fix 7: Redraw on container resize (e.g. entering/exiting fullscreen)
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new ResizeObserver(() => {
      if (!waveformData || !canvasRef.current) return
      const canvas = canvasRef.current
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      // Trigger redraw by updating canvas dimensions — React will re-run the drawing effect
      canvas.width = container.clientWidth
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [waveformData])

  // Handle canvas click for time selection
  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!waveformData || !canvasRef.current || !onTimeSelect) return

      const canvas = canvasRef.current
      const rect = canvas.getBoundingClientRect()
      const x = e.clientX - rect.left
      const width = canvas.width

      const totalDuration = waveformData.duration
      const visibleDuration = totalDuration / zoom
      const startTime = Math.max(0, Math.min(pan, totalDuration - visibleDuration))
      const ratio = x / width
      const selectedTime = startTime + ratio * visibleDuration

      onTimeSelect(Math.max(0, Math.min(selectedTime, totalDuration)))
    },
    [waveformData, zoom, pan, onTimeSelect],
  )

  // Zoom controls
  const handleZoomIn = () => setZoom((z) => Math.min(z * 1.5, 10))
  const handleZoomOut = () => setZoom((z) => Math.max(z / 1.5, 1))

  // Pan controls
  const handlePanLeft = () => {
    if (!waveformData) return
    const totalDuration = waveformData.duration
    const visibleDuration = totalDuration / zoom
    setPan((p) => Math.max(0, p - visibleDuration * 0.2))
  }

  const handlePanRight = () => {
    if (!waveformData) return
    const totalDuration = waveformData.duration
    const visibleDuration = totalDuration / zoom
    setPan((p) => Math.min(totalDuration - visibleDuration, p + visibleDuration * 0.2))
  }

  if (!videoPath) {
    return (
      <div className={`flex items-center justify-center h-48 bg-gray-900 rounded ${className}`}>
        <p className="text-gray-500">No video file selected</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className={`flex items-center justify-center h-48 bg-gray-900 rounded ${className}`}>
        <Loader2 className="w-8 h-8 animate-spin text-teal-500" />
        <span className="ml-2 text-gray-400">Generating waveform...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`flex items-center justify-center h-48 bg-gray-900 rounded ${className}`}>
        <p className="text-red-500">Failed to load waveform</p>
      </div>
    )
  }

  if (!waveformData) {
    return (
      <div className={`flex items-center justify-center h-48 bg-gray-900 rounded ${className}`}>
        <p className="text-gray-500">No waveform data available</p>
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className={`bg-gray-900 rounded border border-gray-700 ${isFullscreen ? 'fixed inset-4 z-50' : ''} ${className}`}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between p-2 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <button
            onClick={handleZoomOut}
            className="p-1 hover:bg-gray-800 rounded"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <span className="text-sm text-gray-400">{Math.round(zoom * 100)}%</span>
          <button
            onClick={handleZoomIn}
            className="p-1 hover:bg-gray-800 rounded"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={handlePanLeft}
            className="px-2 py-1 text-sm hover:bg-gray-800 rounded"
            title="Pan Left"
          >
            ←
          </button>
          <button
            onClick={handlePanRight}
            className="px-2 py-1 text-sm hover:bg-gray-800 rounded"
            title="Pan Right"
          >
            →
          </button>
        </div>
        <button
          onClick={() => setIsFullscreen(!isFullscreen)}
          className="p-1 hover:bg-gray-800 rounded"
          title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
        >
          {isFullscreen ? (
            <Minimize2 className="w-4 h-4" />
          ) : (
            <Maximize2 className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Canvas */}
      <div className="relative">
        <canvas
          ref={canvasRef}
          onClick={handleCanvasClick}
          className="w-full cursor-crosshair"
          style={{ height: '200px' }}
        />
      </div>

      {/* Info */}
      <div className="p-2 text-xs text-gray-500 border-t border-gray-700">
        Duration: {formatTime(waveformData.duration)} | Samples: {waveformData.samples} |{' '}
        {waveformData.sample_rate} Hz
      </div>
    </div>
  )
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.floor((seconds % 1) * 1000)

  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`
  }
  return `${m}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`
}
