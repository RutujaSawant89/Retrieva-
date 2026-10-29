import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, FlaskConical, Play, Trash2, Upload, XCircle } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { ChartCard } from '@/components/charts/Charts'
import { Button } from '@/components/ui/button'
import { Disclosure } from '@/components/ui/help'
import { ConfirmDialog, Dialog, DialogContent, Select, Tooltip } from '@/components/ui/overlays'
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Skeleton,
  Spinner,
  Switch,
} from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { evaluationApi } from '@/services/insights'
import type { EvalDataset, EvalRun } from '@/types/api'
import { cn } from '@/utils/cn'
import { TERMS } from '@/utils/glossary'
import { formatDateTime, formatMs } from '@/utils/format'

const METRICS: { key: string; label: string; hint: string; higherIsBetter?: boolean; ms?: boolean }[] = [
  { key: 'precision@1', label: 'P@1', hint: 'Share of top results that are relevant', higherIsBetter: true },
  { key: 'precision@5', label: 'P@5', hint: 'Relevant results among the top 5', higherIsBetter: true },
  { key: 'recall@5', label: 'Recall@5', hint: 'Labelled passages found in the top 5', higherIsBetter: true },
  { key: 'recall@10', label: 'Recall@10', hint: 'Labelled passages found in the top 10', higherIsBetter: true },
  { key: 'mrr', label: 'MRR', hint: 'Mean reciprocal rank of the first relevant result', higherIsBetter: true },
  { key: 'ndcg@10', label: 'nDCG@10', hint: 'Rank-discounted gain relative to the ideal ranking', higherIsBetter: true },
  { key: 'context_precision', label: 'Context precision', hint: 'Rank-aware precision of the retrieved context', higherIsBetter: true },
  { key: 'context_recall', label: 'Context recall', hint: 'Reference-answer sentences supported by retrieved context', higherIsBetter: true },
  { key: 'faithfulness', label: 'Faithfulness', hint: 'Answer claims supported by retrieved context', higherIsBetter: true },
  { key: 'answer_relevancy', label: 'Answer relevancy', hint: 'Embedding similarity of question and answer (approximation)', higherIsBetter: true },
  { key: 'citation_precision', label: 'Citation precision', hint: 'Valid citations whose passage supports the claim', higherIsBetter: true },
  { key: 'citation_coverage', label: 'Citation coverage', hint: 'Factual sentences supported by a cited passage', higherIsBetter: true },
  { key: 'retrieval_ms', label: 'Latency (mean)', hint: 'Mean retrieval time per question', ms: true },
  { key: 'retrieval_ms_p95', label: 'Latency (p95)', hint: '95th percentile retrieval time', ms: true },
]

