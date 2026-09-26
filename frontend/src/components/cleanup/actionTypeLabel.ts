/** Readable label for a cleanup_history `action_type`; the raw type when none is defined. */
type Translate = (key: string, opts?: { defaultValue?: string }) => string

export function actionTypeLabel(t: Translate, actionType: string): string {
  return t(`cleanup.history.action_types.${actionType}`, { defaultValue: actionType })
}
