/**
 * Normalize a version or git tag to exactly one leading "v".
 * The backend returns GitHub tags verbatim (e.g. "v1.2.0"); some call
 * sites prepend their own "v", producing "vv1.2.0". This collapses that.
 */
export function formatVersion(raw: string | null | undefined): string {
  if (!raw) return ''
  return 'v' + String(raw).replace(/^v+/, '')
}
