import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeftRight, GitCompareArrows } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { StatTile } from '@/components/charts/Charts'
import { AnswerMarkdown } from '@/components/chat/AnswerMarkdown'
import { Button } from '@/components/ui/button'
import { Select, Tabs, TabsList, TabsTrigger } from '@/components/ui/overlays'
import { Badge, Card, CardHeader, EmptyState, PageHeader, Skeleton } from '@/components/ui/primitives'
import { documentsApi } from '@/services/documents'
import { compareApi } from '@/services/insights'
import type { ComparePassage, CompareResult } from '@/types/api'
import { cn } from '@/utils/cn'
import { formatPercent } from '@/utils/format'

type Filter = 'changed' | 'only_a' | 'only_b' | 'same'

function Passage({ passage, figures, tone }: { passage: ComparePassage | null; figures?: string[]; tone?: 'a' | 'b' }) {
  if (!passage) {
    return <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">No comparable passage</p>
  }
  const link = `/app/documents/${passage.document_id}?start=${passage.start}&end=${passage.end}`
  let text: React.ReactNode = passage.text
  if (figures?.length) {
    const pattern = new RegExp(`(${figures.map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g')
    text = passage.text.split(pattern).map((part, i) =>
      figures.some((f) => part.replace(/,/g, '') === f) ? (
        <mark key={i} className={cn('rounded px-0.5', tone === 'a' ? 'bg-danger-soft text-danger' : 'bg-success-soft text-success')}>
          {part}
        </mark>
      ) : (
        part
      ),
    )
  }
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="mb-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono font-semibold text-foreground">{passage.label}</span>
        <span className="truncate">{[passage.page ? `p. ${passage.page}` : null, passage.section].filter(Boolean).join(' · ')}</span>
        <Link to={link} className="ml-auto text-primary hover:underline">
          Open
        </Link>
      </div>
      <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed">{text}</p>
    </div>
  )
}

export function ComparePage() {
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [filter, setFilter] = useState<Filter>('changed')
  const documents = useQuery({
    queryKey: ['documents', 'compare-picker'],
    queryFn: () => documentsApi.list({ status: ['completed'], page_size: 100, sort: 'title', order: 'asc' }),
  })
  const compare = useMutation({
    mutationFn: () => compareApi.compare(a, b),
    onError: (error) => toast.error(error.message),
  })
  const result: CompareResult | undefined = compare.data
  const options = (documents.data?.items ?? []).map((d) => ({ value: d.id, label: d.title }))

  const rows = useMemo(() => {
    if (!result) return []
    if (filter === 'only_b') return result.only_b.map((p) => ({ kind: 'only_b' as const, a: null, b: p, similarity: null, figures: undefined }))
    return result.alignments.filter((al) => al.kind === filter)
  }, [result, filter])

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 lg:px-8">
      <PageHeader
        title="Compare documents"
        description="Aligns passages of two documents by meaning and reports what is the same, what changed, what was added or removed, and where figures disagree."
      />
      <Card className="mb-6 p-4">
        <div className="grid items-end gap-3 sm:grid-cols-[1fr_auto_1fr_auto]">
          <Select aria-label="First document" value={a} onValueChange={setA} options={options} placeholder="First document" />
          <ArrowLeftRight className="mx-auto hidden size-4 text-muted-foreground sm:block" />
          <Select aria-label="Second document" value={b} onValueChange={setB} options={options} placeholder="Second document" />
          <Button onClick={() => compare.mutate()} loading={compare.isPending} disabled={!a || !b || a === b}>
            <GitCompareArrows /> Compare
          </Button>
        </div>
        {documents.data && documents.data.items.length < 2 && (
          <p className="mt-2 text-xs text-muted-foreground">Upload at least two documents to compare them.</p>
        )}
      </Card>

      {compare.isPending && <Skeleton className="h-64" />}
      {!result && !compare.isPending && (
        <Card>
          <EmptyState
            icon={<GitCompareArrows className="size-5" />}
            title="Pick two documents"
            description="Useful for contract versions, policy revisions, or two reports covering the same topic."
          />
        </Card>
      )}
      {result && !compare.isPending && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <StatTile label="Equivalent" value={result.stats.same ?? 0} hint="Near-identical passages" />
            <StatTile label="Changed" value={result.stats.changed ?? 0} hint="Related but different" />
            <StatTile label={`Only in ${result.documents[0]?.title}`} value={result.stats.only_a ?? 0} hint="No counterpart" />
            <StatTile label={`Only in ${result.documents[1]?.title}`} value={result.stats.only_b ?? 0} hint="No counterpart" />
            <StatTile label="Figure conflicts" value={result.contradictions.length} hint="Related passages, different numbers" tone={result.contradictions.length ? 'danger' : 'default'} />
          </div>

          {result.contradictions.length > 0 && (
            <Card className="border-warning/40">
              <CardHeader title="Potential contradictions" description="Matched passages whose figures differ. Check the source before relying on either." />
              <ul className="divide-y divide-border">
                {result.contradictions.map((c) => (
                  <li key={`${c.a}-${c.b}`} className="flex items-start gap-3 px-5 py-3 text-[13px]">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
                    <span>
                      <span className="font-mono text-xs">
                        {c.a} ↔ {c.b}
                      </span>{' '}
                      {c.reason}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card>
            <CardHeader
              title="Summary"
              description={result.summary ? 'Generated from the aligned passages and verified against them' : undefined}
              action={
                result.summary_verification && 'citation_validity' in result.summary_verification ? (
                  <Badge tone="outline">citations valid {formatPercent(result.summary_verification.citation_validity, 0)}</Badge>
                ) : null
              }
            />
            <div className="p-5">
              {result.summary ? (
                <AnswerMarkdown content={result.summary} />
              ) : (
                <p className="text-sm text-muted-foreground">{result.summary_note ?? result.stats.note}</p>
              )}
            </div>
          </Card>

          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
              <p className="text-sm font-semibold">Passage alignment</p>
              <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
                <TabsList>
                  <TabsTrigger value="changed">Changed ({result.stats.changed ?? 0})</TabsTrigger>
                  <TabsTrigger value="only_a">Only A ({result.stats.only_a ?? 0})</TabsTrigger>
                  <TabsTrigger value="only_b">Only B ({result.stats.only_b ?? 0})</TabsTrigger>
                  <TabsTrigger value="same">Same ({result.stats.same ?? 0})</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
            <div className="grid grid-cols-2 gap-3 border-b border-border px-5 py-2 text-xs font-medium text-muted-foreground">
              <span className="truncate">A · {result.documents[0]?.title}</span>
              <span className="truncate">B · {result.documents[1]?.title}</span>
            </div>
            {rows.length === 0 ? (
              <EmptyState className="py-10" title="Nothing in this category" />
            ) : (
              <ul className="divide-y divide-border">
                {rows.map((row, i) => (
                  <li key={i} className="grid gap-3 px-5 py-4 md:grid-cols-2">
                    <Passage passage={row.a} figures={row.figures?.a} tone="a" />
                    <Passage passage={row.b} figures={row.figures?.b} tone="b" />
                    {row.similarity !== null && (
                      <p className="text-[11px] text-muted-foreground md:col-span-2">Semantic similarity {row.similarity.toFixed(3)}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
