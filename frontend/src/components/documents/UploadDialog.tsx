import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleAlert, Copy, UploadCloud, X } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, Select } from '@/components/ui/overlays'
import { Field, Input, Progress } from '@/components/ui/primitives'
import { collectionsApi } from '@/services/collections'
import { documentsApi } from '@/services/documents'
import { ApiError } from '@/services/http'
import type { UploadResult, Visibility } from '@/types/api'
import { cn } from '@/utils/cn'
import { formatBytes } from '@/utils/format'

import { ACCEPTED_EXTENSIONS, validateFile } from '@/utils/uploads'

import { FileTypeIcon } from './DocumentBits'

interface Pending {
  file: File
  error: string | null
}

export function UploadDialog({
  open,
  onOpenChange,
  defaultCollectionId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultCollectionId?: string
}) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [pending, setPending] = useState<Pending[]>([])
  const [dragging, setDragging] = useState(false)
  const [category, setCategory] = useState('')
  const [visibility, setVisibility] = useState<Visibility>('organization')
  const [collectionId, setCollectionId] = useState(defaultCollectionId ?? 'none')
  const [progress, setProgress] = useState<number | null>(null)
  const [results, setResults] = useState<UploadResult[] | null>(null)
  const controller = useRef<AbortController | null>(null)

  const collections = useQuery({
    queryKey: ['collections', 'all'],
    queryFn: () => collectionsApi.list({ page_size: 100 }),
    enabled: open,
  })

  const addFiles = (files: FileList | File[]) => {
    const next = Array.from(files).map((file) => ({ file, error: validateFile(file) }))
    setPending((current) => {
      const names = new Set(current.map((p) => `${p.file.name}:${p.file.size}`))
      return [...current, ...next.filter((p) => !names.has(`${p.file.name}:${p.file.size}`))].slice(0, 20)
    })
    setResults(null)
  }

  const reset = () => {
    setPending([])
    setResults(null)
    setProgress(null)
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files)
  }

  const valid = pending.filter((p) => !p.error)
  const uploading = progress !== null && results === null

  async function upload() {
    controller.current = new AbortController()
    setProgress(0)
    try {
      const response = await documentsApi.upload(
        valid.map((p) => p.file),
        {
          category: category.trim() || undefined,
          visibility,
          collection_id: collectionId !== 'none' ? collectionId : undefined,
        },
        setProgress,
        controller.current.signal,
      )
      setResults(response.results)
      const created = response.results.filter((r) => r.outcome === 'created').length
      if (created) toast.success(`${created} document${created > 1 ? 's' : ''} uploaded — processing started`)
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      void queryClient.invalidateQueries({ queryKey: ['collections'] })
    } catch (error) {
      setProgress(null)
      toast.error(error instanceof ApiError ? error.message : 'Upload failed')
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (uploading) return
        if (!next) reset()
        onOpenChange(next)
      }}
    >
      <DialogContent
        title="Upload documents"
        description="PDF, DOCX, TXT, Markdown, CSV and HTML up to 50 MB each. Files are processed in the background."
        className="max-w-xl"
      >
        {results ? (
          <div className="space-y-3">
            <ul className="max-h-72 space-y-2 overflow-y-auto">
              {results.map((result) => (
                <li key={result.filename} className="flex items-start gap-3 rounded-lg border border-border p-3 text-sm">
                  {result.outcome === 'created' ? (
                    <CheckCircle2 className="mt-0.5 size-4 text-success" />
                  ) : result.outcome === 'duplicate' ? (
                    <Copy className="mt-0.5 size-4 text-warning" />
                  ) : (
                    <CircleAlert className="mt-0.5 size-4 text-danger" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{result.filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {result.outcome === 'created' && 'Uploaded — processing'}
                      {result.outcome === 'duplicate' && (
                        <>
                          Already in your library.{' '}
                          {result.duplicate_of && (
                            <Link
                              className="text-primary hover:underline"
                              to={`/app/documents/${result.duplicate_of}`}
                              onClick={() => onOpenChange(false)}
                            >
                              View existing
                            </Link>
                          )}
                        </>
                      )}
                      {result.outcome === 'rejected' && result.error}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={reset}>
                Upload more
              </Button>
              <Button
                onClick={() => {
                  reset()
                  onOpenChange(false)
                }}
              >
                Done
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              disabled={uploading}
              className={cn(
                'flex w-full cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-6 py-8 text-center transition-colors',
                dragging ? 'border-primary bg-primary-soft' : 'border-border-strong hover:bg-surface-2',
              )}
            >
              <UploadCloud className="size-6 text-muted-foreground" />
              <span className="mt-2 text-sm font-medium">Drop files here or click to browse</span>
              <span className="mt-0.5 text-xs text-muted-foreground">Up to 20 files per upload</span>
            </button>
            <input
              ref={inputRef}
              type="file"
              multiple
              hidden
              accept={ACCEPTED_EXTENSIONS.join(',')}
              data-testid="file-input"
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files)
                e.target.value = ''
              }}
            />

            {pending.length > 0 && (
              <ul className="max-h-48 space-y-1.5 overflow-y-auto">
                {pending.map((p, index) => (
                  <li key={`${p.file.name}-${index}`} className="flex items-center gap-3 rounded-lg border border-border px-3 py-2">
                    <FileTypeIcon type={p.file.name.split('.').pop()?.toLowerCase() ?? ''} className="size-7" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium">{p.file.name}</p>
                      <p className={cn('text-xs', p.error ? 'text-danger' : 'text-muted-foreground')}>
                        {p.error ?? formatBytes(p.file.size)}
                      </p>
                    </div>
                    {!uploading && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${p.file.name}`}
                        onClick={() => setPending((cur) => cur.filter((_, i) => i !== index))}
                      >
                        <X />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}

            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Category" htmlFor="upload_category" hint="Optional">
                <Input
                  id="upload_category"
                  placeholder="e.g. Legal"
                  value={category}
                  maxLength={100}
                  onChange={(e) => setCategory(e.target.value)}
                />
              </Field>
              <Field label="Visibility" htmlFor="upload_visibility">
                <Select
                  id="upload_visibility"
                  value={visibility}
                  onValueChange={(v) => setVisibility(v as Visibility)}
                  options={[
                    { value: 'organization', label: 'Organization' },
                    { value: 'private', label: 'Only me & admins' },
                  ]}
                />
              </Field>
              <Field label="Collection" htmlFor="upload_collection">
                <Select
                  id="upload_collection"
                  value={collectionId}
                  onValueChange={setCollectionId}
                  options={[
                    { value: 'none', label: 'None' },
                    ...(collections.data?.items ?? []).map((c) => ({ value: c.id, label: c.name })),
                  ]}
                />
              </Field>
            </div>

            {progress !== null && (
              <div className="space-y-1">
                <Progress value={progress * 100} />
                <p className="text-xs text-muted-foreground">
                  {progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : 'Validating and queueing…'}
                </p>
              </div>
            )}

            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                {valid.length} file{valid.length === 1 ? '' : 's'} ready
                {pending.length > valid.length && ` · ${pending.length - valid.length} invalid`}
              </p>
              <div className="flex gap-2">
                {uploading ? (
                  <Button variant="secondary" onClick={() => controller.current?.abort()}>
                    Cancel
                  </Button>
                ) : (
                  <Button variant="secondary" onClick={() => onOpenChange(false)}>
                    Close
                  </Button>
                )}
                <Button onClick={upload} loading={uploading} disabled={valid.length === 0}>
                  Upload {valid.length > 0 ? valid.length : ''}
                </Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
