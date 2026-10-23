import { AlertTriangle, ExternalLink, FileText, ShieldAlert, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger, Tooltip } from '@/components/ui/overlays'
import { Badge, EmptyState } from '@/components/ui/primitives'
import { cn } from '@/utils/cn'
import { formatMs, formatPercent } from '@/utils/format'

import { locationOf, type AnswerView, type EvidenceView } from './model'

const VALIDATION_BADGE: Record<EvidenceView['validation'], { tone: 'success' | 'warning' | 'neutral'; label: string; hint: string }> = {
  valid: { tone: 'success', label: 'Supports answer', hint: 'Cited, and the verifier found the cited claim in this passage.' },
  weak: { tone: 'warning', label: 'Weak support', hint: 'Cited, but the verifier found only partial support for the claim.' },
  uncited: { tone: 'neutral', label: 'Not cited', hint: 'Retrieved and shown to the model, but not cited in the answer.' },
}

const CLAIM_TONE = {
  supported: 'success',
  partial: 'warning',
  unsupported: 'danger',
  uncited: 'danger',
} as const

function Score({ label, value, hint, digits = 3 }: { label: string; value: number | null; hint: string; digits?: number }) {
  if (value === null || value === undefined) return null
  return (
    <Tooltip content={hint}>
      <span className="inline-flex cursor-help items-center gap-1 rounded border border-border px-1.5 py-0.5 font-mono text-[10.5px] text-muted-foreground">
        {label} {value.toFixed(digits)}
      </span>
    </Tooltip>
  )
}

function EvidenceCard({ item, active }: { item: EvidenceView; active: boolean }) {
  const ref = useRef<HTMLLIElement>(null)
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [active])
  const badge = VALIDATION_BADGE[item.validation]
  const link =
    item.documentId &&
    `/app/documents/${item.documentId}${item.start != null && item.end != null ? `?start=${item.start}&end=${item.end}` : ''}`
  return (
    <li
      ref={ref}
      id={`evidence-${item.label}`}
      className={cn(
        'rounded-lg border bg-surface p-3 transition-shadow',
        active ? 'border-primary shadow-[0_0_0_3px_color-mix(in_srgb,var(--primary)_18%,transparent)]' : 'border-border',
      )}
    >
      <div className="flex items-start gap-2">
        <span className="rounded bg-primary-soft px-1.5 py-0.5 font-mono text-[11px] font-semibold text-primary">{item.label}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium" title={item.title}>
            {item.title}
          </p>
          <p className="truncate text-xs text-muted-foreground">{locationOf(item) || 'Location not available'}</p>
        </div>
        <Tooltip content={badge.hint}>
          <span>
            <Badge tone={badge.tone}>{badge.label}</Badge>
          </span>
        </Tooltip>
      </div>
      <blockquote className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap border-l-2 border-border-strong pl-3 text-[12.5px] leading-relaxed text-foreground/90">
        {item.passage}
      </blockquote>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Score label="rerank" value={item.rerankScore} hint="Cross-encoder relevance (logit). Higher = more relevant. Not a probability." digits={2} />
        <Score label="rrf" value={item.fusionScore} hint="Reciprocal Rank Fusion score from dense + BM25 rankings." digits={4} />
        <Score label="cos" value={item.denseScore} hint="Cosine similarity between query and passage embeddings." />
        <Score label="bm25" value={item.sparseScore} hint="BM25 keyword score (unbounded)." digits={2} />
        <Score label="support" value={item.supportScore} hint="Verifier's support score for the claim citing this passage (0–1)." digits={2} />
        {link && (
          <Link to={link} className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
            Open passage <ExternalLink className="size-3" />
          </Link>
        )}
      </div>
    </li>
  )
}

