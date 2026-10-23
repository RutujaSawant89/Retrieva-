import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownUp, FileUp, Lock, MoreHorizontal, RotateCcw, Search, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { FileTypeIcon, StatusBadge } from '@/components/documents/DocumentBits'
import { UploadDialog } from '@/components/documents/UploadDialog'
import { Button } from '@/components/ui/button'
import {
  ConfirmDialog,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Select,
} from '@/components/ui/overlays'
import { Badge, Card, EmptyState, ErrorState, Input, PageHeader, Skeleton } from '@/components/ui/primitives'
import { Pagination } from '@/components/ui/table'
import { useAuth } from '@/contexts/AuthContext'
import { useDebouncedValue } from '@/hooks/useDebounce'
import { documentsApi, isProcessing, PROCESSING_STATUSES, type DocumentListParams } from '@/services/documents'
import type { DocumentOut, DocumentStatus } from '@/types/api'
import { formatBytes, formatRelative } from '@/utils/format'

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'completed', label: 'Indexed' },
  { value: 'processing', label: 'Processing' },
  { value: 'failed', label: 'Failed' },
]

const TYPE_FILTERS = [
  { value: 'all', label: 'All types' },
  { value: 'pdf', label: 'PDF' },
  { value: 'docx', label: 'Word' },
  { value: 'md', label: 'Markdown' },
  { value: 'txt', label: 'Text' },
  { value: 'csv', label: 'CSV' },
  { value: 'html', label: 'HTML' },
]

const SORTS = [
  { value: 'created_at:desc', label: 'Newest first' },
  { value: 'created_at:asc', label: 'Oldest first' },
  { value: 'title:asc', label: 'Title A–Z' },
  { value: 'file_size:desc', label: 'Largest first' },
]

