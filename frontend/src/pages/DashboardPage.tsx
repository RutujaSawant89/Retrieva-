import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Circle,
  FileSearch,
  FileText,
  FileUp,
  GitCompareArrows,
  MessageSquareText,
  Search,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'
import { Link } from 'react-router'

import { ChartCard, StatTile } from '@/components/charts/Charts'
import { FileTypeIcon, StatusBadge } from '@/components/documents/DocumentBits'
import { Button } from '@/components/ui/button'
import { InfoTip } from '@/components/ui/help'
import { Badge, Card, CardHeader, EmptyState, ErrorState, Skeleton } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { chatApi, searchApi } from '@/services/chat'
import { documentsApi, isProcessing } from '@/services/documents'
import { analyticsApi } from '@/services/insights'
import { shortDate } from '@/utils/chart'
import { cn } from '@/utils/cn'
import { formatNumber, formatPercent, formatRelative } from '@/utils/format'

function greeting(): string {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
}

interface QuickAction {
  to: string
  title: string
  description: string
  icon: LucideIcon
  permission?: string
  primary?: boolean
}

const QUICK_ACTIONS: QuickAction[] = [
  {
    to: '/app/chat',
    title: 'Ask a question',
    description: 'Get an answer with sources you can check',
    icon: MessageSquareText,
    permission: 'chat:use',
    primary: true,
  },
  {
    to: '/app/documents?upload=1',
    title: 'Upload documents',
    description: 'PDF, Word, text, Markdown, CSV or HTML',
    icon: FileUp,
    permission: 'documents:write',
  },
  {
    to: '/app/research',
    title: 'Start research',
    description: 'A structured, cited report on a bigger question',
    icon: FileSearch,
    permission: 'research:use',
  },
  {
    to: '/app/compare',
    title: 'Compare documents',
    description: 'See what changed between two versions',
    icon: GitCompareArrows,
    permission: 'documents:read',
  },
]

