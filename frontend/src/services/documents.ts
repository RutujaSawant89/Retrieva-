import type {
  ChunkOut,
  ChunkingStrategy,
  DocumentContent,
  DocumentDetail,
  DocumentOut,
  DocumentStatus,
  MessageOut,
  Page,
  UploadResult,
  Visibility,
} from '@/types/api'

import { http, uploadWithProgress } from './http'

export interface DocumentListParams {
  page?: number
  page_size?: number
  q?: string
  status?: DocumentStatus[]
  file_type?: string
  category?: string
  collection_id?: string
  mine?: boolean
  sort?: 'created_at' | 'title' | 'file_size' | 'status'
  order?: 'asc' | 'desc'
}

export const PROCESSING_STATUSES: DocumentStatus[] = [
  'uploaded',
  'queued',
  'extracting',
  'chunking',
  'embedding',
  'indexing',
]

export const isProcessing = (status: DocumentStatus) => PROCESSING_STATUSES.includes(status)

export const documentsApi = {
  list: (params: DocumentListParams = {}) =>
    http.get<Page<DocumentOut>>('/documents', params as Record<string, string | number | boolean | string[]>),
  categories: () => http.get<string[]>('/documents/categories'),
  get: (id: string) => http.get<DocumentDetail>(`/documents/${id}`),
  chunks: (id: string, page = 1) => http.get<Page<ChunkOut>>(`/documents/${id}/chunks`, { page, page_size: 50 }),
  content: (id: string) => http.get<DocumentContent>(`/documents/${id}/content`),
  update: (id: string, body: { title?: string; category?: string | null; visibility?: Visibility }) =>
    http.patch<DocumentOut>(`/documents/${id}`, body),
  remove: (id: string) => http.delete<MessageOut>(`/documents/${id}`),
  reprocess: (
    id: string,
    body: { strategy?: ChunkingStrategy; chunk_size?: number; chunk_overlap?: number; max_tokens?: number },
  ) => http.post<{ status: DocumentStatus }>(`/documents/${id}/reprocess`, body),
  upload: (
    files: File[],
    options: { category?: string; visibility?: Visibility; collection_id?: string },
    onProgress: (fraction: number) => void,
    signal?: AbortSignal,
  ) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    if (options.category) form.append('category', options.category)
    if (options.visibility) form.append('visibility', options.visibility)
    if (options.collection_id) form.append('collection_id', options.collection_id)
    return uploadWithProgress<{ results: UploadResult[] }>('/documents/upload', form, onProgress, signal)
  },
  fileUrl: (id: string) => `/api/v1/documents/${id}/file`,
}
