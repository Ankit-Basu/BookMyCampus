import axios, { AxiosError } from 'axios'

export const api = axios.create({ baseURL: '/api' })

const TOKEN_KEY = 'bmc.tokens'

export type Tokens = { access: string; refresh: string }

export function getTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(TOKEN_KEY)
    return raw ? (JSON.parse(raw) as Tokens) : null
  } catch {
    return null
  }
}

export function setTokens(t: Tokens | null) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, JSON.stringify(t))
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode — session lasts until reload */
  }
}

api.interceptors.request.use((cfg) => {
  const t = getTokens()
  if (t) cfg.headers.Authorization = `Bearer ${t.access}`
  return cfg
})

// null: the refresh token was refused, so sign out. undefined: the server didn't answer, so stay signed in.
let refreshing: Promise<string | null | undefined> | null = null

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as (typeof error.config & { _retry?: boolean }) | undefined
    const tokens = getTokens()
    if (error.response?.status === 401 && tokens?.refresh && original && !original._retry) {
      original._retry = true
      refreshing ??= axios
        .post('/api/auth/refresh', { refresh: tokens.refresh })
        .then((r) => {
          setTokens({ access: r.data.access, refresh: tokens.refresh })
          return r.data.access as string
        })
        .catch((e: AxiosError) => {
          const s = e.response?.status
          if (s === 400 || s === 401) {
            setTokens(null)
            return null
          }
          return undefined
        })
        .finally(() => {
          refreshing = null
        })
      const access = await refreshing
      if (access) {
        original.headers = original.headers ?? {}
        ;(original.headers as Record<string, string>).Authorization = `Bearer ${access}`
        return api(original)
      }
      if (access === null) window.dispatchEvent(new Event('bmc:logout'))
    }
    return Promise.reject(error)
  },
)

export type ApiError = { error?: string; message?: string; detail?: string; details?: Record<string, unknown> }

/** Human message out of any API error shape (domain errors, DRF validation, network). */
/** A missing or forbidden record will not appear on a retry, so say so straight away. */
export const retryUnlessMissing = (count: number, e: unknown) => ![403, 404].includes((e as AxiosError)?.response?.status ?? 0) && count < 2

export function errorMessage(e: unknown): string {
  const ax = e as AxiosError<ApiError | Record<string, string[]>>
  const d = ax?.response?.data as ApiError & Record<string, unknown>
  const status = ax?.response?.status
  if (status && status >= 502 && status <= 504) return 'The server is waking up. Wait a few seconds and try again.'
  if (typeof d === 'string') return status ? `The server had a problem (${status}). Try again in a moment.` : 'Something went wrong'
  if (d) {
    if (typeof d.message === 'string') return d.message
    if (typeof d.detail === 'string') return d.detail
    const first = Object.entries(d)[0]
    if (first) {
      const [k, v] = first
      const msg = Array.isArray(v) ? v[0] : typeof v === 'string' ? v : JSON.stringify(v)
      return k === 'non_field_errors' ? String(msg) : `${k}: ${msg}`
    }
  }
  if (ax?.message === 'Network Error') return 'Can’t reach the server — is the backend running?'
  return ax?.message || 'Something went wrong'
}

export function errorCode(e: unknown): string | undefined {
  return ((e as AxiosError<ApiError>)?.response?.data as ApiError)?.error
}

export function errorDetails(e: unknown): Record<string, any> {
  return (((e as AxiosError<ApiError>)?.response?.data as ApiError)?.details as Record<string, any>) ?? {}
}

/** Authenticated fetch of an SVG/ics endpoint → object URL (img tags can't send our bearer token). */
export async function blobUrl(path: string): Promise<string> {
  const r = await api.get(path, { responseType: 'blob' })
  return URL.createObjectURL(r.data)
}

export async function download(path: string, filename: string) {
  const url = await blobUrl(path)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