export function DashboardPage() {
  const { session, can } = useAuth()
  const overview = useQuery({ queryKey: ['analytics', 'overview'], queryFn: analyticsApi.overview, refetchInterval: 30_000 })
  const usage = useQuery({
    queryKey: ['analytics', 'usage', 14],
    queryFn: () => analyticsApi.usage(14),
    enabled: can('analytics:read'),
  })
  const recentDocs = useQuery({
    queryKey: ['documents', { recent: true }],
    queryFn: () => documentsApi.list({ page_size: 5 }),
    refetchInterval: (q) => (q.state.data?.items.some((d) => isProcessing(d.status)) ? 3000 : false),
  })
  const conversations = useQuery({
    queryKey: ['conversations', 'recent'],
    queryFn: () => chatApi.conversations({ page: 1 }),
    enabled: can('chat:use'),
  })
  const questions = useQuery({
    queryKey: ['search', 'history', 'dashboard'],
    queryFn: () => searchApi.history({ page: 1 }),
    enabled: can('search:use'),
  })

  if (!session) return null
  const o = overview.data
  const firstName = session.user.full_name.split(' ')[0]
  const actions = QUICK_ACTIONS.filter((a) => !a.permission || can(a.permission))
  const steps = [
    { done: (o?.documents.total ?? 0) > 0, label: 'Upload your first documents', to: '/app/documents?upload=1' },
    { done: (o?.documents.indexed ?? 0) > 0, label: 'Wait until they show “Ready”', to: '/app/documents' },
    { done: (o?.answers.total ?? 0) > 0, label: 'Ask a question and click a source to check it', to: '/app/chat' },
  ]
  const onboarding = o && steps.some((s) => !s.done)

  return (
    <div className="page-enter mx-auto max-w-6xl space-y-8 px-4 py-8 lg:px-8">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {greeting()}, {firstName}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Ask questions about {session.organization.name}&rsquo;s documents and get answers you can verify.
          </p>
        </div>
      </section>

      <section aria-label="Quick actions" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {actions.map((action) => (
          <Link
            key={action.to}
            to={action.to}
            className={cn(
              'group flex flex-col rounded-xl border p-4 transition-all hover:-translate-y-0.5 hover:shadow-[var(--shadow-pop)]',
              action.primary
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-surface hover:border-primary/40',
            )}
          >
            <span
              className={cn(
                'flex size-9 items-center justify-center rounded-lg',
                action.primary ? 'bg-white/15' : 'bg-primary-soft text-primary',
              )}
            >
              <action.icon className="size-4" />
            </span>
            <span className="mt-3 flex items-center gap-1 text-sm font-semibold">
              {action.title}
              <ArrowRight className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
            </span>
            <span className={cn('mt-0.5 text-xs', action.primary ? 'text-primary-foreground/80' : 'text-muted-foreground')}>
              {action.description}
            </span>
          </Link>
        ))}
      </section>

      {overview.isError ? (
        <ErrorState error={overview.error} onRetry={() => overview.refetch()} />
      ) : (
        <>
          {onboarding && (
            <Card className="p-5">
              <p className="text-sm font-semibold">Get started in three steps</p>
              <ol className="mt-3 grid gap-2 sm:grid-cols-3">
                {steps.map((step, i) => (
                  <li key={step.label}>
                    <Link
                      to={step.to}
                      className={cn(
                        'flex h-full items-start gap-2.5 rounded-lg border border-border p-3 text-[13px] transition-colors hover:bg-surface-2',
                        step.done && 'text-muted-foreground',
                      )}
                    >
                      {step.done ? (
                        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="Done" />
                      ) : (
                        <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="To do" />
                      )}
                      <span>
                        <span className="block text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                          Step {i + 1}
                        </span>
                        <span className={cn(step.done && 'line-through')}>{step.label}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ol>
            </Card>
          )}

          {o && (o.documents.failed > 0 || o.failed_ingestion_jobs > 0) && (
            <Link
              to="/app/documents?status=failed"
              className="flex items-center gap-3 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-[13px] text-danger hover:brightness-[0.98]"
            >
              <AlertTriangle className="size-4 shrink-0" />
              <span className="flex-1">
                {o.documents.failed} document{o.documents.failed === 1 ? '' : 's'} could not be processed. Open them to see why.
              </span>
              <ArrowRight className="size-4" />
            </Link>
          )}

          <section aria-label="Workspace at a glance" className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {overview.isLoading || !o ? (
              [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px]" />)
            ) : (
              <>
                <StatTile
                  label="Documents ready"
                  value={`${formatNumber(o.documents.indexed)} / ${formatNumber(o.documents.total)}`}
                  hint={o.documents.processing ? `${o.documents.processing} still processing` : 'All documents are ready'}
                  icon={<FileText />}
                />
                <StatTile
                  label="Questions asked"
                  value={formatNumber(o.queries.total)}
                  hint={`${formatNumber(o.conversations)} conversation${o.conversations === 1 ? '' : 's'}`}
                  icon={<Search />}
                />
                <StatTile
                  label={
                    <span className="inline-flex items-center gap-1">
                      Answers backed by sources <InfoTip term="evidenceCoverage" />
                    </span>
                  }
                  value={formatPercent(o.answers.evidence_coverage, 0)}
                  hint={o.answers.total ? `Across ${formatNumber(o.answers.total)} answer${o.answers.total === 1 ? "" : "s"}` : 'No answers yet'}
                  icon={<ShieldCheck />}
                />
                <StatTile
                  label={
                    <span className="inline-flex items-center gap-1">
                      Declined for lack of evidence <InfoTip term="evidenceInsufficient" />
                    </span>
                  }
                  value={formatPercent(o.answers.abstention_rate, 0)}
                  hint="Retrieva says so rather than guess"
                  icon={<ShieldCheck />}
                />
              </>
            )}
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            {can('chat:use') && (
              <Card>
                <CardHeader
                  title="Recent conversations"
                  action={
                    <Link to="/app/chat" className="text-xs font-medium text-primary hover:underline">
                      New chat
                    </Link>
                  }
                />
                {conversations.isLoading ? (
                  <Skeleton className="m-4 h-32" />
                ) : !conversations.data?.items.length ? (
                  <EmptyState
                    className="py-10"
                    icon={<MessageSquareText className="size-5" />}
                    title="No conversations yet"
                    description="Ask your first question — every answer links to the passages it came from."
                    action={
                      <Button asChild size="sm">
                        <Link to="/app/chat">Ask a question</Link>
                      </Button>
                    }
                  />
                ) : (
                  <ul className="divide-y divide-border">
                    {conversations.data.items.slice(0, 5).map((c) => (
                      <li key={c.id}>
                        <Link to={`/app/chat/${c.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-surface-2/60">
                          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
                            <MessageSquareText className="size-4" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13px] font-medium">{c.title}</span>
                            <span className="block text-[11px] text-muted-foreground">
                              {c.message_count} messages · {formatRelative(c.updated_at)}
                            </span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            )}

            <Card>
              <CardHeader
                title="Recent documents"
                action={
                  <Link to="/app/documents" className="text-xs font-medium text-primary hover:underline">
                    View all
                  </Link>
                }
              />
              {recentDocs.isLoading ? (
                <Skeleton className="m-4 h-32" />
              ) : !recentDocs.data?.items.length ? (
                <EmptyState
                  className="py-10"
                  icon={<FileUp className="size-5" />}
                  title="No documents yet"
                  description="Upload files to build your knowledge base."
                  action={
                    can('documents:write') && (
                      <Button asChild size="sm">
                        <Link to="/app/documents?upload=1">Upload documents</Link>
                      </Button>
                    )
                  }
                />
              ) : (
                <ul className="divide-y divide-border">
                  {recentDocs.data.items.map((doc) => (
                    <li key={doc.id}>
                      <Link to={`/app/documents/${doc.id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-surface-2/60">
                        <FileTypeIcon type={doc.file_type} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium">{doc.title}</span>
                          <span className="block text-[11px] text-muted-foreground">{formatRelative(doc.created_at)}</span>
                        </span>
                        <StatusBadge status={doc.status} progress={doc.progress} />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
            {can('analytics:read') && (
              <ChartCard
                kind="bar"
                title="Activity — last 14 days"
                description="Questions asked and documents uploaded per day"
                data={usage.data?.series}
                loading={usage.isLoading}
                xKey="date"
                xFormatter={shortDate}
                series={[
                  { key: 'queries', label: 'Questions' },
                  { key: 'uploads', label: 'Uploads' },
                ]}
                format={(v) => formatNumber(v)}
              />
            )}
            {can('search:use') && (
              <Card>
                <CardHeader title="Your recent questions" description="Searches and chat questions, newest first" />
                {questions.isLoading ? (
                  <Skeleton className="m-4 h-32" />
                ) : !questions.data?.items.length ? (
                  <EmptyState className="py-10" title="Nothing asked yet" />
                ) : (
                  <ul className="divide-y divide-border">
                    {questions.data.items.slice(0, 6).map((q) => (
                      <li key={q.id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
                        <span className="min-w-0 flex-1 truncate">{q.query}</span>
                        <Badge tone={q.success ? 'success' : 'warning'}>{q.success ? 'Answered' : 'No evidence'}</Badge>
                        <span className="hidden shrink-0 text-[11px] text-muted-foreground sm:block">
                          {formatRelative(q.created_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  )
}
