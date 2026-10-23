import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUp, History, SlidersHorizontal, Square } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'

import { AssistantMessage, UserMessage } from '@/components/chat/AssistantMessage'
import { ConversationList } from '@/components/chat/ConversationList'
import { EvidencePanel } from '@/components/chat/EvidencePanel'
import { answerFromMessage, type AnswerView } from '@/components/chat/model'
import { RetrievalOptionsPanel } from '@/components/chat/RetrievalOptionsPanel'
import { ScopePicker } from '@/components/chat/ScopePicker'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/overlays'
import { Badge, ErrorState, Skeleton, Textarea } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { useChatStream } from '@/hooks/useChatStream'
import { chatApi, DEFAULT_OPTIONS } from '@/services/chat'
import type { RetrievalOptions, RetrievalScopeInput } from '@/types/api'
import { scopeSummary } from '@/utils/scope'

const OPTIONS_KEY = 'retrieva.chat.options'

function loadOptions(): RetrievalOptions {
  try {
    const raw = localStorage.getItem(OPTIONS_KEY)
    if (raw) return { ...DEFAULT_OPTIONS, ...JSON.parse(raw) }
  } catch {
    /* ignore */
  }
  return DEFAULT_OPTIONS
}

const EXAMPLES = [
  'Summarize the key obligations in our contracts, with sources.',
  'What notice period applies to termination?',
  'Compare the data retention requirements across our policies.',
]

