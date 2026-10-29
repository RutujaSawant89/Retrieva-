import { useMutation, useQuery } from '@tanstack/react-query'
import { ExternalLink, Search as SearchIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { RetrievalOptionsPanel } from '@/components/chat/RetrievalOptionsPanel'
import { ScopePicker } from '@/components/chat/ScopePicker'
import { Button } from '@/components/ui/button'
import { Callout, InfoTip } from '@/components/ui/help'
import { Tooltip } from '@/components/ui/overlays'
import { Badge, Card, CardHeader, EmptyState, Input, PageHeader, Skeleton } from '@/components/ui/primitives'
import { DEFAULT_OPTIONS, searchApi } from '@/services/chat'
import type { RetrievalOptions, RetrievalScopeInput, SearchResponse } from '@/types/api'
import { formatMs, formatRelative } from '@/utils/format'
import { TERMS } from '@/utils/glossary'
import { settingsSummary, stageName } from '@/utils/retrieval'

function ScoreCell({ value, digits, hint }: { value: number | null; digits: number; hint: string }) {
  return (
    <Tooltip content={hint}>
      <span className="cursor-help font-mono text-[11.5px] tabular-nums">{value === null ? '—' : value.toFixed(digits)}</span>
    </Tooltip>
  )
}

export function SearchPage() {
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<RetrievalOptions>(DEFAULT_OPTIONS)
  const [scope, setScope] = useState<RetrievalScopeInput>({ document_ids: [], collection_ids: [] })
  const [result, setResult] = useState<SearchResponse | null>(null)

  const history = useQuery({ queryKey: ['search', 'history'], queryFn: () => searchApi.history({ kind: 'search' }) })
  const search = useMutation({
    mutationFn: (q: string) => searchApi.search({ query: q, scope, options }),
    onSuccess: (data) => {
      setResult(data)
      void history.refetch()
    },
    onError: (error) => toast.error(error.message),
  })

  const run = (q: string) => {
    if (!q.trim()) return
    setQuery(q)
    search.mutate(q.trim())
  }

  return (
    <div className="page-enter mx-auto max-w-7xl px-4 py-8 lg:px-8">
      <PageHeader
        title="Search Explorer"
        description="See exactly which passages Retrieva finds for a question, and why each one ranks where it does."
      />
      <form
        className="mb-6 flex flex-wrap gap-2"
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          run(query)
        }}
      >
        <div className="relative min-w-64 flex-1">
          <SearchIcon className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input
            className="h-10 pl-9"
            placeholder="Type a question or keywords, e.g. termination notice period"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search query"
            maxLength={2000}
          />
        </div>
        <ScopePicker value={scope} onChange={setScope} />
        <Button type="submit" size="lg" loading={search.isPending} disabled={!query.trim()}>
          Search
        </Button>
      </form>

      <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Search settings" description="Change a setting and search again to compare" />
            <div className="p-4">
              <RetrievalOptionsPanel value={options} onChange={setOptions} />
            </div>
          </Card>
          <Card>
            <CardHeader title="Recent searches" />
            {history.data?.items.length ? (
              <ul className="divide-y divide-border">
                {history.data.items.slice(0, 8).map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className="w-full cursor-pointer px-4 py-2.5 text-left hover:bg-surface-2"
                      onClick={() => run(item.query)}
                    >
                      <p className="truncate text-[13px]">{item.query}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {item.result_count} results · {formatMs(item.retrieval_ms)} · {formatRelative(item.created_at)}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-4 py-6 text-center text-xs text-muted-foreground">Your searches will appear here</p>
            )}
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          {search.isPending ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          ) : !result ? (
            <Card>
              <EmptyState
                icon={<SearchIcon className="size-5" />}
                title="Search your documents"
                description="Unlike AI Chat, this shows the raw passages with no written answer, so you can check what Retrieva would read."
              />
              <div className="px-6 pb-6">
                <Callout title="How ranking works">
                  Each passage is scored by {TERMS.semanticSearch.label} (meaning) and {TERMS.keywordSearch.label} (exact
                  words). Their rankings are combined, then {TERMS.relevanceOptimization.label} re-reads the best candidates.
                  Hover any score to see the technique behind it.
                </Callout>
              </div>
            </Card>
          ) : (
            <>
              <Card className="p-4">
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px]">
                  <span>
                    <strong>{result.results.length}</strong> passages, chosen from {result.candidates_considered} candidates
                  </span>
                  <span className="text-muted-foreground">{settingsSummary(options)}</span>
                  <span className="text-muted-foreground">Took {formatMs(result.total_ms)}</span>
                  <Tooltip content={`Relevance model: ${result.reranker ?? 'off'} · Embedding model: ${result.embedding_model}`}>
                    <span className="cursor-help text-muted-foreground underline decoration-dotted underline-offset-2">Models used</span>
                  </Tooltip>
                </div>
                {result.queries.length > 1 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {result.queries.map((q, i) => (
                      <Badge key={i} tone={i === 0 ? 'primary' : 'outline'}>
                        {q}
                      </Badge>
                    ))}
                  </div>
                )}
                {result.decisions.length > 0 && (
                  <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                    {result.decisions.map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                )}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {Object.entries(result.timings_ms).map(([stage, ms]) => (
                    <span key={stage} className="rounded border border-border px-1.5 py-0.5 font-mono text-[10.5px] text-muted-foreground">
                      {stageName(stage)} {formatMs(ms)}
                    </span>
                  ))}
                </div>
              </Card>
              {result.results.length === 0 ? (
                <Card>
                  <EmptyState title="No passages matched" description="Try different wording or widen the scope." />
                </Card>
              ) : (
                <ol className="space-y-3">
                  {result.results.map((r) => (
                    <li key={r.chunk_id}>
                      <Card className="p-4">
                        <div className="flex flex-wrap items-start gap-3">
                          <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary-soft font-mono text-xs font-semibold text-primary">
                            {r.ranks.final}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">{r.document_title}</p>
                            <p className="truncate text-xs text-muted-foreground">{r.location || 'No page information'}</p>
                          </div>
                          <Link
                            to={`/app/documents/${r.document_id}?start=${r.start_char}&end=${r.end_char}`}
                            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                          >
                            Open in document <ExternalLink className="size-3" />
                          </Link>
                        </div>
                        <p className="mt-3 whitespace-pre-wrap text-[13px] leading-relaxed">{r.compressed ?? r.content}</p>
                        <div className="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-surface-2 p-2.5 text-[11px] sm:grid-cols-4">
                          <div>
                            <p className="text-muted-foreground">Semantic · rank {r.ranks.dense ?? '—'}</p>
                            <ScoreCell value={r.scores.dense} digits={3} hint={`${TERMS.semanticSearch.technical}: cosine similarity, higher is closer in meaning.`} />
                          </div>
                          <div>
                            <p className="text-muted-foreground">Keyword · rank {r.ranks.sparse ?? '—'}</p>
                            <ScoreCell value={r.scores.sparse} digits={2} hint={`${TERMS.keywordSearch.technical} score (unbounded).`} />
                          </div>
                          <div>
                            <p className="flex items-center gap-1 text-muted-foreground">Combined <InfoTip term="fusion" className="size-3" /></p>
                            <ScoreCell value={r.scores.fusion} digits={4} hint="Reciprocal Rank Fusion of the semantic and keyword rankings." />
                          </div>
                          <div>
                            <p className="flex items-center gap-1 text-muted-foreground">Relevance <InfoTip term="relevanceOptimization" className="size-3" /></p>
                            <ScoreCell value={r.scores.rerank} digits={2} hint="Cross-encoder relevance logit. Higher is more relevant; not a probability." />
                          </div>
                        </div>
                      </Card>
                    </li>
                  ))}
                </ol>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
