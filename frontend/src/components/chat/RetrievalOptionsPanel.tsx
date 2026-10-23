import { RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/overlays'
import { Input, Label, Switch } from '@/components/ui/primitives'
import { DEFAULT_OPTIONS } from '@/services/chat'
import type { RetrievalOptions } from '@/types/api'

type Tri = boolean | 'auto'

const TRI_OPTIONS = [
  { value: 'auto', label: 'Auto' },
  { value: 'on', label: 'Always' },
  { value: 'off', label: 'Off' },
]

const toTri = (value: string): Tri => (value === 'auto' ? 'auto' : value === 'on')
const fromTri = (value: Tri) => (value === 'auto' ? 'auto' : value ? 'on' : 'off')

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
    <div className="space-y-4 text-[13px]">
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2 space-y-1.5">
          <Label htmlFor="opt-strategy">Retrieval strategy</Label>
          <Select
            id="opt-strategy"
            value={value.strategy}
            onValueChange={(v) => set('strategy', v as RetrievalOptions['strategy'])}
            options={[
              { value: 'hybrid', label: 'Hybrid — dense + BM25 with RRF' },
              { value: 'dense', label: 'Dense — semantic embeddings' },
              { value: 'sparse', label: 'Sparse — BM25 keywords' },
            ]}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="opt-topk">Top-K evidence</Label>
          <Input
            id="opt-topk"
            type="number"
            min={1}
            max={30}
            value={value.top_k}
            onChange={(e) => set('top_k', Math.min(30, Math.max(1, Number(e.target.value) || 1)))}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="opt-cand">Candidates</Label>
          <Input
            id="opt-cand"
            type="number"
            min={5}
            max={200}
            value={value.candidate_k}
            onChange={(e) => set('candidate_k', Math.min(200, Math.max(5, Number(e.target.value) || 5)))}
          />
        </div>
        {hybrid && !compact && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="opt-dw">Dense weight</Label>
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
              <Label htmlFor="opt-sw">BM25 weight</Label>
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
            <div className="space-y-1.5">
              <Label htmlFor="opt-rrfk">RRF k</Label>
              <Input
                id="opt-rrfk"
                type="number"
                min={1}
                max={1000}
                value={value.rrf_k}
                onChange={(e) => set('rrf_k', Math.max(1, Number(e.target.value) || 60))}
              />
            </div>
          </>
        )}
      </div>

      <div className="space-y-2.5">
        {(
          [
            ['rerank', 'Cross-encoder reranking'],
            ['dedupe', 'Remove near-duplicates'],
            ['metadata_boost', 'Boost documents named in the query'],
            ['compression', 'Contextual compression'],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex cursor-pointer items-center justify-between gap-3">
            <span>{label}</span>
            <Switch checked={value[key]} onCheckedChange={(checked) => set(key, checked)} aria-label={label} />
          </label>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-2">
        {(
          [
            ['rewrite', 'Query rewrite'],
            ['multi_query', 'Multi-query'],
            ['expansion', 'BM25 expansion'],
          ] as const
        ).map(([key, label]) => (
          <div key={key} className="space-y-1.5">
            <Label htmlFor={`opt-${key}`} className="text-xs">
              {label}
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

      <Button variant="ghost" size="sm" onClick={() => onChange(DEFAULT_OPTIONS)}>
        <RotateCcw /> Reset to defaults
      </Button>
    </div>
  )
}
