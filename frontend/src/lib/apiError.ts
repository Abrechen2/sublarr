/**
 * Read the message the API sent with a failed request.
 *
 * Sublarr's error handler answers with `{"error": "..."}` and a meaningful
 * status — a duplicate profile name comes back as 409 with the name in the
 * text. Handlers that ignore the rejection value replace all of that with a
 * generic "save failed", which is what forgejo #20 reported.
 *
 * Falls back to `fallback` when the request never reached the API (network
 * error), when the body has no `error` field, or when the field is empty.
 */
export function apiErrorMessage(error: unknown, fallback: string): string {
  const body = (error as { response?: { data?: unknown } })?.response?.data

  if (typeof body === 'string' && body.trim()) return body.trim()

  if (body && typeof body === 'object') {
    for (const key of ['error', 'message', 'detail'] as const) {
      const value = (body as Record<string, unknown>)[key]
      if (typeof value === 'string' && value.trim()) return value.trim()
    }
  }

  return fallback
}
