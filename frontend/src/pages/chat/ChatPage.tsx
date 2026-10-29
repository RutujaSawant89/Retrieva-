import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUp, Download, History, MessageSquarePlus, ShieldCheck, SlidersHorizontal, Sparkles, Square } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { AssistantMessage, UserMessage } from '@/components/chat/AssistantMessage'
import { ConversationList } from '@/components/chat/ConversationList'
import { EvidencePanel } from '@/components/chat/EvidencePanel'
import { answerFromMessage, type AnswerView } from '@/components/chat/model'
import { RetrievalOptionsPanel } from '@/components/chat/RetrievalOptionsPanel'
import { ScopePicker } from '@/components/chat/ScopePicker'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Tooltip,
} from '@/components/ui/overlays'
import { ErrorState, Skeleton, Textarea } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { useChatStream } from '@/hooks/useChatStream'
import { chatApi, DEFAULT_OPTIONS } from '@/services/chat'
import { documentsApi } from '@/services/documents'
import { exportConversation } from '@/services/insights'
import type { RetrievalOptions, RetrievalScopeInput } from '@/types/api'
import { settingsSummary } from '@/utils/retrieval'

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

const GENERIC_EXAMPLES = [
  'What are the most important deadlines or notice periods?',
  'Which figures or amounts are mentioned, and where?',
]

