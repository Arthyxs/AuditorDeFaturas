export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) => {
          if (typeof item === 'object' && item && 'msg' in item) return String(item.msg)
          return String(item)
        })
        .join(' ')
    }
  } catch {
    // The status-specific fallback below is safer than exposing an HTML error body.
  }
  return 'Não foi possível concluir a solicitação.'
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(path, { credentials: 'same-origin', ...options, headers })
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