export function DocumentsPage() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [uploadOpen, setUploadOpen] = useState(params.get('upload') === '1')
  const [search, setSearch] = useState('')
  const [deleting, setDeleting] = useState<DocumentOut | null>(null)
  const q = useDebouncedValue(search)

  const page = Number(params.get('page') ?? 1)
  const status = params.get('status') ?? 'all'
  const fileType = params.get('type') ?? 'all'
  const category = params.get('category') ?? 'all'
  const sort = params.get('sort') ?? 'created_at:desc'

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value === 'all' || !value) next.delete(key)
    else next.set(key, value)
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }

  const listParams: DocumentListParams = useMemo(() => {
    const [field, order] = sort.split(':') as [DocumentListParams['sort'], 'asc' | 'desc']
    return {
      page,
      page_size: 20,
      q: q || undefined,
      status:
        status === 'processing' ? PROCESSING_STATUSES : status === 'all' ? undefined : [status as DocumentStatus],
      file_type: fileType === 'all' ? undefined : fileType,
      category: category === 'all' ? undefined : category,
      sort: field,
      order,
    }
  }, [page, q, status, fileType, category, sort])

  const documents = useQuery({
    queryKey: ['documents', listParams],
    queryFn: () => documentsApi.list(listParams),
    placeholderData: keepPreviousData,
    // Poll while anything on screen is still processing.
    refetchInterval: (query) => (query.state.data?.items.some((d) => isProcessing(d.status)) ? 2000 : false),
  })
  const categories = useQuery({ queryKey: ['documents', 'categories'], queryFn: documentsApi.categories })

  const reprocess = useMutation({
    mutationFn: (id: string) => documentsApi.reprocess(id, {}),
    onSuccess: () => {
      toast.success('Processing restarted')
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
    onError: (error) => toast.error(error.message),
  })

  const canUpload = can('documents:write')
  const filtered = q || status !== 'all' || fileType !== 'all' || category !== 'all'

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 lg:px-8">
      <PageHeader
        title="Documents"
        description="Your organization's knowledge base. Documents are parsed, chunked, embedded and indexed for retrieval."
        actions={
          canUpload && (
            <Button onClick={() => setUploadOpen(true)}>
              <FileUp /> Upload
            </Button>
          )
        }
      />

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input
              placeholder="Search by title or filename"
              className="pl-8"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setParam('page', '')
              }}
              aria-label="Search documents"
            />
          </div>
          <Select className="w-36" aria-label="Status" value={status} onValueChange={(v) => setParam('status', v)} options={STATUS_FILTERS} />
          <Select className="w-32" aria-label="File type" value={fileType} onValueChange={(v) => setParam('type', v)} options={TYPE_FILTERS} />
          <Select
            className="w-40"
            aria-label="Category"
            value={category}
            onValueChange={(v) => setParam('category', v)}
            options={[{ value: 'all', label: 'All categories' }, ...(categories.data ?? []).map((c) => ({ value: c, label: c }))]}
          />
          <div className="flex items-center gap-1">
            <ArrowDownUp className="size-4 text-muted-foreground" aria-hidden />
            <Select className="w-36" aria-label="Sort" value={sort} onValueChange={(v) => setParam('sort', v)} options={SORTS} />
          </div>
        </div>

        {documents.isLoading ? (
          <div className="space-y-2 p-4">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : documents.isError ? (
          <ErrorState error={documents.error} onRetry={() => documents.refetch()} />
        ) : documents.data?.items.length === 0 ? (
          filtered ? (
            <EmptyState title="No documents match these filters" />
          ) : (
            <EmptyState
              icon={<FileUp className="size-5" />}
              title="No documents yet"
              description="Upload PDFs, Word files, Markdown, HTML, CSV or text to build your knowledge base."
              action={canUpload && <Button onClick={() => setUploadOpen(true)}>Upload documents</Button>}
            />
          )
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Document</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="hidden px-4 py-2.5 font-medium md:table-cell">Pages / chunks</th>
                  <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Size</th>
                  <th className="hidden px-4 py-2.5 font-medium md:table-cell">Uploaded</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {documents.data?.items.map((doc) => (
                  <tr
                    key={doc.id}
                    className="cursor-pointer hover:bg-surface-2/60"
                    onClick={() => navigate(`/app/documents/${doc.id}`)}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <FileTypeIcon type={doc.file_type} />
                        <div className="min-w-0">
                          <Link
                            to={`/app/documents/${doc.id}`}
                            className="block max-w-[28rem] truncate font-medium hover:text-primary"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {doc.title}
                          </Link>
                          <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                            {doc.visibility === 'private' && <Lock className="size-3" aria-label="Private" />}
                            {doc.original_filename}
                            {doc.category && <Badge tone="outline">{doc.category}</Badge>}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={doc.status} progress={doc.progress} />
                      {doc.status === 'failed' && doc.error_message && (
                        <p className="mt-1 max-w-56 truncate text-xs text-danger" title={doc.error_message}>
                          {doc.error_message}
                        </p>
                      )}
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">
                      {doc.page_count ?? '—'} / {doc.status === 'completed' ? doc.chunk_count : '—'}
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground lg:table-cell">{formatBytes(doc.file_size)}</td>
                    <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">
                      <span title={doc.owner_name ?? undefined}>{formatRelative(doc.created_at)}</span>
                    </td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${doc.title}`}>
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem onSelect={() => navigate(`/app/chat?document=${doc.id}`)} disabled={doc.status !== 'completed'}>
                            Ask about this document
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={() => reprocess.mutate(doc.id)}
                            disabled={!can('documents:write') || isProcessing(doc.status)}
                          >
                            <RotateCcw /> Reprocess
                          </DropdownMenuItem>
                          <DropdownMenuItem destructive onSelect={() => setDeleting(doc)} disabled={!can('documents:write')}>
                            <Trash2 /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {documents.data && (
          <Pagination
            page={page}
            pageSize={documents.data.page_size}
            total={documents.data.total}
            onPage={(p) => setParam('page', String(p))}
          />
        )}
      </Card>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete "${deleting?.title}"?`}
        description="The file, its chunks and embeddings are permanently removed and it will no longer appear in answers. Past answers keep their quoted passages."
        confirmLabel="Delete document"
        destructive
        onConfirm={async () => {
          if (!deleting) return
          try {
            await documentsApi.remove(deleting.id)
            toast.success('Document deleted')
            await queryClient.invalidateQueries({ queryKey: ['documents'] })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Delete failed')
          }
        }}
      />
    </div>
  )
}
