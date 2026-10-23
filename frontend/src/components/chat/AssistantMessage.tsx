import { motion } from 'framer-motion'
import { AlertCircle, Ban, Check, Copy, PanelRightOpen, RotateCcw, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useState } from 'react'

import { LogoMark } from '@/components/brand/Logo'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/overlays'
import { Badge } from '@/components/ui/primitives'
import { formatMs, formatPercent } from '@/utils/format'

import { AnswerMarkdown, type CitationTone } from './AnswerMarkdown'
import type { AnswerView } from './model'

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

  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
      <LogoMark className="mt-0.5 size-7 shrink-0" />
      <div className="min-w-0 flex-1">
        {answer.status === 'abstained' && (
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-md bg-warning-soft px-2 py-1 text-xs font-medium text-warning">
            <Ban className="size-3.5" /> Not enough evidence — answer withheld
          </div>
        )}
        {answer.status === 'error' && (
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-md bg-danger-soft px-2 py-1 text-xs font-medium text-danger">
            <AlertCircle className="size-3.5" /> {answer.error ?? 'The answer could not be generated'}
          </div>
        )}

        {answer.content ? (
          <AnswerMarkdown content={answer.content} onCite={onCite} activeLabel={activeLabel} toneFor={toneFor} />
        ) : answer.status === 'streaming' ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="inline-flex gap-1">
              <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.2s]" />
              <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.1s]" />
              <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground" />
            </span>
            {answer.trace ? `Generating from ${answer.evidence.length} passages…` : 'Retrieving evidence…'}
          </p>
        ) : null}
        {answer.status === 'streaming' && answer.content && (
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-primary align-middle" aria-hidden />
        )}

        {answer.status !== 'streaming' && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {v && (
              <>
                {v.low_support ? (
                  <Tooltip content="Less than half of the factual sentences are supported by a cited passage. Check the claims tab.">
                    <span>
                      <Badge tone="warning">
                        <TriangleAlert className="size-3" /> Low evidence coverage
                      </Badge>
                    </span>
                  </Tooltip>
                ) : (
                  <Badge tone="success">
                    <ShieldCheck className="size-3" /> Verified against sources
                  </Badge>
                )}
                <Tooltip content="Citations that refer to a provided source">
                  <span>
                    <Badge tone="outline">citations valid {formatPercent(v.citation_validity, 0)}</Badge>
                  </span>
                </Tooltip>
                <Tooltip content="Factual sentences supported by a cited passage">
                  <span>
                    <Badge tone="outline">coverage {formatPercent(v.evidence_coverage, 0)}</Badge>
                  </span>
                </Tooltip>
                {v.unsupported_claims.length > 0 && (
                  <Badge tone="danger">{v.unsupported_claims.length} unsupported</Badge>
                )}
              </>
            )}
            <span className="text-[11px] text-muted-foreground">
              {answer.provider === 'extractive' ? 'Extractive mode' : answer.model}
              {answer.totalMs !== null && ` · ${formatMs(answer.totalMs)}`}
            </span>
            <div className="ml-auto flex items-center gap-0.5">
              {onShowEvidence && (
                <Button variant="ghost" size="icon-sm" onClick={onShowEvidence} aria-label="Show evidence" className="xl:hidden">
                  <PanelRightOpen />
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
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-navy px-4 py-2.5 text-[14.5px] text-white dark:bg-primary-soft dark:text-foreground">
        {content}
      </div>
    </div>
  )
}
