import type {
  ConversationDetail,
  ConversationOut,
  EvidenceOut,
  MessageOut,
  Page,
  RetrievalOptions,
  RetrievalScopeInput,
  RetrievalTrace,
  SearchHistoryItem,
  SearchResponse,
  VerificationReport,
} from '@/types/api'

import { http, rawRequest } from './http'

export const DEFAULT_OPTIONS: RetrievalOptions = {
  strategy: 'hybrid',
  top_k: 8,
  candidate_k: 40,
  rrf_k: 60,
  dense_weight: 1,
  sparse_weight: 1,
  metric: 'cosine',
  rerank: true,
  rewrite: 'auto',
  multi_query: 'auto',
  expansion: 'auto',
  metadata_boost: true,
  compression: false,
  dedupe: true,
  relevance_threshold: null,
}

export type StreamEvent =
  | { type: 'meta'; data: { conversation_id: string; title: string } }
  | { type: 'retrieval'; data: RetrievalTrace & { evidence: EvidenceOut[] } }
  | { type: 'token'; data: { delta: string } }
  | { type: 'verification'; data: VerificationReport }
  | {
      type: 'done'
      data: {
        message_id: string
        status: string
        abstention_reason: string | null
        llm_provider: string
        llm_model: string
        retrieval_ms: number
        generation_ms: number
        total_ms: number
      }
    }
  | { type: 'error'; data: { code: string; message: string } }

/** Parse a Server-Sent Events stream from a fetch Response. */
export async function* readEventStream(response: Response): AsyncGenerator<StreamEvent> {
  const reader = response.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')
      let event = 'message'
      const dataLines: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (dataLines.length) {
        yield { type: event, data: JSON.parse(dataLines.join('\n')) } as StreamEvent
      }
    }
  }
}

export const chatApi = {
  stream: async (
    body: { question: string; conversation_id?: string; scope?: RetrievalScopeInput; options?: RetrievalOptions },
    signal?: AbortSignal,
  ) => {
    const response = await rawRequest('/chat/stream', {
      method: 'POST',
      body,
      signal,
      headers: { Accept: 'text/event-stream' },
    })
    return readEventStream(response)
  },
  regenerate: async (messageId: string, options?: RetrievalOptions, signal?: AbortSignal) => {
    const response = await rawRequest(`/chat/messages/${messageId}/regenerate`, {
      method: 'POST',
      body: { options: options ?? DEFAULT_OPTIONS },
      signal,
      headers: { Accept: 'text/event-stream' },
    })
    return readEventStream(response)
  },
  conversations: (params: { page?: number; q?: string } = {}) =>
    http.get<Page<ConversationOut>>('/conversations', params),
  conversation: (id: string) => http.get<ConversationDetail>(`/conversations/${id}`),
  createConversation: (body: { title?: string; scope?: RetrievalScopeInput }) =>
    http.post<ConversationOut>('/conversations', body),
  renameConversation: (id: string, title: string) => http.patch<ConversationOut>(`/conversations/${id}`, { title }),
  deleteConversation: (id: string) => http.delete<MessageOut>(`/conversations/${id}`),
}

export const searchApi = {
  search: (body: { query: string; scope?: RetrievalScopeInput; options?: Partial<RetrievalOptions> }) =>
    http.post<SearchResponse>('/search', { ...body, options: { ...DEFAULT_OPTIONS, ...body.options } }),
  history: (params: { page?: number; kind?: string } = {}) =>
    http.get<Page<SearchHistoryItem>>('/search/history', params),
}