function num(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

function RunStatusBadge({ status }: { status: EvalRun['status'] }) {
  if (status === 'completed') return <Badge tone="success">Completed</Badge>
  if (status === 'failed') return <Badge tone="danger">Failed</Badge>
  return (
    <Badge tone="primary">
      <Spinner className="size-3" /> {status === 'running' ? 'Running' : 'Queued'}
    </Badge>
  )
}

export function EvaluationPage() {
  const { can } = useAuth()
  const queryClient = useQueryClient()
  const canRun = can('evaluation:run')
  const [datasetId, setDatasetId] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [runOpen, setRunOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [detailId, setDetailId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<EvalDataset | null>(null)

  const datasets = useQuery({ queryKey: ['evaluation', 'datasets'], queryFn: evaluationApi.datasets })
  const activeDataset = datasets.data?.items.find((d) => d.id === datasetId) ?? datasets.data?.items[0]
  const runs = useQuery({
    queryKey: ['evaluation', 'runs', activeDataset?.id],
    queryFn: () => evaluationApi.runs(activeDataset?.id),
    enabled: !!activeDataset,
    refetchInterval: (q) => (q.state.data?.items.some((r) => r.status === 'pending' || r.status === 'running') ? 2000 : false),
  })

  const completed = useMemo(() => (runs.data?.items ?? []).filter((r) => r.status === 'completed'), [runs.data])
  const latestGroup = completed[0]?.config.group
  const compared = useMemo(() => {
    const chosen = selected.length ? completed.filter((r) => selected.includes(r.id)) : completed.filter((r) => r.config.group === latestGroup)
    return chosen.slice(0, 8)
  }, [completed, selected, latestGroup])

  const chartData = compared.map((r) => ({
    run: r.config.experiment ?? r.name,
    ndcg: num(r.metrics['ndcg@10']),
    mrr: num(r.metrics.mrr),
    recall: num(r.metrics['recall@5']),
    precision: num(r.metrics['precision@1']),
  }))

  return (
    <div className="page-enter mx-auto max-w-7xl px-4 py-8 lg:px-8">
      <PageHeader
        title="Search Quality Evaluation"
        description="Measure how reliably Retrieva finds the right passages for questions with known answers, and compare search settings with real numbers."
        actions={
          canRun && (
            <>
              <Button variant="secondary" onClick={() => setUploadOpen(true)}>
                <Upload /> Upload dataset
              </Button>
              <Button onClick={() => setRunOpen(true)} disabled={!activeDataset}>
                <Play /> Run experiment
              </Button>
            </>
          )
        }
      />

      <Disclosure
        className="mb-6"
        title="How evaluation works"
        description="Three steps: a question set, an experiment, and measured results."
      >
        <ol className="grid gap-3 text-[13px] sm:grid-cols-3">
          <li>
            <p className="font-medium">1. Upload a question set</p>
            <p className="text-muted-foreground">Questions paired with the passages or documents that answer them.</p>
          </li>
          <li>
            <p className="font-medium">2. Run an experiment</p>
            <p className="text-muted-foreground">
              Every question goes through the real search pipeline with each configuration (e.g. {TERMS.keywordSearch.label}{' '}
              vs {TERMS.smartSearch.label}).
            </p>
          </li>
          <li>
            <p className="font-medium">3. Compare the results</p>
            <p className="text-muted-foreground">
              Scores like nDCG@10 and Recall@5 show how high the right passages rank. Hover a metric name for its meaning.
            </p>
          </li>
        </ol>
      </Disclosure>

      {datasets.isLoading ? (
        <Skeleton className="h-64" />
      ) : datasets.isError ? (
        <ErrorState error={datasets.error} onRetry={() => datasets.refetch()} />
      ) : !datasets.data?.items.length ? (
        <Card>
          <EmptyState
            icon={<FlaskConical className="size-5" />}
            title="No evaluation datasets yet"
            description="Upload questions labelled with the passages that answer them (JSON, JSONL or CSV). A ready-made sample for the demo corpus is in evaluation/datasets/ in the repository."
            action={canRun && <Button onClick={() => setUploadOpen(true)}>Upload a dataset</Button>}
          />
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <Card className="h-fit">
            <CardHeader title="Datasets" />
            <ul className="divide-y divide-border">
              {datasets.data.items.map((d) => (
                <li key={d.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => {
                      setDatasetId(d.id)
                      setSelected([])
                    }}
                    className={cn(
                      'w-full cursor-pointer px-4 py-3 text-left',
                      activeDataset?.id === d.id ? 'bg-primary-soft' : 'hover:bg-surface-2',
                    )}
                  >
                    <p className="truncate pr-6 text-[13px] font-medium">{d.name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      v{d.version} · {d.item_count} questions
                    </p>
                  </button>
                  {canRun && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="absolute right-2 top-3 opacity-0 group-hover:opacity-100 focus:opacity-100"
                      aria-label={`Delete ${d.name} v${d.version}`}
                      onClick={() => setDeleting(d)}
                    >
                      <Trash2 />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </Card>

          <div className="min-w-0 space-y-6">
            <ChartCard
              kind="bar"
              title="Search quality by configuration"
              description={
                selected.length
                  ? 'Selected runs'
                  : latestGroup
                    ? `Latest experiment: ${latestGroup}. Select runs below to compare others.`
                    : 'Run an experiment to compare configurations'
              }
              data={chartData}
              loading={runs.isLoading}
              xKey="run"
              xLabel="Configuration"
              series={[
                { key: 'ndcg', label: 'nDCG@10' },
                { key: 'mrr', label: 'MRR' },
                { key: 'recall', label: 'Recall@5' },
                { key: 'precision', label: 'P@1' },
              ]}
              format={(v) => (v === null || v === undefined ? '—' : v.toFixed(3))}
              emptyText="No completed runs for this dataset yet"
              height={260}
            />

            {compared.length > 0 && <ComparisonTable runs={compared} onOpen={setDetailId} />}

            <Card>
              <CardHeader title="Runs" description="Every run stores its dataset version, models and full configuration." />
              {runs.isLoading ? (
                <Skeleton className="m-4 h-32" />
              ) : !runs.data?.items.length ? (
                <EmptyState title="No runs yet" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b border-border text-left text-xs text-muted-foreground">
                      <tr>
                        <th className="w-8 px-4 py-2.5" />
                        <th className="px-4 py-2.5 font-medium">Run</th>
                        <th className="px-4 py-2.5 font-medium">Status</th>
                        <th className="px-4 py-2.5 font-medium">Models</th>
                        <th className="px-4 py-2.5 font-medium">Started</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {runs.data.items.map((r) => (
                        <tr key={r.id}>
                          <td className="px-4 py-2.5">
                            <input
                              type="checkbox"
                              className="size-4 accent-[var(--primary)]"
                              aria-label={`Compare ${r.name}`}
                              disabled={r.status !== 'completed'}
                              checked={selected.includes(r.id)}
                              onChange={() =>
                                setSelected((cur) => (cur.includes(r.id) ? cur.filter((x) => x !== r.id) : [...cur, r.id]))
                              }
                            />
                          </td>
                          <td className="px-4 py-2.5">
                            <button type="button" className="cursor-pointer text-left font-medium hover:text-primary" onClick={() => setDetailId(r.id)}>
                              {r.name}
                            </button>
                            <p className="text-xs text-muted-foreground">
                              {r.config.retrieval?.strategy} · rerank {r.config.retrieval?.rerank ? 'on' : 'off'} · dataset v{r.dataset_version}
                              {r.config.generate ? ' · with generation' : ''}
                            </p>
                            {r.error_message && <p className="text-xs text-danger">{r.error_message}</p>}
                          </td>
                          <td className="px-4 py-2.5">
                            <RunStatusBadge status={r.status} />
                          </td>
                          <td className="px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
                            <div>{r.embedding_model}</div>
                            {r.reranker_model && <div>{r.reranker_model}</div>}
                            {r.llm_model && <div>{r.llm_model}</div>}
                          </td>
                          <td className="px-4 py-2.5 text-xs text-muted-foreground">{formatDateTime(r.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        </div>
      )}

      {uploadOpen && <UploadDatasetDialog onClose={() => setUploadOpen(false)} onCreated={(d) => setDatasetId(d.id)} />}
      {runOpen && activeDataset && <RunDialog dataset={activeDataset} onClose={() => setRunOpen(false)} onStarted={() => setSelected([])} />}
      {detailId && <RunDetailDialog runId={detailId} onClose={() => setDetailId(null)} />}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name} v${deleting?.version}?`}
        description="The dataset version and all of its runs and results are permanently deleted."
        confirmLabel="Delete dataset"
        destructive
        onConfirm={async () => {
          if (!deleting) return
          try {
            await evaluationApi.deleteDataset(deleting.id)
            toast.success('Dataset deleted')
            setDatasetId(null)
            await queryClient.invalidateQueries({ queryKey: ['evaluation'] })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Delete failed')
          }
        }}
      />
    </div>
  )
}

function ComparisonTable({ runs, onOpen }: { runs: EvalRun[]; onOpen: (id: string) => void }) {
  const rows = METRICS.filter((m) => runs.some((r) => num(r.metrics[m.key]) !== null))
  return (
    <Card>
      <CardHeader title="Metric comparison" description="Best value per metric is highlighted. All values are measured, not estimated." />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-medium">Metric</th>
              {runs.map((r) => (
                <th key={r.id} className="px-4 py-2.5 text-right font-medium">
                  <button type="button" className="cursor-pointer hover:text-primary" onClick={() => onOpen(r.id)}>
                    {r.config.experiment ?? r.name}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((metric) => {
              const values = runs.map((r) => num(r.metrics[metric.key]))
              const present = values.filter((v): v is number => v !== null)
              const best = present.length > 1 ? (metric.ms ? Math.min(...present) : Math.max(...present)) : null
              return (
                <tr key={metric.key}>
                  <td className="px-4 py-2">
                    <Tooltip content={metric.hint}>
                      <span className="cursor-help border-b border-dotted border-border-strong">{metric.label}</span>
                    </Tooltip>
                  </td>
                  {values.map((v, i) => (
                    <td
                      key={runs[i].id}
                      className={cn('px-4 py-2 text-right tabular-nums', v !== null && v === best && 'font-semibold text-success')}
                    >
                      {v === null ? '—' : metric.ms ? formatMs(v) : v.toFixed(3)}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function UploadDatasetDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (d: EvalDataset) => void }) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: () => evaluationApi.uploadDataset(file!, name.trim()),
    onSuccess: (dataset) => {
      toast.success(`Dataset "${dataset.name}" v${dataset.version} created with ${dataset.item_count} questions`)
      void queryClient.invalidateQueries({ queryKey: ['evaluation', 'datasets'] })
      onCreated(dataset)
      onClose()
    },
    onError: (error) => toast.error(error.message),
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        title="Upload evaluation dataset"
        description="Each item needs a question and either relevant_passages (snippets from your documents) or relevant_documents (titles). Add reference_answer to measure context recall. Uploading an existing name creates a new version."
      >
        <div className="space-y-4">
          <Field label="Name" htmlFor="dataset_name">
            <Input id="dataset_name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} placeholder="e.g. Contract Q&A" />
          </Field>
          <Field label="File (.json, .jsonl, .csv)" htmlFor="dataset_file">
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => input.current?.click()}>
                Choose file
              </Button>
              <span className="truncate text-[13px] text-muted-foreground">{file?.name ?? 'No file selected'}</span>
            </div>
            <input
              id="dataset_file"
              ref={input}
              type="file"
              hidden
              accept=".json,.jsonl,.csv"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null
                setFile(f)
                if (f && !name) setName(f.name.replace(/\.(jsonl?|csv)$/i, ''))
              }}
            />
          </Field>
          <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 font-mono text-[11px] text-muted-foreground">{`{"items": [{
  "question": "What notice is required to terminate?",
  "relevant_passages": ["terminate ... upon ninety (90) days prior written notice"],
  "reference_answer": "Ninety days' written notice."
}]}`}</pre>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={() => upload.mutate()} loading={upload.isPending} disabled={!file || !name.trim()}>
              Upload
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function RunDialog({ dataset, onClose, onStarted }: { dataset: EvalDataset; onClose: () => void; onStarted: () => void }) {
  const queryClient = useQueryClient()
  const presets = useQuery({ queryKey: ['evaluation', 'presets'], queryFn: evaluationApi.presets })
  const [preset, setPreset] = useState('retrieval_strategies')
  const [name, setName] = useState('')
  const [generate, setGenerate] = useState(false)
  const chosen = presets.data?.[preset]

  const defaultName = chosen?.label.split(':')[0] ?? 'Experiment'
  const run = useMutation({
    mutationFn: () => evaluationApi.run({ dataset_id: dataset.id, name: name.trim() || defaultName, preset, generate }),
    onSuccess: (runs) => {
      toast.success(`Started ${runs.length} run${runs.length > 1 ? 's' : ''}`)
      void queryClient.invalidateQueries({ queryKey: ['evaluation', 'runs'] })
      onStarted()
      onClose()
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent title={`Run experiment on "${dataset.name}" v${dataset.version}`} description="Each configuration runs every question through the real pipeline against your indexed documents.">
        <div className="space-y-4">
          <Field label="Experiment" htmlFor="preset">
            <Select
              id="preset"
              value={preset}
              onValueChange={(v) => {
                setPreset(v)
                setName('')
              }}
              options={Object.entries(presets.data ?? {}).map(([key, p]) => ({ value: key, label: p.label }))}
            />
          </Field>
          {chosen && (
            <ul className="space-y-1 rounded-lg bg-surface-2 p-3 text-xs">
              {chosen.experiments.map((e) => (
                <li key={e.name} className="flex justify-between gap-3">
                  <span className="font-medium">{e.name}</span>
                  <span className="truncate font-mono text-muted-foreground">
                    {Object.entries(e.options)
                      .map(([k, v]) => `${k}=${String(v)}`)
                      .join(' ')}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Field label="Name" htmlFor="experiment_name">
            <Input id="experiment_name" value={name} placeholder={defaultName} maxLength={150} onChange={(e) => setName(e.target.value)} />
          </Field>
          <label className="flex cursor-pointer items-center justify-between gap-3 text-[13px]">
            <span>
              Also generate and verify answers
              <span className="block text-xs text-muted-foreground">
                Adds faithfulness, answer relevancy and citation metrics. Uses the configured LLM — slower.
              </span>
            </span>
            <Switch checked={generate} onCheckedChange={setGenerate} aria-label="Generate answers" />
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={() => run.mutate()} loading={run.isPending} disabled={!chosen}>
              <Play /> Start
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function RunDetailDialog({ runId, onClose }: { runId: string; onClose: () => void }) {
  const detail = useQuery({ queryKey: ['evaluation', 'run', runId], queryFn: () => evaluationApi.runDetail(runId) })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent title={detail.data?.name ?? 'Run details'} className="max-h-[85vh] max-w-3xl overflow-y-auto">
        {detail.isLoading || !detail.data ? (
          <Skeleton className="h-64" />
        ) : (
          <div className="space-y-4">
            <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 font-mono text-[11px]">
              {JSON.stringify({ retrieval: detail.data.config.retrieval, ks: detail.data.config.ks, chunking: detail.data.config.chunking }, null, 2)}
            </pre>
            <ul className="space-y-3">
              {detail.data.results.map((r) => (
                <li key={r.item_index} className="rounded-lg border border-border p-3">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-[13px] font-medium">
                      {r.item_index + 1}. {r.question}
                    </p>
                    <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                      MRR {Number(r.metrics.mrr ?? 0).toFixed(2)} · {formatMs(r.latency_ms)}
                    </span>
                  </div>
                  <ol className="mt-2 space-y-1">
                    {r.retrieved.slice(0, 5).map((hit) => (
                      <li key={hit.rank} className="flex items-start gap-2 text-xs">
                        {hit.relevant ? (
                          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" aria-label="Relevant" />
                        ) : (
                          <XCircle className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-label="Not relevant" />
                        )}
                        <span className="text-muted-foreground">
                          #{hit.rank} {hit.document_title}
                          {hit.page ? ` p. ${hit.page}` : ''} — <span className="text-foreground">{hit.excerpt.slice(0, 160)}…</span>
                        </span>
                      </li>
                    ))}
                  </ol>
                  {r.answer && <p className="mt-2 rounded bg-surface-2 p-2 text-xs">{r.answer}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
