import { apiRequest } from '../../api/client'

export type Tariff = {
  id: string
  original_filename: string
  internal_filename: string
  extension: string
  mime_type: string
  size: number
  sha256: string
  description: string | null
  notes: string | null
  active: boolean
  version: number
  version_group_id: string
  previous_version_id: string | null
  uploaded_by_id: string
  created_at: string
  updated_at: string
  deleted_at: string | null
  usage_count: number
}

export type TariffPage = {
  items: Tariff[]
  page: number
  page_size: number
  total: number
  pages: number
}

export type TariffFilters = {
  page: number
  pageSize: number
  search: string
  active: '' | 'true' | 'false'
}

export function listTariffs(filters: TariffFilters): Promise<TariffPage> {
  const query = new URLSearchParams({
    page: String(filters.page),
    page_size: String(filters.pageSize),
  })
  if (filters.search.trim()) query.set('search', filters.search.trim())
  if (filters.active) query.set('active', filters.active)
  return apiRequest<TariffPage>(`/api/tariffs?${query.toString()}`)
}

export function getTariff(id: string): Promise<Tariff> {
  return apiRequest<Tariff>(`/api/tariffs/${id}`)
}

export function getTariffVersions(id: string): Promise<Tariff[]> {
  return apiRequest<Tariff[]>(`/api/tariffs/${id}/versions`)
}

export async function uploadTariff(file: File): Promise<Tariff> {
  const body = new FormData()
  body.append('files', file)
  const response = await apiRequest<{ items: Tariff[] }>('/api/tariffs', {
    method: 'POST',
    body,
  })
  return response.items[0]
}

export function updateTariff(
  id: string,
  patch: { description?: string | null; notes?: string | null; active?: boolean },
): Promise<Tariff> {
  return apiRequest<Tariff>(`/api/tariffs/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export function deleteTariff(id: string): Promise<void> {
  return apiRequest<void>(`/api/tariffs/${id}`, { method: 'DELETE' })
}
