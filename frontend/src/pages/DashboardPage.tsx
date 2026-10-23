import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  Circle,
  FileText,
  FileUp,
  Layers,
  MessageSquareText,
  Search,
  Timer,
} from 'lucide-react'
import { Link } from 'react-router'

import { ChartCard, StatTile } from '@/components/charts/Charts'
import { FileTypeIcon, StatusBadge } from '@/components/documents/DocumentBits'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { documentsApi, isProcessing } from '@/services/documents'
import { analyticsApi } from '@/services/insights'
import { shortDate } from '@/utils/chart'
import { formatMs, formatNumber, formatPercent, formatRelative } from '@/utils/format'

export function DashboardPage() {
  const { session, can } = useAuth()
  const overview = useQuery({ queryKey: ['analytics', 'overview'], queryFn: analyticsApi.overview, refetchInterval: 30_000 })
  const usage = useQuery({
    queryKey: ['analytics', 'usage', 14],
    queryFn: () => analyticsApi.usage(14),
    enabled: can('analytics:read'),
  })
  const recent = useQuery({
    queryKey: ['documents', { recent: true }],
    queryFn: () => documentsApi.list({ page_size: 6 }),
    refetchInterval: (q) => (q.state.data?.items.some((d) => isProcessing(d.status)) ? 3000 : false),
  })

  if (!session) return null
  const o = overview.data
  const firstName = session.user.full_name.split(' ')[0]
  const steps = [
    { done: (o?.documents.total ?? 0) > 0, label: 'Upload your first documents', to: '/app/documents?upload=1' },
    { done: (o?.documents.indexed ?? 0) > 0, label: 'Wait for processing to finish', to: '/app/documents' },
    { done: (o?.answers.total ?? 0) > 0, label: 'Ask a question and inspect the evidence', to: '/app/chat' },
  ]
  const onboarding = o && steps.some((s) => !s.done)

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 lg:px-8">
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description={`${session.organization.name} · ${session.organization.role}`}
        actions={
          <>
            {can('documents:write') && (
              <Button variant="secondary" asChild>
                <Link to="/app/documents?upload=1">
                  <FileUp /> Upload
                </Link>
              </Button>
            )}
            <Button asChild>
              <Link to="/app/chat">
                <MessageSquareText /> Ask a question
              </Link>
            </Button>
          </>
        }
      />

      {overview.isError ? (
        <ErrorState error={overview.error} onRetry={() => overview.refetch()} />
      ) : (
        <>
          {onboarding && (
            <Card className="mb-6 p-5">
              <p className="text-sm font-semibold">Get started</p>
              <ol className="mt-3 space-y-2">
                {steps.map((step) => (
                  <li key={step.label} className="flex items-center gap-2.5 text-[13.5px]">
                    {step.done ? (
                      <CheckCircle2 className="size-4 text-success" />
                    ) : (
                      <Circle className="size-4 text-muted-foreground" />
                    )}
                    <Link to={step.to} className={step.done ? 'text-muted-foreground line-through' : 'hover:text-primary'}>
                      {step.label}
                    </Link>
                  </li>
                ))}
              </ol>
            </Card>
          )}

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {overview.isLoading || !o ? (
              [0, 1, 2, 3, 4, 5, 6, 7].map((i) => <Skeleton key={i} className="h-[104px]" />)
            ) : (
              <>
                <StatTile
                  label="Indexed documents"
                  value={`${formatNumber(o.documents.indexed)} / ${formatNumber(o.documents.total)}`}
                  hint={o.documents.processing ? `${o.documents.processing} processing` : 'All processed'}
                  icon={<FileText />}
                />
                <StatTile label="Chunks indexed" value={formatNumber(o.documents.chunks)} hint="Searchable passages" icon={<Layers />} />
                <StatTile label="Queries" value={formatNumber(o.queries.total)} hint={`${formatNumber(o.conversations)} conversations`} icon={<Search />} />
                <StatTile
                  label="Avg. retrieval latency"
                  value={formatMs(o.queries.avg_retrieval_ms)}
                  hint={o.answers.avg_total_ms !== null ? `${formatMs(o.answers.avg_total_ms)} per answer end-to-end` : 'No answers yet'}
                  icon={<Timer />}
                />
                <StatTile
                  label="Citation validity"
                  value={formatPercent(o.answers.citation_validity_rate)}
                  hint="Citations that map to a provided source"
                  icon={<BadgeCheck />}
                />
                <StatTile
                  label="Evidence coverage"
                  value={formatPercent(o.answers.evidence_coverage)}
                  hint="Answer sentences supported by a cited passage"
                  icon={<BadgeCheck />}
                />
                <StatTile
                  label="Retrieval success"
                  value={formatPercent(o.queries.retrieval_success_rate)}
                  hint={o.answers.abstention_rate !== null ? `${formatPercent(o.answers.abstention_rate)} of questions abstained` : 'Queries returning evidence'}
                  icon={<Search />}
                />
                <StatTile
                  label="Failed ingestion jobs"
                  value={formatNumber(o.failed_ingestion_jobs)}
                  hint={o.documents.failed ? `${o.documents.failed} documents need attention` : 'No failures'}
                  icon={<AlertTriangle />}
                  tone={o.failed_ingestion_jobs ? 'danger' : 'default'}
                />
              </>
            )}
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1.5fr_1fr]">
            {can('analytics:read') ? (
              <ChartCard
                kind="bar"
                title="Activity — last 14 days"
                description="Queries and document uploads per day"
                data={usage.data?.series}
                loading={usage.isLoading}
                xKey="date"
                xFormatter={shortDate}
                series={[
                  { key: 'queries', label: 'Queries' },
                  { key: 'uploads', label: 'Uploads' },
                ]}
                format={(v) => formatNumber(v)}
              />
            ) : (
              <Card>
                <CardHeader title="Activity" />
                <EmptyState title="Usage charts are available to analysts and admins" />
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
              {recent.isLoading ? (
                <Skeleton className="m-4 h-40" />
              ) : !recent.data?.items.length ? (
                <EmptyState title="No documents yet" description="Uploaded documents will appear here." />
              ) : (
                <ul className="divide-y divide-border">
                  {recent.data.items.map((doc) => (
                    <li key={doc.id}>
                      <Link to={`/app/documents/${doc.id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-surface-2/60">
                        <FileTypeIcon type={doc.file_type} className="size-7" />
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
        </>
      )}
    </div>
  )
}
