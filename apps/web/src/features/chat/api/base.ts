const configuredApiOrigin = import.meta.env.VITE_API_BASE_URL as string | undefined
const runtimeApiOrigin = typeof configuredApiOrigin === 'string' ? configuredApiOrigin.replace(/\/$/, '') : ''

export const API_BASE = runtimeApiOrigin ? `${runtimeApiOrigin}/api/v1` : '/api/v1'

export function apiUrl(path: string) {
  return `${API_BASE}${path}`
}
