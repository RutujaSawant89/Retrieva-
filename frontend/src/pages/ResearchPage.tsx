import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Download, FileSearch, Loader2, Search, Trash2 } from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { AnswerMarkdown } from '@/components/chat/AnswerMarkdown'
import { EvidencePanel } from '@/components/chat/EvidencePanel'
import { evidenceFromStream, type AnswerView } from '@/components/chat/model'
import { ScopePicker } from '@/components/chat/ScopePicker'
import { Button } from '@/components/ui/button'
import {
  ConfirmDialog,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/overlays'
import { Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton, Textarea } from '@/components/ui/primitives'
import { ApiError } from '@/services/http'
import { researchApi } from '@/services/insights'
import type { EvidenceOut, ResearchReport, ResearchSubquery, RetrievalScopeInput, VerificationReport } from '@/types/api'
import { cn } from '@/utils/cn'
import { formatMs, formatPercent, formatRelative } from '@/utils/format'

interface LiveState {
  stage: 'planning' | 'retrieving' | 'writing' | 'verifying' | 'done' | 'error'
  subqueries: string[]
  done: ResearchSubquery[]
  evidence: EvidenceOut[]
  conflicts: { labels: string[]; reason: string }[]
  report: string
  verification: VerificationReport | null
  error?: string
}

function toAnswer(report: string, evidence: EvidenceOut[], verification: VerificationReport | null, status: string): AnswerView {
  return {
    id: null,
    content: report,
    status: status === 'abstained' ? 'abstained' : 'answered',
    evidence: evidenceFromStream(evidence, verification),
    trace: null,
    verification,
    provider: null,
    model: null,
    retrievalMs: null,
    generationMs: null,
    totalMs: null,
    promptTokens: null,
    completionTokens: null,
  }
}

export function ResearchPage() {
  const { reportId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [question, setQuestion] = useState('')
  const [scope, setScope] = useState<RetrievalScopeInput>({ document_ids: [], collection_ids: [] })
  const [live, setLive] = useState<LiveState | null>(null)
  const [activeLabel, setActiveLabel] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)

  const history = useQuery({ queryKey: ['research', 'list'], queryFn: researchApi.list })
  const saved = useQuery({ queryKey: ['research', reportId], queryFn: () => researchApi.get(reportId!), enabled: !!reportId && !live })

  async function start(event: FormEvent) {
    event.preventDefault()
    if (question.trim().length < 5) return
    controller.current?.abort()
    controller.current = new AbortController()
    setActiveLabel(null)
    const state: LiveState = { stage: 'planning', subqueries: [], done: [], evidence: [], conflicts: [], report: '', verification: null }
    setLive({ ...state })
    let newId: string | null = null
    try {
      const events = await researchApi.start({ question: question.trim(), scope }, controller.current.signal)
      for await (const event of events) {
        const data = event.data
        if (event.type === 'meta') newId = String(data.report_id)
        else if (event.type === 'plan') {
          state.subqueries = data.subqueries as string[]
          state.stage = 'retrieving'
        } else if (event.type === 'subquery') state.done = [...state.done, data as unknown as ResearchSubquery]
        else if (event.type === 'evidence') {
          state.evidence = data.evidence as EvidenceOut[]
          state.conflicts = data.conflicts as LiveState['conflicts']
          state.stage = 'writing'
        } else if (event.type === 'token') state.report += String(data.delta)
        else if (event.type === 'verification') {
          state.verification = data as unknown as VerificationReport
          state.stage = 'verifying'
        } else if (event.type === 'done') state.stage = 'done'
        else if (event.type === 'error') {
          state.stage = 'error'
          state.error = String(data.message)
        }
        setLive({ ...state })
      }
      void queryClient.invalidateQueries({ queryKey: ['research', 'list'] })
      if (newId) {
        navigate(`/app/research/${newId}`, { replace: true })
        await queryClient.invalidateQueries({ queryKey: ['research', newId] })
      }
      setLive(null)
    } catch (error) {
      setLive({ ...state, stage: 'error', error: error instanceof ApiError ? error.message : 'Research failed' })
    }
  }

  const view: ResearchReport | null = saved.data && !live ? saved.data : null
  const answer = live
    ? live.stage === 'writing' || live.report
      ? toAnswer(live.report, live.evidence, live.verification, 'completed')
      : null
    : view
      ? toAnswer(view.report, view.evidence, 'claims' in view.verification ? (view.verification as VerificationReport) : null, view.status)
      : null
  const verification = live?.verification ?? (view && 'claims' in view.verification ? (view.verification as VerificationReport) : null)
  const conflicts = live?.conflicts ?? view?.conflicts ?? []
  const subqueries = live
    ? live.subqueries.map((q, i) => live.done.find((d) => d.index === i) ?? { index: i, query: q, results: -1, decisions: [], total_ms: 0 })
    : (view?.subqueries ?? [])

  return (
    <div className="page-enter mx-auto max-w-7xl px-4 py-8 lg:px-8">
      <PageHeader
        title="Research"
        description="For bigger questions: Retrieva breaks your question into parts, searches for each, and writes a structured report with verified sources you can export."
      />
      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <Card className="h-fit">
          <CardHeader title="Past reports" />
          {history.isLoading ? (
            <Skeleton className="m-4 h-24" />
          ) : !history.data?.items.length ? (
            <p className="px-4 py-6 text-center text-xs text-muted-foreground">Reports you run are saved here</p>
          ) : (
            <ul className="divide-y divide-border">
              {history.data.items.map((r) => (
                <li key={r.id} className="group relative">
                  <button
                    type="button"
                    data-report-link
                    onClick={() => {
                      setLive(null)
                      navigate(`/app/research/${r.id}`)
                    }}
                    className={cn('w-full cursor-pointer px-4 py-3 pr-9 text-left', r.id === reportId ? 'bg-primary-soft' : 'hover:bg-surface-2')}
                  >
                    <p className="line-clamp-2 text-[13px] font-medium">{r.question}</p>
                    <p className="text-[11px] text-muted-foreground">{formatRelative(r.created_at)}</p>
                  </button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="absolute right-2 top-3 opacity-0 group-hover:opacity-100 focus:opacity-100"
                    aria-label="Delete report"
                    onClick={() => setDeleting(r.id)}
                  >
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="min-w-0 space-y-6">
          <Card className="p-4">
            <form onSubmit={start} className="space-y-3">
              <Textarea
                rows={3}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g. How do our vendor agreements handle termination, liability and data protection, and where do they differ?"
                aria-label="Research question"
                maxLength={2000}
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <ScopePicker value={scope} onChange={setScope} />
                <Button type="submit" disabled={question.trim().length < 5 || (!!live && live.stage !== 'done' && live.stage !== 'error')}>
                  <FileSearch /> Run research
                </Button>
              </div>
            </form>
          </Card>

          {live?.stage === 'error' && <ErrorState title="Research failed" error={live.error} />}
          {reportId && saved.isError && !live && <ErrorState error={saved.error} />}

          {(live || view) && (
            <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
              <div className="min-w-0 space-y-6">
                <Card>
                  <CardHeader
                    title={view?.question ?? question}
                    description={
                      view
                        ? `${view.llm_model ?? 'extractive'} · ${formatMs(view.total_ms)}`
                        : live?.stage === 'done'
                          ? 'Finished'
                          : `${live?.stage}…`
                    }
                    action={
                      view && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button size="sm" variant="secondary">
                              <Download /> Export
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent>
                            {(['pdf', 'docx', 'md'] as const).map((format) => (
                              <DropdownMenuItem
                                key={format}
                                onSelect={() =>
                                  researchApi.export(view.id, format, view.question).catch((e: Error) => toast.error(e.message))
                                }
                              >
                                {format === 'md' ? 'Markdown' : format.toUpperCase()}
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )
                    }
                  />
                  <div className="p-5">
                    {subqueries.length > 0 && (
                      <div className="mb-5">
                        <p className="mb-2 text-xs font-medium text-muted-foreground">Sub-questions</p>
                        <ul className="space-y-1.5">
                          {subqueries.map((s) => (
                            <li key={s.index} className="flex items-center gap-2 text-[13px]">
                              {s.results < 0 ? (
                                <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
                              ) : (
                                <CheckCircle2 className="size-3.5 text-success" />
                              )}
                              <span className="flex-1">{s.query}</span>
                              {s.results >= 0 && (
                                <span className="text-[11px] text-muted-foreground">
                                  {s.results} passages{s.labels?.length ? ` · ${s.labels.join(' ')}` : ''}
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {verification && (
                      <div className="mb-4 flex flex-wrap gap-1.5">
                        <Badge tone={verification.low_support ? 'warning' : 'success'}>
                          {verification.low_support ? 'Low evidence coverage' : 'Verified against sources'}
                        </Badge>
                        <Badge tone="outline">Valid citations {formatPercent(verification.citation_validity, 0)}</Badge>
                        <Badge tone="outline">Supported sentences {formatPercent(verification.evidence_coverage, 0)}</Badge>
                      </div>
                    )}
                    {conflicts.length > 0 && (
                      <ul className="mb-4 space-y-1 rounded-lg bg-warning-soft p-3 text-xs text-warning">
                        {conflicts.map((c) => (
                          <li key={c.labels.join('-')}>
                            Possible conflict {c.labels.join(' vs ')}: {c.reason}
                          </li>
                        ))}
                      </ul>
                    )}
                    {answer?.content ? (
                      <AnswerMarkdown content={answer.content} onCite={setActiveLabel} activeLabel={activeLabel} />
                    ) : live && live.stage !== 'error' ? (
                      <p className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="size-4 animate-spin" />
                        {live.stage === 'planning' ? 'Planning sub-questions…' : live.stage === 'retrieving' ? 'Retrieving evidence…' : 'Writing report…'}
                      </p>
                    ) : null}
                  </div>
                </Card>
              </div>
              <Card className="h-fit max-h-[80vh] overflow-hidden xl:sticky xl:top-4">
                <div className="h-[70vh]">
                  <EvidencePanel answer={answer} activeLabel={activeLabel} />
                </div>
              </Card>
            </div>
          )}
          {!live && !reportId && (
            <Card>
              <EmptyState
                icon={<Search className="size-5" />}
                title="Ask a research question"
                description="Best for questions with several parts, comparisons across documents, or anything needing a structured, cited write-up you can export."
              />
            </Card>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this report?"
        description="The report and its evidence snapshot are deleted."
        confirmLabel="Delete"
        destructive
        onConfirm={async () => {
          if (!deleting) return
          await researchApi.remove(deleting)
          await queryClient.invalidateQueries({ queryKey: ['research'] })
          if (deleting === reportId) navigate('/app/research', { replace: true })
        }}
      />
    </div>
  )
}

