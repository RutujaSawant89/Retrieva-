import { Check, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Disclosure, InfoTip, TermLabel } from '@/components/ui/help'
import { Select } from '@/components/ui/overlays'
import { Input, Label, Switch } from '@/components/ui/primitives'
import { DEFAULT_OPTIONS } from '@/services/chat'
import type { RetrievalOptions } from '@/types/api'
import { cn } from '@/utils/cn'
import { STRATEGY_TERMS } from '@/utils/retrieval'

type Tri = boolean | 'auto'

const TRI_OPTIONS = [
  { value: 'auto', label: 'Automatic' },
  { value: 'on', label: 'Always' },
  { value: 'off', label: 'Off' },
]

const toTri = (value: string): Tri => (value === 'auto' ? 'auto' : value === 'on')
const fromTri = (value: Tri) => (value === 'auto' ? 'auto' : value ? 'on' : 'off')

const STRATEGIES: { value: RetrievalOptions['strategy']; recommended?: boolean }[] = [
  { value: 'hybrid', recommended: true },
  { value: 'dense' },
  { value: 'sparse' },
]

/** Search settings: simple choices up front, every technical knob under "Advanced settings". */
export function RetrievalOptionsPanel({
  value,
  onChange,
  compact,
}: {
  value: RetrievalOptions
  onChange: (next: RetrievalOptions) => void
  compact?: boolean
}) {
  const set = <K extends keyof RetrievalOptions>(key: K, v: RetrievalOptions[K]) => onChange({ ...value, [key]: v })
  const hybrid = value.strategy === 'hybrid'

  return (
    <div className="space-y-5 text-[13px]">
      <fieldset className="space-y-2">
        <legend className="mb-2 text-[13px] font-medium">How should Retrieva search?</legend>
        <div role="radiogroup" className="grid gap-2">
          {STRATEGIES.map(({ value: strategy, recommended }) => {
            const term = STRATEGY_TERMS[strategy]
            const selected = value.strategy === strategy
            return (
              <button
                key={strategy}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => set('strategy', strategy)}
                className={cn(
                  'flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-left transition-colors',
                  selected ? 'border-primary bg-primary-soft/60' : 'border-border hover:bg-surface-2',
                )}
              >
                <span
                  className={cn(
                    'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border',
                    selected ? 'border-primary bg-primary text-primary-foreground' : 'border-border-strong',
                  )}
                  aria-hidden
                >
                  {selected && <Check className="size-3" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 font-medium">
                    {term.label}
                    {recommended && (
                      <span className="rounded bg-primary-soft px-1.5 py-px text-[10px] font-semibold text-primary">
                        Recommended
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">{term.description}</span>
                </span>
              </button>
            )
          })}
        </div>
      </fieldset>

      <label className="flex cursor-pointer items-start justify-between gap-4 rounded-lg border border-border p-3">
        <span>
          <TermLabel term="relevanceOptimization" className="font-medium" />
          <span className="mt-0.5 block text-xs text-muted-foreground">
            Re-reads the best candidates with your question to put the most useful passages first. Slightly slower.
          </span>
        </span>
        <Switch checked={value.rerank} onCheckedChange={(checked) => set('rerank', checked)} aria-label="Relevance Optimization" />
      </label>

      <div className="flex items-center justify-between gap-4">
        <Label htmlFor="opt-topk" className="flex items-center gap-1">
          Sources to use per answer
          <InfoTip>How many passages are given to the answer. More sources cover more ground but answers take longer.</InfoTip>
        </Label>
        <Select
          id="opt-topk"
          className="w-28"
          value={String(value.top_k)}
          onValueChange={(v) => set('top_k', Number(v))}
          options={[4, 6, 8, 12, 16, 20].map((n) => ({ value: String(n), label: `${n}${n === 8 ? ' (default)' : ''}` }))}
        />
      </div>

      {!compact && (
        <Disclosure title="Advanced settings" description="Fine-tune each stage. Useful for comparing techniques.">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="opt-cand" className="flex items-center gap-1">
                  Candidate pool <InfoTip>Passages fetched before Relevance Optimization picks the best ones (candidate_k).</InfoTip>
                </Label>
                <Input
                  id="opt-cand"
                  type="number"
                  min={5}
                  max={200}
                  value={value.candidate_k}
                  onChange={(e) => set('candidate_k', Math.min(200, Math.max(5, Number(e.target.value) || 5)))}
                />
              </div>
              {hybrid && (
                <div className="space-y-1.5">
                  <Label htmlFor="opt-rrfk" className="flex items-center gap-1">
                    Fusion constant <InfoTip term="fusion" />
                  </Label>
                  <Input
                    id="opt-rrfk"
                    type="number"
                    min={1}
                    max={1000}
                    value={value.rrf_k}
                    onChange={(e) => set('rrf_k', Math.max(1, Number(e.target.value) || 60))}
                  />
                </div>
              )}
              {hybrid && (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="opt-dw">Semantic weight</Label>
                    <Input
                      id="opt-dw"
                      type="number"
                      step={0.1}
                      min={0}
                      max={5}
                      value={value.dense_weight}
                      onChange={(e) => set('dense_weight', Number(e.target.value))}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="opt-sw">Keyword weight</Label>
                    <Input
                      id="opt-sw"
                      type="number"
                      step={0.1}
                      min={0}
                      max={5}
                      value={value.sparse_weight}
                      onChange={(e) => set('sparse_weight', Number(e.target.value))}
                    />
                  </div>
                </>
              )}
            </div>

            <div className="space-y-2.5">
              {(
                [
                  ['dedupe', 'Remove near-duplicate passages', 'Skips passages that repeat text already selected.'],
                  ['metadata_boost', 'Prefer documents named in the question', 'Ranks passages higher when your question mentions their document by title.'],
                  ['compression', 'Trim passages to relevant sentences', 'Contextual compression: keeps only the sentences most related to the question.'],
                ] as const
              ).map(([key, label, hint]) => (
                <label key={key} className="flex cursor-pointer items-center justify-between gap-3">
                  <span className="flex items-center gap-1">
                    {label} <InfoTip>{hint}</InfoTip>
                  </span>
                  <Switch checked={value[key]} onCheckedChange={(checked) => set(key, checked)} aria-label={label} />
                </label>
              ))}
            </div>

            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  ['rewrite', 'Clarify follow-ups', 'Rewrites follow-up questions ("and for breach?") into complete questions.'],
                  ['multi_query', 'Ask in several ways', 'Searches with alternative phrasings of complex questions (multi-query).'],
                  ['expansion', 'Expand keywords', 'Adds related terms from top results when keyword matches are weak (pseudo-relevance feedback).'],
                ] as const
              ).map(([key, label, hint]) => (
                <div key={key} className="space-y-1.5">
                  <Label htmlFor={`opt-${key}`} className="flex items-center gap-1 text-xs">
                    {label} <InfoTip>{hint}</InfoTip>
                  </Label>
                  <Select
                    id={`opt-${key}`}
                    value={fromTri(value[key])}
                    onValueChange={(v) => set(key, toTri(v))}
                    options={TRI_OPTIONS}
                  />
                </div>
              ))}
            </div>
          </div>
        </Disclosure>
      )}

      <Button variant="ghost" size="sm" onClick={() => onChange(DEFAULT_OPTIONS)}>
        <RotateCcw /> Reset to recommended
      </Button>
    </div>
  )
}