export function ChatPage() {
  const { conversationId: routeId = null } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { session, can } = useAuth()

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
  const readyDocs = useQuery({
    queryKey: ['documents', 'chat-suggestions'],
    queryFn: () => documentsApi.list({ status: ['completed'], page_size: 3 }),
    enabled: !routeId,
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
    if (pending && !pending.regenerateOf && !pending.answer.id && last?.role === 'user' && last.content === pending.question) {
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

  // Grow the input with its content, up to a limit.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [input])

  const scope: RetrievalScopeInput = routeId
    ? {
        document_ids: conversation.data?.scope.document_ids ?? [],
        collection_ids: conversation.data?.scope.collection_ids ?? [],
      }
    : draftScope

  const submit = useCallback(
    (text?: string) => {
      const question = (text ?? input).trim()
      if (!question || stream.streaming) return
      setInput('')
      setSelectedId(null)
      setActiveLabel(null)
      void stream.send(question, routeId, options, routeId ? undefined : draftScope)
    },
    [input, stream, routeId, options, draftScope],
  )

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  const showEvidenceDialog = () => {
    // On wide screens the evidence panel is always visible beside the thread.
    if (!window.matchMedia?.('(min-width: 1280px)').matches) setEvidenceOpen(true)
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

  const suggestions = useMemo(() => {
    const docs = readyDocs.data?.items ?? []
    const fromDocs = docs.slice(0, 2).flatMap((d, i) =>
      i === 0 ? [`Summarize “${d.title}”`, `What are the key points in “${d.title}”?`] : [`What is “${d.title}” about?`],
    )
    return [...fromDocs, ...GENERIC_EXAMPLES].slice(0, 4)
  }, [readyDocs.data])

  const empty = !routeId && !pending
  const noDocuments = readyDocs.data && readyDocs.data.total === 0

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 border-r border-border bg-surface 2xl:block">
        <ConversationList activeId={routeId} />
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 items-center gap-2 border-b border-border px-4">
          <Tooltip content="Conversation history">
            <Button variant="ghost" size="icon-sm" className="2xl:hidden" onClick={() => setHistoryOpen(true)} aria-label="Conversation history">
              <History />
            </Button>
          </Tooltip>
          <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">
            {routeId ? (conversation.data?.title ?? 'Conversation') : 'New conversation'}
          </h1>
          {routeId && (
            <Button variant="ghost" size="sm" onClick={() => navigate('/app/chat')}>
              <MessageSquarePlus /> <span className="hidden sm:inline">New chat</span>
            </Button>
          )}
          {routeId && conversation.data && conversation.data.messages.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" aria-label="Export conversation">
                  <Download /> <span className="hidden sm:inline">Export</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {(['pdf', 'docx', 'md'] as const).map((format) => (
                  <DropdownMenuItem
                    key={format}
                    onSelect={() =>
                      exportConversation(routeId, format, conversation.data!.title)
                        .then(() => toast.success('Export downloaded'))
                        .catch((e: Error) => toast.error(e.message))
                    }
                  >
                    Export as {format === 'md' ? 'Markdown' : format === 'docx' ? 'Word' : 'PDF'}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
            {empty && (
              <div className="page-enter pt-8 sm:pt-14">
                <div className="text-center">
                  <span className="mx-auto flex size-11 items-center justify-center rounded-2xl bg-primary-soft text-primary">
                    <Sparkles className="size-5" />
                  </span>
                  <h2 className="mt-4 text-2xl font-semibold tracking-tight">
                    What would you like to know{session ? `, ${session.user.full_name.split(' ')[0]}` : ''}?
                  </h2>
                  <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
                    Ask in plain language. Every answer shows the passages it came from, and Retrieva tells you when your
                    documents don&rsquo;t contain the answer.
                  </p>
                </div>
                {noDocuments ? (
                  <div className="mx-auto mt-8 max-w-md rounded-xl border border-dashed border-border-strong p-5 text-center text-sm">
                    <p className="font-medium">You don&rsquo;t have any ready documents yet</p>
                    <p className="mt-1 text-muted-foreground">Upload a file first — questions are answered from your documents.</p>
                    {can('documents:write') && (
                      <Button asChild size="sm" className="mt-3">
                        <Link to="/app/documents?upload=1">Upload documents</Link>
                      </Button>
                    )}
                  </div>
                ) : (
                  <div className="mx-auto mt-8 grid max-w-2xl gap-2 sm:grid-cols-2">
                    {suggestions.map((example) => (
                      <button
                        key={example}
                        type="button"
                        className="group cursor-pointer rounded-xl border border-border bg-surface px-4 py-3 text-left text-[13.5px] transition-colors hover:border-primary/40 hover:bg-primary-soft/40"
                        onClick={() => submit(example)}
                      >
                        {example}
                        <span className="mt-1 block text-[11px] text-muted-foreground group-hover:text-primary">Ask this →</span>
                      </button>
                    ))}
                  </div>
                )}
                <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
                  <ShieldCheck className="size-3.5 text-success" /> Answers are checked against their sources before you see the
                  verdict.
                </p>
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
                  className={panelAnswer?.id === m.id ? 'rounded-2xl xl:-m-3 xl:bg-surface xl:p-3 xl:ring-1 xl:ring-border' : ''}
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

        <div className="border-t border-border bg-background px-4 pb-4 pt-3">
          <div className="mx-auto max-w-3xl">
            <div className="rounded-2xl border border-border bg-surface shadow-[var(--shadow-card)] transition-colors focus-within:border-primary focus-within:ring-4 focus-within:ring-primary/10">
              <Textarea
                ref={textareaRef}
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={routeId ? 'Ask a follow-up question…' : 'Ask a question about your documents…'}
                className="min-h-14 resize-none border-0 bg-transparent px-4 pt-3 text-[15px] shadow-none focus-visible:border-0 focus-visible:ring-0"
                aria-label="Message"
                maxLength={2000}
              />
              <div className="flex flex-wrap items-center gap-2 px-3 pb-3">
                <ScopePicker value={scope} onChange={setDraftScope} disabled={!!routeId} />
                <Tooltip content="Search settings">
                  <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setOptionsOpen(true)}>
                    <SlidersHorizontal /> <span className="hidden sm:inline">{settingsSummary(options)}</span>
                  </Button>
                </Tooltip>
                <span className="flex-1" />
                {stream.streaming ? (
                  <Button size="icon" variant="secondary" onClick={stream.stop} aria-label="Stop generating">
                    <Square />
                  </Button>
                ) : (
                  <Button size="icon" onClick={() => submit()} disabled={!input.trim()} aria-label="Send">
                    <ArrowUp />
                  </Button>
                )}
              </div>
            </div>
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              Enter to send · Shift + Enter for a new line · Click a source tag like <span className="font-mono">S1</span> to see
              the passage
            </p>
          </div>
        </div>
      </section>

      <aside className="hidden w-[380px] shrink-0 border-l border-border bg-background xl:block 2xl:w-[420px]">
        <EvidencePanel answer={panelAnswer} activeLabel={activeLabel} />
      </aside>

      {/* Evidence for small screens */}
      <Dialog open={evidenceOpen} onOpenChange={setEvidenceOpen}>
        <DialogContent title="Sources" className="h-[85vh] max-w-xl p-0 xl:hidden">
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
          title="Search settings"
          description="How Retrieva finds evidence for your next question. The defaults work well for most documents."
          className="max-h-[90vh] overflow-y-auto"
        >
          <RetrievalOptionsPanel value={options} onChange={setOptions} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
