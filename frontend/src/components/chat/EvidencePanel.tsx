import { AlertTriangle, ChevronRight, ExternalLink, FileText, ShieldAlert, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Disclosure, InfoTip } from '@/components/ui/help'
import { Tabs, TabsContent, TabsList, TabsTrigger, Tooltip } from '@/components/ui/overlays'
import { Badge, EmptyState } from '@/components/ui/primitives'
import { cn } from '@/utils/cn'
import { formatMs, formatPercent } from '@/utils/format'
import { TERMS } from '@/utils/glossary'
import { stageName } from '@/utils/retrieval'

import { locationOf, type AnswerView, type EvidenceView } from './model'

const VALIDATION_BADGE: Record<EvidenceView['validation'], { tone: 'success' | 'warning' | 'neutral'; label: string; hint: string }> = {
  valid: { tone: 'success', label: 'Supports answer', hint: 'Cited in the answer, and Source Verification found the claim in this passage.' },
  weak: { tone: 'warning', label: 'Partial support', hint: 'Cited in the answer, but only part of the claim was found in this passage.' },
  uncited: { tone: 'neutral', label: 'Not cited', hint: 'Found during search and read, but not used in the answer.' },
}

const CLAIM_STATUS = {
  supported: { tone: 'success', label: 'Supported' },
  partial: { tone: 'warning', label: 'Partly supported' },
  unsupported: { tone: 'danger', label: 'Not supported' },
  uncited: { tone: 'danger', label: 'No source cited' },
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
  const [showScores, setShowScores] = useState(false)
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [active])
  const badge = VALIDATION_BADGE[item.validation]
  const link =
    item.documentId &&
    `/app/documents/${item.documentId}${item.start != null && item.end != null ? `?start=${item.start}&end=${item.end}` : ''}`
  const hasScores = [item.rerankScore, item.fusionScore, item.denseScore, item.sparseScore, item.supportScore].some(
    (s) => s !== null && s !== undefined,
  )
  return (
    <li
      ref={ref}
      id={`evidence-${item.label}`}
      className={cn(
        'rounded-xl border bg-surface p-3 transition-shadow',
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
      <blockquote className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap border-l-2 border-primary/30 pl-3 text-[12.5px] leading-relaxed text-foreground/90 scroll-thin">
        {item.passage}
      </blockquote>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {hasScores && (
          <button
            type="button"
            onClick={() => setShowScores((s) => !s)}
            aria-expanded={showScores}
            className="inline-flex cursor-pointer items-center gap-0.5 text-[11px] text-muted-foreground hover:text-foreground"
          >
            <ChevronRight className={cn('size-3 transition-transform', showScores && 'rotate-90')} /> Technical details
          </button>
        )}
        {link && (
          <Link to={link} className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
            Open passage <ExternalLink className="size-3" />
          </Link>
        )}
      </div>
      {showScores && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Score label="relevance" value={item.rerankScore} hint={`${TERMS.relevanceOptimization.technical}. Higher = more relevant; not a probability.`} digits={2} />
          <Score label="combined" value={item.fusionScore} hint={`${TERMS.fusion.technical} from semantic + keyword rankings.`} digits={4} />
          <Score label="semantic" value={item.denseScore} hint="Cosine similarity between question and passage embeddings." />
          <Score label="keyword" value={item.sparseScore} hint="BM25 keyword score (unbounded)." digits={2} />
          <Score label="support" value={item.supportScore} hint="Source Verification support score for the sentence citing this passage (0–1)." digits={2} />
        </div>
      )}
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
        title="Sources appear here"
        description="Ask a question to see the exact passages behind the answer and whether each sentence is supported."
      />
    )
  }
  const v = answer.verification
  const trace = answer.trace
  const cited = answer.evidence.filter((e) => e.validation !== 'uncited')
  const others = answer.evidence.filter((e) => e.validation === 'uncited')
  // Before verification arrives every source is "uncited"; show them all rather than an empty list.
  const primary = cited.length ? cited : answer.evidence
  const secondary = cited.length ? others : []
  const activeInSecondary = secondary.some((e) => e.label === activeLabel)

  return (
    <div className="flex h-full flex-col">
      <div className={cn('flex items-center justify-between border-b border-border px-4 py-3', !showHeader && 'hidden')}>
        <p className="text-sm font-semibold">Sources</p>
        {onClose && (
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close sources panel">
            <X />
          </Button>
        )}
      </div>
      <Tabs defaultValue="sources" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="mx-4 mt-3 self-start">
          <TabsTrigger value="sources">Sources ({answer.evidence.length})</TabsTrigger>
          <TabsTrigger value="claims" disabled={!v}>
            Verification
          </TabsTrigger>
          <TabsTrigger value="trace" disabled={!trace}>
            How it was found
          </TabsTrigger>
        </TabsList>

        <TabsContent value="sources" className="min-h-0 flex-1 overflow-y-auto px-4 py-3 scroll-thin">
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
            <EmptyState className="py-8" title="No passages were found" description="Try rephrasing or searching more documents." />
          ) : (
            <>
              {secondary.length > 0 && (
                <p className="mb-2 text-xs font-medium text-muted-foreground">Used in the answer ({primary.length})</p>
              )}
              <ul className="space-y-3">
                {primary.map((item) => (
                  <EvidenceCard key={item.label} item={item} active={item.label === activeLabel} />
                ))}
              </ul>
              {secondary.length > 0 && (
                <Disclosure
                  key={activeInSecondary ? 'open' : 'closed'}
                  defaultOpen={activeInSecondary}
                  className="mt-4"
                  title={`Also considered (${secondary.length})`}
                  description="Found during search but not needed for the answer."
                >
                  <ul className="space-y-3">
                    {secondary.map((item) => (
                      <EvidenceCard key={item.label} item={item} active={item.label === activeLabel} />
                    ))}
                  </ul>
                </Disclosure>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="claims" className="min-h-0 flex-1 overflow-y-auto px-4 py-3 scroll-thin">
          {v && (
            <>
              <p className="mb-3 text-xs text-muted-foreground">
                Each sentence of the answer was checked against the passage it cites.{' '}
                <InfoTip term="sourceVerification" className="align-middle" />
              </p>
              <dl className="mb-4 grid grid-cols-3 gap-2 text-center">
                {(
                  [
                    ['Valid citations', v.citation_validity, TERMS.citationValidity.description],
                    ['Accurate citations', v.citation_precision, 'Share of valid citations whose passage actually supports the sentence (citation precision).'],
                    ['Supported sentences', v.evidence_coverage, TERMS.evidenceCoverage.description],
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
                {v.claims.map((claim, i) => {
                  const status = CLAIM_STATUS[claim.status]
                  return (
                    <li key={i} className="rounded-lg border border-border p-3 text-[12.5px]">
                      <div className="mb-1 flex items-center gap-2">
                        <Badge tone={status.tone}>{status.label}</Badge>
                        <span className="text-[11px] text-muted-foreground">
                          {claim.citations.length ? claim.citations.join(' ') : 'no citation'}
                        </span>
                      </div>
                      <p className="leading-relaxed">{claim.text}</p>
                      {claim.invalid_citations.length > 0 && (
                        <p className="mt-1 text-danger">Cites a source that doesn&apos;t exist: {claim.invalid_citations.join(', ')}</p>
                      )}
                      {claim.missing_numbers.length > 0 && (
                        <p className="mt-1 text-danger">Figures not found in the cited source: {claim.missing_numbers.join(', ')}</p>
                      )}
                      {claim.page_issues.map((issue) => (
                        <p key={issue} className="mt-1 text-danger">
                          {issue}
                        </p>
                      ))}
                    </li>
                  )
                })}
              </ul>
              <p className="mt-3 text-[11px] text-muted-foreground">
                Checked independently after the answer was written (scorer: {v.scorer}). These are verification signals,
                not model confidence.
              </p>
            </>
          )}
        </TabsContent>

        <TabsContent value="trace" className="min-h-0 flex-1 overflow-y-auto px-4 py-3 text-[12.5px] scroll-thin">
          {trace && (
            <div className="space-y-4">
              <section>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Searched for</p>
                <ul className="space-y-1">
                  {trace.queries.map((q, i) => (
                    <li key={i} className="rounded-md bg-surface-2 px-2 py-1 text-[12px]">
                      {q}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Steps taken</p>
                {trace.decisions.length ? (
                  <ul className="list-disc space-y-1 pl-4">
                    {trace.decisions.map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground">The standard search was enough; no extra steps were needed.</p>
                )}
              </section>
              <section>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Time per step</p>
                <table className="w-full">
                  <tbody>
                    {Object.entries(trace.timings_ms).map(([stage, ms]) => (
                      <tr key={stage} className="border-b border-border last:border-0">
                        <td className="py-1 text-muted-foreground">{stageName(stage)}</td>
                        <td className="py-1 text-right tabular-nums">{formatMs(ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <Disclosure title="Technical details">
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
              </Disclosure>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
