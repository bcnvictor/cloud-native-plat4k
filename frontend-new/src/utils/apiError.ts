// Extrait le `detail` FastAPI d'une erreur axios, sinon un message générique.
export function apiError(error: unknown, fallback = 'Unexpected error'): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}
