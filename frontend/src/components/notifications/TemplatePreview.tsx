import { useEffect, useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { usePreviewNotificationTemplate } from '@/hooks/useApi'
import { Bell, Loader2 } from 'lucide-react'

interface TemplatePreviewProps {
  templateId: number | null
  titleTemplate?: string
  bodyTemplate?: string
}

export function TemplatePreview({ templateId, titleTemplate, bodyTemplate }: TemplatePreviewProps) {
  const { t } = useTranslation('settings')
  const preview = usePreviewNotificationTemplate()
  const [renderedTitle, setRenderedTitle] = useState<string>('')
  const [renderedBody, setRenderedBody] = useState<string>('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounced preview refresh
  useEffect(() => {
    if (!templateId) return

    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }

    debounceRef.current = setTimeout(() => {
      preview.mutate(templateId, {
        onSuccess: (data) => {
          setRenderedTitle(data.title)
          setRenderedBody(data.body)
        },
      })
    }, 500)

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId, titleTemplate, bodyTemplate])

  if (!templateId) {
    return (
      <div
        className="rounded-lg p-4 text-center"
        style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
      >
        <Bell size={24} className="mx-auto mb-2" style={{ color: 'var(--text-muted)' }} />
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {t('notifications.templates.previewHint', 'Save a template to see its preview.')}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
        {t('notifications.templates.preview', 'Preview')}
      </h4>
      <div
        className="rounded-lg overflow-hidden"
        style={{ border: '1px solid var(--border)' }}
      >
        {/* Notification Header */}
        <div
          className="px-4 py-2.5 flex items-center gap-2"
          style={{ backgroundColor: 'var(--accent)', color: 'white' }}
        >
          <Bell size={14} />
          <span className="text-sm font-medium">
            {preview.isPending ? (
              <Loader2 size={14} className="animate-spin inline" />
            ) : (
              renderedTitle || 'Notification Title'
            )}
          </span>
        </div>
        {/* Notification Body */}
        <div
          className="px-4 py-3"
          style={{ backgroundColor: 'var(--bg-surface)' }}
        >
          <p className="text-sm whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>
            {renderedBody || 'Notification body will appear here...'}
          </p>
        </div>
        {/* Footer */}
        <div
          className="px-4 py-1.5 text-[10px]"
          style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}
        >
          Sublarr Notification Preview
        </div>
      </div>
    </div>
  )
}
