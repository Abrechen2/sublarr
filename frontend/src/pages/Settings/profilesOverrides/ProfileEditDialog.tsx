import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

export type ProfileDialogMode = 'add' | 'edit' | 'delete'

export interface ProfileSubmitPayload {
  readonly id?: number
  readonly name: string
}

export interface ProfileEditDialogProps {
  readonly mode: ProfileDialogMode
  readonly initialId?: number
  readonly initialName?: string
  readonly impact?: { series_count: number; movies_count: number }
  readonly onClose: () => void
  readonly onSubmit: (payload: ProfileSubmitPayload) => Promise<void>
}

export function ProfileEditDialog(props: ProfileEditDialogProps) {
  const { t } = useTranslation('settings')
  const [name, setName] = useState(props.initialName ?? '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => setName(props.initialName ?? ''), [props.initialName])

  const handleSubmit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await props.onSubmit({ id: props.initialId, name: name.trim() })
      props.onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'unknown error')
    } finally {
      setSubmitting(false)
    }
  }

  const titles = {
    add: t('profiles_overrides.dialog.add_title', 'Add profile'),
    edit: t('profiles_overrides.dialog.edit_title', 'Edit profile'),
    delete: t('profiles_overrides.dialog.delete_title', 'Delete profile'),
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/65"
      onClick={(e) => {
        if (e.target === e.currentTarget) props.onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md flex flex-col rounded-lg overflow-hidden bg-[var(--bg-surface)] border border-[var(--border)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)] bg-[var(--bg-elevated)]">
          <h2 className="text-sm font-semibold m-0">{titles[props.mode]}</h2>
          <button
            onClick={props.onClose}
            aria-label="close"
            className="p-1 text-[var(--text-muted)] hover:text-[var(--error)]"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-4 py-3 flex flex-col gap-3">
          {props.mode !== 'delete' && (
            <label className="flex flex-col gap-1 text-xs">
              <span>{t('profiles_overrides.dialog.name_label', 'Name')}</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="px-2 py-1.5 rounded bg-[var(--bg-primary)] border border-[var(--border)]"
                autoFocus
              />
            </label>
          )}

          {props.mode === 'delete' && props.impact && (
            <p className="text-xs text-[var(--text-secondary)]">
              {`Deleting "${props.initialName}" will leave ${props.impact.series_count} series and ${props.impact.movies_count} movies without a profile.`}
            </p>
          )}

          {error && (
            <p role="alert" className="text-xs text-[var(--error)]">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 px-4 py-3 border-t border-[var(--border)] bg-[var(--bg-elevated)]">
          <button
            onClick={props.onClose}
            className="px-3 py-1.5 text-xs rounded border border-[var(--border)] text-[var(--text-muted)]"
          >
            {t('profiles_overrides.dialog.cancel', 'Cancel')}
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || (props.mode !== 'delete' && !name.trim())}
            className={
              props.mode === 'delete'
                ? 'px-3 py-1.5 text-xs rounded bg-[var(--error)] text-white disabled:opacity-50'
                : 'px-3 py-1.5 text-xs rounded bg-[var(--accent)] text-[var(--bg-primary)] disabled:opacity-50'
            }
          >
            {props.mode === 'delete'
              ? t('profiles_overrides.dialog.confirm_delete', 'Delete')
              : t('profiles_overrides.dialog.save', 'Save')}
          </button>
        </div>
      </div>
    </div>
  )
}
