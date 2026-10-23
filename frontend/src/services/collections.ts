import type { CollectionOut, MessageOut, Page, Visibility } from '@/types/api'

import { http, request } from './http'

export const collectionsApi = {
  list: (params: { page?: number; page_size?: number; q?: string } = {}) =>
    http.get<Page<CollectionOut>>('/collections', params),
  get: (id: string) => http.get<CollectionOut>(`/collections/${id}`),
  create: (body: { name: string; description?: string; visibility?: Visibility }) =>
    http.post<CollectionOut>('/collections', body),
  update: (id: string, body: { name?: string; description?: string; visibility?: Visibility }) =>
    http.patch<CollectionOut>(`/collections/${id}`, body),
  remove: (id: string) => http.delete<MessageOut>(`/collections/${id}`),
  addDocuments: (id: string, document_ids: string[]) =>
    http.post<CollectionOut>(`/collections/${id}/documents`, { document_ids }),
  removeDocuments: (id: string, document_ids: string[]) =>
    request<CollectionOut>(`/collections/${id}/documents`, { method: 'DELETE', body: { document_ids } }),
}
