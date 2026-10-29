import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { ChartCard, StatTile } from '@/components/charts/Charts'
import { InfoTip } from '@/components/ui/help'
import { Select } from '@/components/ui/overlays'
import { ErrorState, PageHeader, Skeleton } from '@/components/ui/primitives'
import { analyticsApi } from '@/services/insights'
import { shortDate } from '@/utils/chart'
import { formatMs, formatNumber, formatPercent } from '@/utils/format'
import { STRATEGY_TERMS, stageName } from '@/utils/retrieval'

const RANGES = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
]

const msFormat = (v: number | null | undefined) => (v === null || v === undefined ? '—' : formatMs(v))

export function AnalyticsPage() {
  const [days, setDays] = useState(30)
  const overview = useQuery({ queryKey: ['analytics', 'overview'], queryFn: analyticsApi.overview })
  const retrieval = useQuery({ queryKey: ['analytics', 'retrieval', days], queryFn: () => analyticsApi.retrieval(days) })
  const usage = useQuery({ queryKey: ['analytics', 'usage', days], queryFn: () => analyticsApi.usage(days) })

  const o = overview.data
  const strategyRows = retrieval.data?.by_strategy.map((s) => ({
    ...s,
    strategy: STRATEGY_TERMS[s.strategy as keyof typeof STRATEGY_TERMS]?.label ?? s.strategy,
    success_pct: s.success_rate !== null ? s.success_rate * 100 : null,
  }))

  return (
    <div className="page-enter mx-auto max-w-6xl px-4 py-8 lg:px-8">
      <PageHeader
        title="Analytics"
        description="Usage, speed and answer quality, measured from this workspace's real questions, answers and uploads."
        actions={
          <Select
            className="w-40"
            aria-label="Time range"
            value={String(days)}
            onValueChange={(v) => setDays(Number(v))}
            options={RANGES}
          />
        }
      />
      {overview.isError || retrieval.isError || usage.isError ? (
        <ErrorState
          error={overview.error ?? retrieval.error ?? usage.error}
          onRetry={() => {
            void overview.refetch()
            void retrieval.refetch()
            void usage.refetch()
          }}
        />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {!o || !usage.data ? (
              [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px]" />)
            ) : (
              <>
                <StatTile label="Questions & searches" value={formatNumber(o.queries.total)} hint={`${usage.data.active_users} active users in range`} />
                <StatTile label="Avg. answer writing time" value={formatMs(o.answers.avg_generation_ms)} hint="Answered questions only" />
                <StatTile label={<span className="inline-flex items-center gap-1">Declined for lack of evidence <InfoTip term="evidenceInsufficient" /></span>} value={formatPercent(o.answers.abstention_rate)} hint={`${o.answers.abstained} of ${o.answers.total} answers withheld`} />
                <StatTile label={<span className="inline-flex items-center gap-1">Valid citations <InfoTip term="citationValidity" /></span>} value={formatPercent(o.answers.citation_validity_rate)} hint={`Supported sentences ${formatPercent(o.answers.evidence_coverage)}`} />
              </>
            )}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <ChartCard
              kind="bar"
              title="Activity"
              description="Searches per day across chat, Search Explorer, research and evaluation"
              data={usage.data?.series}
              loading={usage.isLoading}
              xKey="date"
              xFormatter={shortDate}
              series={[{ key: 'queries', label: 'Queries' }]}
              format={(v) => formatNumber(v)}
            />
            <ChartCard
              kind="bar"
              title="Document ingestion"
              description="Uploads and failed processing jobs per day"
              data={usage.data?.series}
              loading={usage.isLoading}
              xKey="date"
              xFormatter={shortDate}
              series={[
                { key: 'uploads', label: 'Uploads' },
                { key: 'failures', label: 'Failures' },
              ]}
              format={(v) => formatNumber(v)}
            />
            <ChartCard
              kind="line"
              title="Search speed"
              description="Mean and 95th percentile per day"
              data={retrieval.data?.latency}
              loading={retrieval.isLoading}
              xKey="date"
              xFormatter={shortDate}
              series={[
                { key: 'avg_ms', label: 'Mean' },
                { key: 'p95_ms', label: 'p95' },
              ]}
              format={msFormat}
            />
            <ChartCard
              kind="line"
              title="Answer speed"
              description="Time to write the answer, and total time from question to answer"
              data={retrieval.data?.response_latency}
              loading={retrieval.isLoading}
              xKey="date"
              xFormatter={shortDate}
              series={[
                { key: 'generation_ms', label: 'Generation' },
                { key: 'total_ms', label: 'End-to-end' },
              ]}
              format={msFormat}
            />
            <ChartCard
              kind="bar"
              title="Speed by search method"
              description="Mean and p95 over the selected range"
              data={strategyRows}
              loading={retrieval.isLoading}
              xKey="strategy"
              xLabel="Strategy"
              series={[
                { key: 'avg_ms', label: 'Mean' },
                { key: 'p95_ms', label: 'p95' },
              ]}
              format={msFormat}
              emptyText="Run searches with different strategies to compare them"
            />
            <ChartCard
              kind="bar"
              title="Where search time goes"
              description="Average time per search step"
              data={retrieval.data?.stage_ms.map((row) => ({ ...row, stage: stageName(row.stage) }))}
              loading={retrieval.isLoading}
              xKey="stage"
              xLabel="Stage"
              series={[{ key: 'avg_ms', label: 'Avg. time' }]}
              format={msFormat}
            />
            <ChartCard
              kind="bar"
              title="Usage trend"
              description="Conversations started and API calls per day"
              data={usage.data?.series}
              loading={usage.isLoading}
              xKey="date"
              xFormatter={shortDate}
              series={[
                { key: 'conversations', label: 'Conversations' },
                { key: 'api_calls', label: 'API calls' },
              ]}
              format={(v) => formatNumber(v)}
            />
            <ChartCard
              kind="bar"
              title="AI model usage (tokens)"
              description="Prompt and completion tokens per day (as reported by the provider)"
              data={usage.data?.series}
              loading={usage.isLoading}
              xKey="date"
              xFormatter={shortDate}
              stacked
              series={[
                { key: 'prompt_tokens', label: 'Prompt' },
                { key: 'completion_tokens', label: 'Completion' },
              ]}
              format={(v) => formatNumber(v)}
              emptyText="No LLM tokens used (extractive mode or no answers yet)"
            />
          </div>
        </div>
      )}
    </div>
  )
}
