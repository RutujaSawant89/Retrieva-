import { useCallback, useLayoutEffect, useRef, useState } from 'react'

import { evidenceFromStream, type AnswerView } from '@/components/chat/model'
import { chatApi, type StreamEvent } from '@/services/chat'
import { ApiError } from '@/services/http'
import type { EvidenceOut, RetrievalOptions, RetrievalScopeInput } from '@/types/api'

export interface PendingTurn {
  question: string
  answer: AnswerView
  regenerateOf: string | null
}

const emptyAnswer = (): AnswerView => ({
  id: null,
  content: '',
  status: 'streaming',
  evidence: [],
  trace: null,
  verification: null,
  provider: null,
  model: null,
  retrievalMs: null,
  generationMs: null,
  totalMs: null,
  promptTokens: null,
  completionTokens: null,
})

/**
 * Drives one streamed chat turn and exposes its live state. When the stream finishes,
 * ``onSettled`` lets the page refetch the conversation, which then owns the message.
 */
export function useChatStream(opts: {
  onConversation: (id: string) => void
  onSettled: (conversationId: string | null) => void
}) {
  const [pending, setPending] = useState<PendingTurn | null>(null)
  const controller = useRef<AbortController | null>(null)
  const evidenceRef = useRef<EvidenceOut[]>([])
  // Latest callbacks, so a stream started on an earlier render reports to current handlers.
  const handlers = useRef(opts)
  useLayoutEffect(() => {
    handlers.current = opts
  })

  const consume = useCallback(
    async (events: AsyncGenerator<StreamEvent>, initialConversation: string | null) => {
      let conversationId = initialConversation
      for await (const event of events) {
        switch (event.type) {
          case 'meta':
            conversationId = event.data.conversation_id
            handlers.current.onConversation(conversationId)
            break
          case 'retrieval':
            evidenceRef.current = event.data.evidence
            setPending((p) =>
              p && { ...p, answer: { ...p.answer, trace: event.data, evidence: evidenceFromStream(event.data.evidence, null) } },
            )
            break
          case 'token':
            setPending((p) => p && { ...p, answer: { ...p.answer, content: p.answer.content + event.data.delta } })
            break
          case 'verification':
            setPending(
              (p) =>
                p && {
                  ...p,
                  answer: {
                    ...p.answer,
                    verification: event.data,
                    evidence: evidenceFromStream(evidenceRef.current, event.data),
                  },
                },
            )
            break
          case 'done':
            setPending(
              (p) =>
                p && {
                  ...p,
                  answer: {
                    ...p.answer,
                    id: event.data.message_id,
                    status: event.data.status as AnswerView['status'],
                    provider: event.data.llm_provider,
                    model: event.data.llm_model,
                    retrievalMs: event.data.retrieval_ms,
                    generationMs: event.data.generation_ms,
                    totalMs: event.data.total_ms,
                  },
                },
            )
            break
          case 'error':
            setPending((p) => p && { ...p, answer: { ...p.answer, status: 'error', error: event.data.message } })
            break
        }
      }
      return conversationId
    },
    [],
  )

  const run = useCallback(
    async (start: (signal: AbortSignal) => Promise<AsyncGenerator<StreamEvent>>, turn: Omit<PendingTurn, 'answer'>, conversationId: string | null) => {
      controller.current?.abort()
      controller.current = new AbortController()
      evidenceRef.current = []
      setPending({ ...turn, answer: emptyAnswer() })
      let finalConversation = conversationId
      try {
        finalConversation = await consume(await start(controller.current.signal), conversationId)
      } catch (error) {
        const aborted = error instanceof DOMException && error.name === 'AbortError'
        setPending(
          (p) =>
            p && {
              ...p,
              answer: {
                ...p.answer,
                status: 'error',
                error: aborted ? 'Stopped' : error instanceof ApiError ? error.message : 'Connection lost while streaming',
              },
            },
        )
      } finally {
        handlers.current.onSettled(finalConversation)
      }
    },
    [consume],
  )

  const send = useCallback(
    (question: string, conversationId: string | null, options: RetrievalOptions, scope?: RetrievalScopeInput) =>
      run(
        (signal) =>
          chatApi.stream(
            { question, conversation_id: conversationId ?? undefined, scope: conversationId ? undefined : scope, options },
            signal,
          ),
        { question, regenerateOf: null },
        conversationId,
      ),
    [run],
  )

  const regenerate = useCallback(
    (messageId: string, question: string, conversationId: string, options: RetrievalOptions) =>
      run((signal) => chatApi.regenerate(messageId, options, signal), { question, regenerateOf: messageId }, conversationId),
    [run],
  )

  const stop = useCallback(() => controller.current?.abort(), [])
  const clear = useCallback(() => setPending(null), [])
  const streaming = pending?.answer.status === 'streaming'

  return { pending, streaming, send, regenerate, stop, clear }
}