export function ChatPage() {
  const { conversationId: routeId = null } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { session } = useAuth()

  const [input, setInput] = useState('')
  const [options, setOptions] = useState<RetrievalOptions>(loadOptions)
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [activeLabel, setActiveLabel] = useState<string | null>(null)
  const [draftScope, setDraftScope] = useState<RetrievalScopeInput>(() => ({
    document_ids: params.get('document') ? [params.get('document')!] : [],
    collection_ids: params.get('collection') ? [params.get('collection')!] : [],
  }))
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    try {
      localStorage.setItem(OPTIONS_KEY, JSON.stringify(options))
    } catch {
      /* ignore */
    }
  }, [options])

  const conversation = useQuery({
    queryKey: ['conversation', routeId],
    queryFn: () => chatApi.conversation(routeId!),
    enabled: !!routeId,
  })

  const stream = useChatStream({
    onConversation: (id) => {
      if (id !== routeId) navigate(`/app/chat/${id}`, { replace: true })
    },
    onSettled: (id) => {
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (id) void queryClient.invalidateQueries({ queryKey: ['conversation', id] })
    },
  })
  const { pending, clear } = stream

  // Once the refetched conversation contains the streamed answer, drop the local copy.
  useEffect(() => {
    if (!pending || pending.answer.status === 'streaming' || !pending.answer.id) return
    if (conversation.data?.messages.some((m) => m.id === pending.answer.id)) clear()
  }, [conversation.data, pending, clear])

  // Reset per-conversation UI state when switching conversations.
  useEffect(() => {
    setSelectedId(null)
    setActiveLabel(null)
    if (!stream.streaming) clear()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeId])

  const messages = useMemo(() => {
    let loaded = conversation.data?.messages ?? []
    if (pending?.regenerateOf) loaded = loaded.filter((m) => m.id !== pending.regenerateOf)
    // The server stores the question before answering; while streaming, show the local copy only.
    const last = loaded[loaded.length - 1]
    if (pending && !pending.regenerateOf && !pending.answer.id && last?.role === "user" && last.content === pending.question) {
      loaded = loaded.slice(0, -1)
    }
    return loaded
  }, [conversation.data, pending])

  const answers = useMemo(() => {
    const map = new Map<string, AnswerView>()
    messages.forEach((m) => m.role === 'assistant' && map.set(m.id, answerFromMessage(m)))
    return map
  }, [messages])

  const lastAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id ?? null
  const panelAnswer: AnswerView | null =
    (selectedId && answers.get(selectedId)) || pending?.answer || (lastAssistantId ? answers.get(lastAssistantId)! : null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, pending?.answer.content, pending?.question])

  const scope: RetrievalScopeInput = routeId
    ? {
        document_ids: conversation.data?.scope.document_ids ?? [],
        collection_ids: conversation.data?.scope.collection_ids ?? [],
      }
    : draftScope

  const submit = useCallback(() => {
    const question = input.trim()
    if (!question || stream.streaming) return
    setInput('')
    setSelectedId(null)
    setActiveLabel(null)
    void stream.send(question, routeId, options, routeId ? undefined : draftScope)
  }, [input, stream, routeId, options, draftScope])

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  const showEvidenceDialog = () => {
    // On wide screens the evidence panel is always visible beside the thread.
    if (!window.matchMedia?.("(min-width: 1280px)").matches) setEvidenceOpen(true)
  }

  const cite = (answerId: string | null) => (label: string) => {
    setSelectedId(answerId)
    setActiveLabel(label)
    showEvidenceDialog()
  }

  const questionFor = (assistantId: string): string => {
    const index = messages.findIndex((m) => m.id === assistantId)
    for (let i = index - 1; i >= 0; i -= 1) if (messages[i].role === 'user') return messages[i].content
    return ''
  }

  const empty = !routeId && !pending

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 border-r border-border bg-surface lg:block">
        <ConversationList activeId={routeId} />
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
          <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setHistoryOpen(true)} aria-label="Conversations">
            <History />
          </Button>
          <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">
            {routeId ? (conversation.data?.title ?? 'Conversation') : 'New chat'}
          </h1>
          <ScopePicker value={scope} onChange={setDraftScope} disabled={!!routeId} />
          <Button variant="secondary" size="sm" onClick={() => setOptionsOpen(true)}>
            <SlidersHorizontal /> <span className="hidden sm:inline">Retrieval</span>
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
            {empty && (
              <div className="pt-10 text-center sm:pt-16">
                <h2 className="text-2xl font-semibold tracking-tight">
                  Ask your knowledge base{session ? `, ${session.user.full_name.split(' ')[0]}` : ''}
                </h2>
                <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
                  Answers cite the exact passages they rely on. When the documents don't contain the answer, Retrieva
                  says so. Searching: <strong>{scopeSummary(draftScope)}</strong>.
                </p>
                <div className="mx-auto mt-6 grid max-w-xl gap-2">
                  {EXAMPLES.map((example) => (
                    <button
                      key={example}
                      type="button"
                      className="cursor-pointer rounded-lg border border-border bg-surface px-4 py-2.5 text-left text-sm hover:bg-surface-2"
                      onClick={() => {
                        setInput(example)
                        textareaRef.current?.focus()
                      }}
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {routeId && conversation.isLoading && (
              <div className="space-y-4">
                <Skeleton className="ml-auto h-10 w-2/3" />
                <Skeleton className="h-32" />
              </div>
            )}
            {routeId && conversation.isError && !pending && (
              <ErrorState title="Conversation unavailable" error={conversation.error} onRetry={() => conversation.refetch()} />
            )}

            {messages.map((m) =>
              m.role === 'user' ? (
                <UserMessage key={m.id} content={m.content} />
              ) : (
                <div
                  key={m.id}
                  onClick={() => setSelectedId(m.id)}
                  className={panelAnswer?.id === m.id ? 'rounded-xl xl:bg-surface/60 xl:ring-1 xl:ring-border xl:p-3 xl:-m-3' : ''}
                >
                  <AssistantMessage
                    answer={answers.get(m.id)!}
                    activeLabel={panelAnswer?.id === m.id ? activeLabel : null}
                    onCite={cite(m.id)}
                    onShowEvidence={() => {
                      setSelectedId(m.id)
                      showEvidenceDialog()
                    }}
                    canRegenerate={m.id === lastAssistantId && !stream.streaming && !pending}
                    onRegenerate={() => routeId && void stream.regenerate(m.id, questionFor(m.id), routeId, options)}
                  />
                </div>
              ),
            )}

            {pending && (
              <>
                {!pending.regenerateOf && <UserMessage content={pending.question} />}
                <AssistantMessage
                  answer={pending.answer}
                  activeLabel={!selectedId ? activeLabel : null}
                  onCite={cite(null)}
                  onShowEvidence={() => {
                    setSelectedId(null)
                    showEvidenceDialog()
                  }}
                  canRegenerate={false}
                />
              </>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="border-t border-border bg-background px-4 py-3">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end gap-2 rounded-xl border border-border bg-surface p-2 shadow-[var(--shadow-card)] focus-within:border-primary">
              <Textarea
                ref={textareaRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={routeId ? 'Ask a follow-up question…' : 'Ask a question about your documents…'}
                className="max-h-40 min-h-9 resize-none border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:ring-0"
                aria-label="Message"
                maxLength={2000}
              />
              {stream.streaming ? (
                <Button size="icon" variant="secondary" onClick={stream.stop} aria-label="Stop generating">
                  <Square />
                </Button>
              ) : (
                <Button size="icon" onClick={submit} disabled={!input.trim()} aria-label="Send">
                  <ArrowUp />
                </Button>
              )}
            </div>
            <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
              <Badge tone="outline">{options.strategy}</Badge>
              {options.rerank && <Badge tone="outline">rerank</Badge>}
              <span>top-{options.top_k} · Enter to send, Shift+Enter for a new line</span>
            </p>
          </div>
        </div>
      </section>

      <aside className="hidden w-[400px] shrink-0 border-l border-border bg-background xl:block">
        <EvidencePanel answer={panelAnswer} activeLabel={activeLabel} />
      </aside>

      {/* Evidence for small screens */}
      <Dialog open={evidenceOpen} onOpenChange={setEvidenceOpen}>
        <DialogContent title="Evidence" className="h-[85vh] max-w-xl p-0 xl:hidden">
          <div className="h-[calc(85vh-4rem)]">
            <EvidencePanel answer={panelAnswer} activeLabel={activeLabel} showHeader={false} />
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent title="Conversations" className="h-[80vh] max-w-sm p-0">
          <div className="h-[calc(80vh-4rem)]">
            <ConversationList activeId={routeId} onNavigate={() => setHistoryOpen(false)} />
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={optionsOpen} onOpenChange={setOptionsOpen}>
        <DialogContent
          title="Retrieval settings"
          description="Applied to your next question. Each stage can be switched off to compare its effect."
        >
          <RetrievalOptionsPanel value={options} onChange={setOptions} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
