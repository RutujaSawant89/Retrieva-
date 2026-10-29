import { motion } from 'framer-motion'
import { AlertCircle, Check, Copy, FileText, PanelRightOpen, RotateCcw, SearchX, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useState } from 'react'

import { LogoMark } from '@/components/brand/Logo'
import { Button } from '@/components/ui/button'
import { InfoTip } from '@/components/ui/help'
import { Tooltip } from '@/components/ui/overlays'
import { cn } from '@/utils/cn'
import { formatMs, formatPercent } from '@/utils/format'

import { AnswerMarkdown, type CitationTone } from './AnswerMarkdown'
import type { AnswerView } from './model'

/** What the assistant is doing right now, in plain words. */
function thinkingLabel(answer: AnswerView): string {
  if (!answer.trace) return 'Searching your documents…'
  return `Reading ${answer.evidence.length} relevant passage${answer.evidence.length === 1 ? '' : 's'}…`
}

export function AssistantMessage({
  answer,
  activeLabel,
  onCite,
  onRegenerate,
  onShowEvidence,
  canRegenerate,
}: {
  answer: AnswerView
  activeLabel: string | null
  onCite: (label: string) => void
  onRegenerate?: () => void
  onShowEvidence?: () => void
  canRegenerate: boolean
}) {
  const [copied, setCopied] = useState(false)
  const v = answer.verification
  const invalid = new Set(v?.invalid_labels ?? [])
  const supporting = new Set(v?.supporting_labels ?? [])
  const toneFor = (label: string): CitationTone => {
    if (invalid.has(label)) return 'invalid'
    if (!v) return 'valid'
    return supporting.has(label) ? 'valid' : 'weak'
  }
  const citedLabels = new Set(v?.cited_labels ?? [])
  const citedSources = answer.evidence.filter((e) => citedLabels.has(e.label))

  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
      <LogoMark className="mt-0.5 size-7 shrink-0" />
      <div className="min-w-0 flex-1">
        {answer.status === 'abstained' && (
          <div className="mb-3 flex gap-2.5 rounded-xl border border-warning/25 bg-warning-soft p-3 text-[13px]">
            <SearchX className="mt-0.5 size-4 shrink-0 text-warning" />
            <div>
              <p className="flex items-center gap-1 font-medium text-warning">
                Evidence insufficient <InfoTip term="evidenceInsufficient" />
              </p>
              <p className="mt-0.5 text-muted-foreground">
                Your documents don&apos;t contain enough relevant information to answer this reliably, so Retrieva
                didn&apos;t guess. Try rephrasing, widening the search to more documents, or uploading a source that
                covers it.
              </p>
            </div>
          </div>
        )}
        {answer.status === 'error' && (
          <div className="mb-3 flex items-center gap-2 rounded-xl border border-danger/25 bg-danger-soft p-3 text-[13px] text-danger">
            <AlertCircle className="size-4 shrink-0" /> {answer.error ?? 'The answer could not be generated. Please try again.'}
          </div>
        )}

        {answer.content ? (
          <AnswerMarkdown content={answer.content} onCite={onCite} activeLabel={activeLabel} toneFor={toneFor} />
        ) : answer.status === 'streaming' ? (
          <p className="flex items-center gap-2.5 text-sm text-muted-foreground" role="status">
            <span className="inline-flex gap-1">
              <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.2s]" />
              <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.1s]" />
              <span className="size-1.5 animate-bounce rounded-full bg-primary" />
            </span>
            {thinkingLabel(answer)}
          </p>
        ) : null}
        {answer.status === 'streaming' && answer.content && (
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-primary align-middle" aria-hidden />
        )}

        {answer.status !== 'streaming' && citedSources.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {citedSources.map((source) => (
              <button
                key={source.label}
                type="button"
                onClick={() => onCite(source.label)}
                className={cn(
                  'inline-flex max-w-[240px] cursor-pointer items-center gap-1.5 rounded-lg border px-2 py-1 text-xs transition-colors',
                  activeLabel === source.label
                    ? 'border-primary bg-primary-soft text-primary'
                    : 'border-border bg-surface hover:border-border-strong hover:bg-surface-2',
                )}
                title={source.title}
              >
                <span className="font-mono text-[10.5px] font-semibold text-primary">{source.label}</span>
                <FileText className="size-3 shrink-0 text-muted-foreground" />
                <span className="truncate">{source.title}</span>
                {source.pageNumber ? <span className="shrink-0 text-muted-foreground">p. {source.pageNumber}</span> : null}
              </button>
            ))}
          </div>
        )}

        {answer.status !== 'streaming' && (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
            {v &&
              (v.low_support ? (
                <Tooltip content="Fewer than half of the factual sentences are backed by the passage they cite. Review the sources before relying on this answer.">
                  <span className="inline-flex cursor-help items-center gap-1 font-medium text-warning">
                    <TriangleAlert className="size-3.5" /> Partly supported by sources
                  </span>
                </Tooltip>
              ) : (
                <Tooltip
                  content={`Source Verification checked every sentence against its citation: ${formatPercent(v.evidence_coverage, 0)} of factual sentences are supported and ${formatPercent(v.citation_validity, 0)} of citations are valid.`}
                >
                  <span className="inline-flex cursor-help items-center gap-1 font-medium text-success">
                    <ShieldCheck className="size-3.5" /> Verified against sources
                  </span>
                </Tooltip>
              ))}
            {v && v.unsupported_claims.length > 0 && (
              <span className="font-medium text-danger">
                {v.unsupported_claims.length} sentence{v.unsupported_claims.length === 1 ? '' : 's'} not supported
              </span>
            )}
            <span className="text-muted-foreground">
              {answer.provider === 'extractive' ? 'Quoted from your documents' : answer.model}
              {answer.totalMs !== null && ` · ${formatMs(answer.totalMs)}`}
            </span>
            <div className="ml-auto flex items-center gap-0.5">
              {onShowEvidence && (
                <Button variant="ghost" size="sm" onClick={onShowEvidence} aria-label="Show sources" className="xl:hidden">
                  <PanelRightOpen /> Sources
                </Button>
              )}
              <Tooltip content={copied ? 'Copied' : 'Copy answer'}>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Copy answer"
                  onClick={async () => {
                    await navigator.clipboard.writeText(answer.content)
                    setCopied(true)
                    setTimeout(() => setCopied(false), 1500)
                  }}
                >
                  {copied ? <Check /> : <Copy />}
                </Button>
              </Tooltip>
              {canRegenerate && onRegenerate && (
                <Tooltip content="Regenerate answer">
                  <Button variant="ghost" size="icon-sm" aria-label="Regenerate answer" onClick={onRegenerate}>
                    <RotateCcw />
                  </Button>
                </Tooltip>
              )}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  )
}

export function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[14.5px] text-primary-foreground">
        {content}
      </div>
    </div>
  )
}
