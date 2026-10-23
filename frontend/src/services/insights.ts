import type {
  AnalyticsOverview,
  CompareResult,
  EvalDataset,
  EvalItem,
  EvalPreset,
  EvalRun,
  EvalRunDetail,
  MessageOut,
  Page,
  ResearchReport,
  ResearchSummary,
  RetrievalAnalytics,
  RetrievalOptions,
  RetrievalScopeInput,
  UsageAnalytics,
} from '@/types/api'

import { DEFAULT_OPTIONS, readEventStream } from './chat'
import { downloadFile, http, rawRequest, uploadWithProgress } from './http'

const fileStem = (title: string) => title.slice(0, 60).replace(/[^\w -]+/g, '').trim() || 'retrieva-export'

export const analyticsApi = {
  overview: () => http.get<AnalyticsOverview>('/analytics/overview'),
  retrieval: (days: number) => http.get<RetrievalAnalytics>('/analytics/retrieval', { days }),
  usage: (days: number) => http.get<UsageAnalytics>('/analytics/usage', { days }),
}

export const evaluationApi = {
  presets: () => http.get<Record<string, EvalPreset>>('/evaluation/presets'),
  datasets: () => http.get<Page<EvalDataset>>('/evaluation/datasets'),
  dataset: (id: string) => http.get<EvalDataset & { items: EvalItem[] }>(`/evaluation/datasets/${id}`),
  uploadDataset: (file: File, name: string, description = '') => {
    const form = new FormData()
    form.append('file', file)
    form.append('name', name)
    form.append('description', description)
    return uploadWithProgress<EvalDataset>('/evaluation/datasets/upload', form, () => {})
  },
  deleteDataset: (id: string) => http.delete<MessageOut>(`/evaluation/datasets/${id}`),
  run: (body: {
    dataset_id: string
    name: string
    preset?: string
    experiments?: { name: string; options: RetrievalOptions }[]
    ks?: number[]
    generate?: boolean
    use_ragas?: boolean
  }) => http.post<EvalRun[]>('/evaluation/run', body),
  runs: (datasetId?: string) => http.get<Page<EvalRun>>('/evaluation/runs', { dataset_id: datasetId, page_size: 200 }),
  runDetail: (id: string) => http.get<EvalRunDetail>(`/evaluation/runs/${id}`),
  deleteRun: (id: string) => http.delete<MessageOut>(`/evaluation/runs/${id}`),
}

export type ResearchEvent = { type: string; data: Record<string, unknown> }

export const researchApi = {
  start: async (
    body: { question: string; scope?: RetrievalScopeInput; options?: RetrievalOptions },
    signal?: AbortSignal,
  ) => {
    const response = await rawRequest('/research', {
      method: 'POST',
      body: { ...body, options: body.options ?? DEFAULT_OPTIONS },
      signal,
      headers: { Accept: 'text/event-stream' },
    })
    return readEventStream(response) as unknown as AsyncGenerator<ResearchEvent>
  },
  list: () => http.get<Page<ResearchSummary>>('/research'),
  get: (id: string) => http.get<ResearchReport>(`/research/${id}`),
  remove: (id: string) => http.delete<MessageOut>(`/research/${id}`),
  export: (id: string, format: 'md' | 'docx' | 'pdf', title: string) =>
    downloadFile(`/research/${id}/export`, `${fileStem(title)}.${format}`, { query: { format } }),
}

export const compareApi = {
  compare: (document_a: string, document_b: string, summarize = true) =>
    http.post<CompareResult>('/compare', { document_a, document_b, summarize }),
}

export const exportConversation = (id: string, format: 'md' | 'docx' | 'pdf', title: string) =>
  downloadFile(`/conversations/${id}/export`, `${fileStem(title)}.${format}`, { query: { format } })
