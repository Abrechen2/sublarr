/**
 * OCRExtractor - OCR extraction UI for embedded image subtitles.
 *
 * Allows users to extract text from DVD/Blu-ray image subtitles using OCR.
 * Displays preview frames and allows manual correction.
 */

import { useState, useCallback } from 'react'
import { useExtractOCR, usePreviewOCRFrame } from '@/hooks/useApi'
import { Loader2, Play, Eye, AlertCircle, CheckCircle } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import type { OCRExtractResult, OCRPreviewResult } from '@/api/client'

interface OCRExtractorProps {
  filePath: string
  streamIndex?: number
  language?: string
  onExtracted?: (text: string) => void
  className?: string
}

export function OCRExtractor({
  filePath,
  streamIndex = 0,
  language = 'eng',
  onExtracted,
  className = '',
}: OCRExtractorProps) {
  const [isExtracting, setIsExtracting] = useState(false)
  const [previewFrame, setPreviewFrame] = useState<OCRPreviewResult | null>(null)
  const [extractResult, setExtractResult] = useState<OCRExtractResult | null>(null)
  const [timestamp, setTimestamp] = useState(0)

  const extractMutation = useExtractOCR()
  const previewMutation = usePreviewOCRFrame()

  const handlePreview = useCallback(async () => {
    try {
      const result = await previewMutation.mutateAsync({
        filePath,
        timestamp,
        streamIndex,
      })
      setPreviewFrame(result)
    } catch (_err) {
      toast('Preview failed', 'error')
    }
  }, [filePath, timestamp, streamIndex, previewMutation])

  const handleExtract = useCallback(async () => {
    setIsExtracting(true)
    try {
      const result = await extractMutation.mutateAsync({
        filePath,
        streamIndex,
        language,
      })
      setExtractResult(result)
      onExtracted?.(result.text)
      toast(`OCR completed: ${result.successful_frames}/${result.frames} frames, quality: ${result.quality}%`, 'success')
    } catch (_err) {
      toast('OCR extraction failed', 'error')
    } finally {
      setIsExtracting(false)
    }
  }, [filePath, streamIndex, language, extractMutation, onExtracted])

  return (
    <div className={`bg-gray-900 rounded border border-gray-700 p-4 ${className}`}>
      <div className="mb-4">
        <h3 className="text-lg font-semibold mb-2">OCR Extraction</h3>
        <p className="text-sm text-gray-400">
          Extract text from embedded image subtitles (DVD, Blu-ray) using Tesseract OCR.
        </p>
      </div>

      {/* Preview Section */}
      <div className="mb-4">
        <label className="block text-sm font-medium mb-2">Preview Frame</label>
        <div className="flex gap-2 mb-2">
          <input
            type="number"
            value={timestamp}
            onChange={(e) => setTimestamp(parseFloat(e.target.value) || 0)}
            className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm"
            placeholder="Timestamp (seconds)"
            step="0.1"
          />
          <button
            onClick={handlePreview}
            className="px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded flex items-center gap-2"
            disabled={previewMutation.isPending}
          >
            {previewMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Eye className="w-4 h-4" />
            )}
            Preview
          </button>
        </div>

        {previewFrame && (
          <div className="mt-2 p-2 bg-gray-800 rounded">
            <div className="mb-2">
              <img
                src={`/api/v1/ocr/preview?file_path=${encodeURIComponent(filePath)}&timestamp=${timestamp}&download=true`}
                alt="OCR Preview"
                className="max-w-full h-auto rounded"
              />
            </div>
            {previewFrame.preview_text && (
              <div className="text-sm text-gray-300">
                <strong>Extracted text:</strong>
                <p className="mt-1 p-2 bg-gray-900 rounded">{previewFrame.preview_text}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Extract Section */}
      <div className="mb-4">
        <button
          onClick={handleExtract}
          className="w-full px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded flex items-center justify-center gap-2"
          disabled={isExtracting || extractMutation.isPending}
        >
          {isExtracting || extractMutation.isPending ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Extracting...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Extract OCR Text
            </>
          )}
        </button>
      </div>

      {/* Results */}
      {extractResult && (
        <div className="mt-4 p-3 bg-gray-800 rounded">
          <div className="flex items-center gap-2 mb-2">
            {extractResult.quality >= 70 ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : (
              <AlertCircle className="w-5 h-5 text-yellow-500" />
            )}
            <span className="font-medium">
              Quality: {extractResult.quality}% ({extractResult.successful_frames}/{extractResult.frames} frames)
            </span>
          </div>
          <div className="mt-2">
            <label className="block text-sm font-medium mb-1">Extracted Text:</label>
            <textarea
              readOnly
              value={extractResult.text}
              className="w-full h-32 px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm font-mono"
            />
          </div>
        </div>
      )}
    </div>
  )
}
