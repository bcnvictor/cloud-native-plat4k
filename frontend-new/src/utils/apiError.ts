// Extrait le `detail` FastAPI d'une erreur axios (string, ou liste d'erreurs de validation 422), sinon un message générique.
export function apiError(error: unknown, fallback = 'Unexpected error'): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string }).msg).filter(Boolean).join(', ') || fallback;
  return fallback;
}
