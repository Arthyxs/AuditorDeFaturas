import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiRequest } from './client'

afterEach(() => vi.unstubAllGlobals())

describe('apiRequest', () => {
  it('surfaces backend upload validation details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'file extension is not supported' }),
      { status: 422, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(apiRequest('/api/tariffs')).rejects.toThrow('file extension is not supported')
  })

  it('lets the browser generate the multipart boundary', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const body = new FormData()
    body.append('files', new File(['x'], 'rates.csv', { type: 'text/csv' }))

    await apiRequest('/api/tariffs', { method: 'POST', body })

    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(new Headers(options.headers).has('Content-Type')).toBe(false)
  })
})
