import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, MessageSquareText, Pencil, RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { FileTypeIcon, StatusBadge } from '@/components/documents/DocumentBits'
import { Button } from '@/components/ui/button'
import {
  ConfirmDialog,
  Dialog,
  DialogContent,
  Select,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/overlays'
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Progress,
  Skeleton,
} from '@/components/ui/primitives'
import { Pagination } from '@/components/ui/table'
import { documentsApi, isProcessing } from '@/services/documents'
import { downloadFile } from '@/services/http'
import type { ChunkingStrategy, ContentBlock, DocumentDetail, Visibility } from '@/types/api'
import { cn } from '@/utils/cn'
import { formatBytes, formatDateTime, formatMs, formatNumber } from '@/utils/format'

const STAGES = ['extracting', 'chunking', 'embedding', 'indexing'] as const

export function DocumentDetailPage() {
  const { documentId = '' } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const highlight = useMemo(() => {
    const start = Number(params.get('start'))
    const end = Number(params.get('end'))
    return params.has('start') && end > start ? { start, end } : null
  }, [params])
  const [tab, setTab] = useState(highlight ? 'preview' : 'overview')
  const [editing, setEditing] = useState(false)
  const [reprocessOpen, setReprocessOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const detail = useQuery({
    queryKey: ['documents', documentId],
    queryFn: () => documentsApi.get(documentId),
    refetchInterval: (query) => (query.state.data && isProcessing(query.state.data.status) ? 1500 : false),
  })

  if (detail.isLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-8 lg:px-8">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (detail.isError || !detail.data) {
    return <ErrorState className="py-24" title="Document unavailable" error={detail.error} onRetry={() => detail.refetch()} />
  }
  const doc = detail.data
  const processing = isProcessing(doc.status)

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 lg:px-8">
      <Link to="/app/documents" className="mb-4 inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Documents
      </Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <FileTypeIcon type={doc.file_type} className="size-10" />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold tracking-tight">{doc.title}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-[13px] text-muted-foreground">
              <StatusBadge status={doc.status} progress={doc.progress} />
              <span>{doc.original_filename}</span>·<span>{formatBytes(doc.file_size)}</span>
              {doc.page_count !== null && <>·<span>{doc.page_count} pages</span></>}
              {doc.category && <Badge tone="outline">{doc.category}</Badge>}
              {doc.visibility === 'private' && <Badge tone="warning">Private</Badge>}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={doc.status !== 'completed'}
            onClick={() => navigate(`/app/chat?document=${doc.id}`)}
          >
            <MessageSquareText /> Ask
          </Button>
          <Button
            variant="secondary"
            onClick={() =>
              downloadFile(`/documents/${doc.id}/file`, doc.original_filename).catch((e: Error) => toast.error(e.message))
            }
          >
            <Download /> Download
          </Button>
          {doc.can_modify && (
            <>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
              <Button variant="secondary" disabled={processing} onClick={() => setReprocessOpen(true)}>
                <RotateCcw /> Reprocess
              </Button>
              <Button variant="ghost" className="text-danger" onClick={() => setDeleteOpen(true)} aria-label="Delete document">
                <Trash2 />
              </Button>
            </>
          )}
        </div>
      </div>

      {processing && (
        <Card className="mb-6 p-4">
          <div className="mb-2 flex items-center justify-between text-[13px]">
            <span className="font-medium capitalize">{doc.status}…</span>
            <span className="text-muted-foreground">{doc.progress}%</span>
          </div>
          <Progress value={doc.progress} />
        </Card>
      )}
      {doc.status === 'failed' && (
        <Card className="mb-6 border-danger/40 bg-danger-soft p-4 text-[13px] text-danger" role="alert">
          <p className="font-medium">Processing failed</p>
          <p className="mt-0.5">{doc.error_message}</p>
        </Card>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="preview" disabled={doc.status !== 'completed'}>
            Preview
          </TabsTrigger>
          <TabsTrigger value="chunks" disabled={doc.status !== 'completed'}>
            Chunks
          </TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-5">
          <Overview doc={doc} />
        </TabsContent>
        <TabsContent value="preview" className="mt-5">
          {tab === 'preview' && <Preview documentId={doc.id} highlight={highlight} />}
        </TabsContent>
        <TabsContent value="chunks" className="mt-5">
          {tab === 'chunks' && <Chunks documentId={doc.id} />}
        </TabsContent>
      </Tabs>

      <EditDialog doc={doc} open={editing} onOpenChange={setEditing} />
      <ReprocessDialog doc={doc} open={reprocessOpen} onOpenChange={setReprocessOpen} />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Delete "${doc.title}"?`}
        description="The file, its chunks and embeddings are permanently removed."
        confirmLabel="Delete document"
        destructive
        onConfirm={async () => {
          try {
            await documentsApi.remove(doc.id)
            toast.success('Document deleted')
            await queryClient.invalidateQueries({ queryKey: ['documents'] })
            navigate('/app/documents', { replace: true })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Delete failed')
          }
        }}
      />
    </div>
  )
}

function Stat({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn('mt-0.5 truncate text-sm', mono && 'font-mono text-[12px]')}>{value}</dd>
    </div>
  )
}

function Overview({ doc }: { doc: DocumentDetail }) {
  const job = doc.latest_job
  const timings = job?.stage_timings ?? {}
  const total = STAGES.reduce((sum, s) => sum + (timings[s] ?? 0), 0)
  const metadataEntries = Object.entries(doc.metadata ?? {}).filter(([, v]) => v !== null && v !== '')

  return (
    <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <Card>
        <CardHeader title="Processing pipeline" description={job?.finished_at ? `Finished ${formatDateTime(job.finished_at)}` : 'Not finished yet'} />
        <div className="space-y-3 p-5">
          {STAGES.map((stage) => {
            const ms = timings[stage]
            return (
              <div key={stage} className="flex items-center gap-3 text-[13px]">
                <span className="w-24 capitalize text-muted-foreground">{stage}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: ms && total ? `${Math.max(2, (ms / total) * 100)}%` : '0%' }}
                  />
                </div>
                <span className="w-20 text-right tabular-nums">{ms !== undefined ? formatMs(ms) : '—'}</span>
              </div>
            )
          })}
          {job && (
            <dl className="grid grid-cols-2 gap-4 border-t border-border pt-4 sm:grid-cols-3">
              <Stat label="Strategy" value={String(job.config.strategy ?? doc.chunking_strategy ?? '—')} />
              <Stat label="Chunk size" value={job.config.chunk_size ? `${job.config.chunk_size} chars` : '—'} />
              <Stat label="Overlap" value={job.config.chunk_overlap !== undefined ? `${job.config.chunk_overlap} chars` : '—'} />
              <Stat label="Token cap" value={job.config.max_tokens ? String(job.config.max_tokens) : '—'} />
              <Stat label="Embeddings reused" value={formatNumber(Number(job.config.reused_embeddings ?? 0))} />
              <Stat label="Attempts" value={job.attempts} />
            </dl>
          )}
        </div>
      </Card>
      <Card>
        <CardHeader title="Details" />
        <dl className="grid grid-cols-2 gap-4 p-5">
          <Stat label="Chunks" value={formatNumber(doc.chunk_count)} />
          <Stat label="Pages" value={doc.page_count ?? '—'} />
          <Stat label="Embedding model" value={doc.embedding_model ?? '—'} mono />
          <Stat label="Indexed" value={doc.indexed_at ? formatDateTime(doc.indexed_at) : '—'} />
          <Stat label="Uploaded by" value={doc.owner_name ?? '—'} />
          <Stat label="Uploaded" value={formatDateTime(doc.created_at)} />
          <div className="col-span-2">
            <Stat label="SHA-256" value={doc.content_hash} mono />
          </div>
          {metadataEntries.map(([key, value]) => (
            <Stat key={key} label={key.replace(/_/g, ' ')} value={Array.isArray(value) ? value.join(', ') : String(value)} />
          ))}
        </dl>
      </Card>
    </div>
  )
}

function HighlightedText({ block, highlight }: { block: ContentBlock; highlight: { start: number; end: number } | null }) {
  if (!highlight || highlight.end <= block.start || highlight.start >= block.end) return <>{block.text}</>
  const from = Math.max(0, highlight.start - block.start)
  const to = Math.min(block.text.length, highlight.end - block.start)
  return (
    <>
      {block.text.slice(0, from)}
      <mark className="rounded bg-warning-soft px-0.5 text-foreground ring-1 ring-warning/50" data-highlight>
        {block.text.slice(from, to)}
      </mark>
      {block.text.slice(to)}
    </>
  )
}

function Preview({ documentId, highlight }: { documentId: string; highlight: { start: number; end: number } | null }) {
  const content = useQuery({ queryKey: ['documents', documentId, 'content'], queryFn: () => documentsApi.content(documentId) })
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (content.data && highlight) {
      container.current?.querySelector('[data-highlight]')?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [content.data, highlight])

  if (content.isLoading) return <Skeleton className="h-96" />
  if (content.isError) return <ErrorState error={content.error} onRetry={() => content.refetch()} />
  let lastPage: number | null = null
  return (
    <Card>
      <div ref={container} className="max-h-[70vh] space-y-3 overflow-y-auto px-6 py-5 text-[14px] leading-relaxed">
        {content.data?.blocks.map((block, index) => {
          const pageBreak = block.page !== null && block.page !== lastPage
          lastPage = block.page
          return (
            <div key={index}>
              {pageBreak && (
                <div className="my-4 flex items-center gap-3 text-[11px] uppercase tracking-wider text-muted-foreground">
                  <span className="h-px flex-1 bg-border" />
                  Page {block.page}
                  <span className="h-px flex-1 bg-border" />
                </div>
              )}
              {block.kind === 'heading' ? (
                <p className={cn('font-semibold', block.level <= 1 ? 'text-base' : 'text-[15px]')}>
                  <HighlightedText block={block} highlight={highlight} />
                </p>
              ) : block.kind === 'table' || block.kind === 'code' || block.kind === 'row' || block.kind === 'list' ? (
                <pre className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 font-mono text-[12px]">
                  <HighlightedText block={block} highlight={highlight} />
                </pre>
              ) : (
                <p>
                  <HighlightedText block={block} highlight={highlight} />
                </p>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function Chunks({ documentId }: { documentId: string }) {
  const [page, setPage] = useState(1)
  const chunks = useQuery({
    queryKey: ['documents', documentId, 'chunks', page],
    queryFn: () => documentsApi.chunks(documentId, page),
  })
  if (chunks.isLoading) return <Skeleton className="h-96" />
  if (chunks.isError) return <ErrorState error={chunks.error} onRetry={() => chunks.refetch()} />
  if (!chunks.data?.items.length) return <EmptyState title="No chunks" />
  return (
    <Card>
      <ul className="divide-y divide-border">
        {chunks.data.items.map((chunk) => (
          <li key={chunk.id} className="px-5 py-4">
            <div className="mb-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge tone="outline" className="font-mono">
                #{chunk.chunk_index}
              </Badge>
              {chunk.page_number !== null && (
                <span>
                  p. {chunk.page_number}
                  {chunk.page_end && chunk.page_end !== chunk.page_number ? `–${chunk.page_end}` : ''}
                </span>
              )}
              {chunk.heading_path.length > 0 && <span className="truncate">{chunk.heading_path.join(' › ')}</span>}
              <span className="ml-auto tabular-nums">{chunk.token_count} tokens</span>
            </div>
            <p className="whitespace-pre-wrap text-[13px] leading-relaxed">{chunk.content}</p>
          </li>
        ))}
      </ul>
      <Pagination page={page} pageSize={chunks.data.page_size} total={chunks.data.total} onPage={setPage} />
    </Card>
  )
}

function EditDialog({ doc, open, onOpenChange }: { doc: DocumentDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(doc.title)
  const [category, setCategory] = useState(doc.category ?? '')
  const [visibility, setVisibility] = useState<Visibility>(doc.visibility)
  const save = useMutation({
    mutationFn: () => documentsApi.update(doc.id, { title: title.trim(), category: category.trim() || null, visibility }),
    onSuccess: () => {
      toast.success('Document updated')
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      onOpenChange(false)
    },
    onError: (error) => toast.error(error.message),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Edit document">
        <form
          className="space-y-4"
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <Field label="Title" htmlFor="doc_title">
            <Input id="doc_title" value={title} maxLength={500} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Category" htmlFor="doc_category">
            <Input id="doc_category" value={category} maxLength={100} onChange={(e) => setCategory(e.target.value)} />
          </Field>
          <Field label="Visibility" htmlFor="doc_visibility">
            <Select
              id="doc_visibility"
              value={visibility}
              onValueChange={(v) => setVisibility(v as Visibility)}
              options={[
                { value: 'organization', label: 'Everyone in the organization' },
                { value: 'private', label: 'Only me and admins' },
              ]}
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending} disabled={!title.trim()}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ReprocessDialog({
  doc,
  open,
  onOpenChange,
}: {
  doc: DocumentDetail
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const queryClient = useQueryClient()
  const config = doc.latest_job?.config ?? {}
  const [strategy, setStrategy] = useState<ChunkingStrategy>((config.strategy as ChunkingStrategy) ?? 'structure')
  const [size, setSize] = useState(String(config.chunk_size ?? 900))
  const [overlap, setOverlap] = useState(String(config.chunk_overlap ?? 150))
  const run = useMutation({
    mutationFn: () =>
      documentsApi.reprocess(doc.id, { strategy, chunk_size: Number(size), chunk_overlap: Number(overlap) }),
    onSuccess: () => {
      toast.success('Reprocessing started')
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      onOpenChange(false)
    },
    onError: (error) => toast.error(error.message),
  })
  const sizeNum = Number(size)
  const overlapNum = Number(overlap)
  const invalid = !(sizeNum >= 100 && sizeNum <= 8000 && overlapNum >= 0 && overlapNum < sizeNum / 2)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Reprocess document"
        description="Re-chunk and re-index with different settings. Embeddings for unchanged chunks are reused."
      >
        <div className="space-y-4">
          <Field label="Chunking strategy" htmlFor="strategy">
            <Select
              id="strategy"
              value={strategy}
              onValueChange={(v) => setStrategy(v as ChunkingStrategy)}
              options={[
                { value: 'structure', label: 'Structure-aware (sections, tables)' },
                { value: 'recursive', label: 'Recursive character' },
                { value: 'token', label: 'Token windows' },
                { value: 'semantic', label: 'Semantic (embedding breakpoints)' },
              ]}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Chunk size (characters)" htmlFor="chunk_size">
              <Input id="chunk_size" type="number" min={100} max={8000} value={size} onChange={(e) => setSize(e.target.value)} />
            </Field>
            <Field label="Overlap (characters)" htmlFor="chunk_overlap" hint="Less than half the chunk size">
              <Input id="chunk_overlap" type="number" min={0} value={overlap} onChange={(e) => setOverlap(e.target.value)} />
            </Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={() => run.mutate()} loading={run.isPending} disabled={invalid}>
              Reprocess
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
