/**
 * SpellCheckPanel - Spell checking UI component for subtitle editor.
 *
 * Displays spelling errors with suggestions and allows auto-correction.
 * Integrates with SubtitleEditor for real-time spell checking.
 */

import { useState, useEffect, useCallback } from 'react'
import { useSpellCheck, useSpellDictionaries } from '@/hooks/useApi'
import { CheckCircle, X, AlertCircle, Loader2, RefreshCw, Wand2 } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import type { SpellCheckError } from '@/api/client'

interface SpellCheckPanelProps {
  content: string
  filePath?: string
  language?: string
  customWords?: string[]
  onWordReplace?: (oldWord: string, newWord: string, position: number) => void
  className?: string
}

export function SpellCheckPanel({
  content,
  filePath,
  language = 'en_US',
  customWords,
  onWordReplace,
  className = '',
}: SpellCheckPanelProps) {
  const [errors, setErrors] = useState<SpellCheckError[]>([])
  const [isChecking, setIsChecking] = useState(false)
  const [selectedError, setSelectedError] = useState<SpellCheckError | null>(null)

  const spellCheckMutation = useSpellCheck()
  const { data: dictionaries } = useSpellDictionaries()

  // Run spell check when content changes (debounced)
  useEffect(() => {
    if (!content) {
      setErrors([])
      return
    }

    const timer = setTimeout(() => {
      runSpellCheck()
    }, 1000) // 1 second debounce

    return () => clearTimeout(timer)
  }, [content, filePath, language, customWords])

  const runSpellCheck = useCallback(async () => {
    if (!content) {
      setErrors([])
      return
    }

    setIsChecking(true)
    try {
      const result = await spellCheckMutation.mutateAsync({
        filePath,
        content,
        language,
        customWords,
      })
      setErrors(result.errors || [])
    } catch (err) {
      toast('Spell check failed', 'error')
      setErrors([])
    } finally {
      setIsChecking(false)
    }
  }, [content, filePath, language, customWords, spellCheckMutation])

  const handleReplace = useCallback(
    (error: SpellCheckError, suggestion: string) => {
      if (onWordReplace) {
        onWordReplace(error.word, suggestion, error.position)
      }
      // Remove error from list
      setErrors((prev) => prev.filter((e) => e !== error))
      toast(`Replaced "${error.word}" with "${suggestion}"`, 'success')
    },
    [onWordReplace],
  )

  const handleIgnore = useCallback((error: SpellCheckError) => {
    // Remove error from list (temporary, will reappear on next check)
    setErrors((prev) => prev.filter((e) => e !== error))
  }, [])

  if (errors.length === 0 && !isChecking) {
    return (
      <div className={`p-4 bg-gray-900 rounded border border-gray-700 ${className}`}>
        <div className="flex items-center gap-2 text-green-500">
          <CheckCircle className="w-5 h-5" />
          <span className="text-sm font-medium">No spelling errors found</span>
        </div>
      </div>
    )
  }

  return (
    <div className={`bg-gray-900 rounded border border-gray-700 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          {isChecking ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin text-teal-500" />
              <span className="text-sm text-gray-400">Checking spelling...</span>
            </>
          ) : (
            <>
              <AlertCircle className="w-4 h-4 text-yellow-500" />
              <span className="text-sm font-medium">
                {errors.length} error{errors.length !== 1 ? 's' : ''} found
              </span>
            </>
          )}
        </div>
        <button
          onClick={runSpellCheck}
          className="p-1 hover:bg-gray-800 rounded"
          title="Re-check spelling"
          disabled={isChecking}
        >
          <RefreshCw className={`w-4 h-4 ${isChecking ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Error List */}
      {errors.length > 0 && (
        <div className="max-h-96 overflow-y-auto">
          {errors.map((error, index) => (
            <div
              key={index}
              className={`p-3 border-b border-gray-700 last:border-b-0 hover:bg-gray-800 cursor-pointer ${
                selectedError === error ? 'bg-gray-800' : ''
              }`}
              onClick={() => setSelectedError(error === selectedError ? null : error)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-red-400">{error.word}</span>
                    {error.line && (
                      <span className="text-xs text-gray-500">Line {error.line}</span>
                    )}
                  </div>
                  {error.text && (
                    <p className="text-xs text-gray-400 truncate">{error.text}</p>
                  )}
                </div>
                {error.suggestions.length > 0 && (
                  <div className="flex items-center gap-1">
                    {error.suggestions.slice(0, 3).map((suggestion, i) => (
                      <button
                        key={i}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleReplace(error, suggestion)
                        }}
                        className="px-2 py-1 text-xs bg-teal-500/20 hover:bg-teal-500/30 text-teal-400 rounded"
                        title={`Replace with "${suggestion}"`}
                      >
                        {suggestion}
                      </button>
                    ))}
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleIgnore(error)
                      }}
                      className="p-1 hover:bg-gray-700 rounded"
                      title="Ignore"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