export function EvidencePanel({
  answer,
  activeLabel,
  onClose,
  showHeader = true,
}: {
  answer: AnswerView | null
  activeLabel: string | null
  onClose?: () => void
  showHeader?: boolean
}) {
  if (!answer) {
    return (
      <EmptyState
        icon={<FileText className="size-5" />}
        title="Evidence appears here"
        description="Ask a question to see the passages retrieved for the answer, how they were scored, and whether the answer's citations hold up."
      />
    )
  }
  const v = answer.verification
  const trace = answer.trace
  return (
    <div className="flex h-full flex-col">
      <div className={cn("flex items-center justify-between border-b border-border px-4 py-3", !showHeader && "hidden")}>
        <p className="text-sm font-semibold">Evidence</p>
        {onClose && (
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close evidence panel">
            <X />
          </Button>
        )}
      </div>
      <Tabs defaultValue="sources" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="mx-4 mt-3 self-start">
          <TabsTrigger value="sources">Sources ({answer.evidence.length})</TabsTrigger>
          <TabsTrigger value="claims" disabled={!v}>
            Claims
          </TabsTrigger>
          <TabsTrigger value="trace" disabled={!trace}>
            Retrieval
          </TabsTrigger>
        </TabsList>

        <TabsContent value="sources" className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {trace?.suspicious_sources?.length ? (
            <div className="mb-3 flex gap-2 rounded-lg bg-warning-soft p-2.5 text-xs text-warning">
              <ShieldAlert className="size-4 shrink-0" />
              <span>
                {trace.suspicious_sources.join(', ')} contain instruction-like text. It was treated as document content,
                not as instructions.
              </span>
            </div>
          ) : null}
          {trace?.conflicts?.map((c) => (
            <div key={c.labels.join('-')} className="mb-3 flex gap-2 rounded-lg bg-warning-soft p-2.5 text-xs text-warning">
              <AlertTriangle className="size-4 shrink-0" />
              <span>
                Possible conflict between {c.labels.join(' and ')}: {c.reason}
              </span>
            </div>
          ))}
          {answer.evidence.length === 0 ? (
            <EmptyState className="py-8" title="No passages were retrieved" />
          ) : (
            <ul className="space-y-3">
              {answer.evidence.map((item) => (
                <EvidenceCard key={item.label} item={item} active={item.label === activeLabel} />
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="claims" className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {v && (
            <>
              <dl className="mb-4 grid grid-cols-3 gap-2 text-center">
                {(
                  [
                    ['Citation validity', v.citation_validity, 'Cited labels that exist in the provided sources'],
                    ['Citation precision', v.citation_precision, 'Valid citations whose passage supports the claim'],
                    ['Evidence coverage', v.evidence_coverage, 'Factual sentences supported by a cited passage'],
                  ] as const
                ).map(([label, value, hint]) => (
                  <Tooltip key={label} content={hint}>
                    <div className="cursor-help rounded-lg border border-border p-2">
                      <dd className="text-base font-semibold tabular-nums">{formatPercent(value, 0)}</dd>
                      <dt className="text-[11px] text-muted-foreground">{label}</dt>
                    </div>
                  </Tooltip>
                ))}
              </dl>
              <ul className="space-y-2">
                {v.claims.map((claim, i) => (
                  <li key={i} className="rounded-lg border border-border p-3 text-[12.5px]">
                    <div className="mb-1 flex items-center gap-2">
                      <Badge tone={CLAIM_TONE[claim.status]} className="capitalize">
                        {claim.status}
                      </Badge>
                      <span className="text-[11px] text-muted-foreground">
                        {claim.citations.length ? claim.citations.join(' ') : 'no citation'} · support{' '}
                        {claim.best_support.toFixed(2)}
                      </span>
                    </div>
                    <p className="leading-relaxed">{claim.text}</p>
                    {claim.invalid_citations.length > 0 && (
                      <p className="mt-1 text-danger">Cites non-existent source {claim.invalid_citations.join(', ')}</p>
                    )}
                    {claim.missing_numbers.length > 0 && (
                      <p className="mt-1 text-danger">
                        Figures not found in cited sources: {claim.missing_numbers.join(', ')}
                      </p>
                    )}
                    {claim.page_issues.map((issue) => (
                      <p key={issue} className="mt-1 text-danger">
                        {issue}
                      </p>
                    ))}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-[11px] text-muted-foreground">
                Verified independently after generation with the {v.scorer} scorer. These are verification signals, not
                model confidence.
              </p>
            </>
          )}
        </TabsContent>

        <TabsContent value="trace" className="min-h-0 flex-1 overflow-y-auto px-4 py-3 text-[12.5px]">
          {trace && (
            <div className="space-y-4">
              <section>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Queries executed</p>
                <ul className="space-y-1">
                  {trace.queries.map((q, i) => (
                    <li key={i} className="rounded-md bg-surface-2 px-2 py-1 font-mono text-[11.5px]">
                      {q}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Pipeline decisions</p>
                {trace.decisions.length ? (
                  <ul className="list-disc space-y-1 pl-4">
                    {trace.decisions.map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground">No optional techniques were triggered.</p>
                )}
              </section>
              <section>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Stage timings</p>
                <table className="w-full">
                  <tbody>
                    {Object.entries(trace.timings_ms).map(([stage, ms]) => (
                      <tr key={stage} className="border-b border-border last:border-0">
                        <td className="py-1 text-muted-foreground">{stage}</td>
                        <td className="py-1 text-right tabular-nums">{formatMs(ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <dl className="grid grid-cols-2 gap-2">
                <div>
                  <dt className="text-muted-foreground">Strategy</dt>
                  <dd>{String(trace.config.strategy ?? '—')}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Candidates fused</dt>
                  <dd>{trace.candidates_considered}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Reranker</dt>
                  <dd className="truncate font-mono text-[11px]">{trace.reranker ?? 'off'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Embedding model</dt>
                  <dd className="truncate font-mono text-[11px]">{trace.embedding_model ?? '—'}</dd>
                </div>
              </dl>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
