import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, FolderKanban, FolderPlus, Lock, MessageSquareText, Pencil, Plus, Trash2, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { FileTypeIcon, StatusBadge } from '@/components/documents/DocumentBits'
import { UploadDialog } from '@/components/documents/UploadDialog'
import { Button } from '@/components/ui/button'
import { ConfirmDialog, Dialog, DialogContent, Select } from '@/components/ui/overlays'
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
  Textarea,
} from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { useDebouncedValue } from '@/hooks/useDebounce'
import { collectionsApi } from '@/services/collections'
import { documentsApi } from '@/services/documents'
import type { CollectionOut, Visibility } from '@/types/api'
import { formatRelative } from '@/utils/format'

export function CollectionsPage() {
  const { collectionId } = useParams()
  return collectionId ? <CollectionDetail id={collectionId} /> : <CollectionList />
}

function CollectionForm({
  initial,
  open,
  onOpenChange,
}: {
  initial?: CollectionOut
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [visibility, setVisibility] = useState<Visibility>(initial?.visibility ?? 'organization')
  const save = useMutation({
    mutationFn: () =>
      initial
        ? collectionsApi.update(initial.id, { name: name.trim(), description: description.trim(), visibility })
        : collectionsApi.create({ name: name.trim(), description: description.trim(), visibility }),
    onSuccess: (collection) => {
      toast.success(initial ? 'Collection updated' : 'Collection created')
      void queryClient.invalidateQueries({ queryKey: ['collections'] })
      onOpenChange(false)
      if (!initial) navigate(`/app/collections/${collection.id}`)
    },
    onError: (error) => toast.error(error.message),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={initial ? 'Edit collection' : 'New collection'} description="Group related documents to search and chat over them together.">
        <form
          className="space-y-4"
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <Field label="Name" htmlFor="collection_name">
            <Input id="collection_name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} placeholder="e.g. Compliance Documents" />
          </Field>
          <Field label="Description" htmlFor="collection_description" hint="Optional">
            <Textarea id="collection_description" rows={3} value={description} maxLength={2000} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <Field label="Visibility" htmlFor="collection_visibility">
            <Select
              id="collection_visibility"
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
            <Button type="submit" loading={save.isPending} disabled={!name.trim()}>
              {initial ? 'Save' : 'Create'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function CollectionList() {
  const { can } = useAuth()
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState('')
  const q = useDebouncedValue(search)
  const collections = useQuery({ queryKey: ['collections', 'list', q], queryFn: () => collectionsApi.list({ q: q || undefined }) })

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 lg:px-8">
      <PageHeader
        title="Collections"
        description="Organize documents — financial reports, policies, research — and query them as a unit."
        actions={
          can('collections:write') && (
            <Button onClick={() => setCreating(true)}>
              <FolderPlus /> New collection
            </Button>
          )
        }
      />
      <Input className="mb-4 max-w-sm" placeholder="Search collections" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search collections" />
      {collections.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : collections.isError ? (
        <ErrorState error={collections.error} onRetry={() => collections.refetch()} />
      ) : !collections.data?.items.length ? (
        <Card>
          <EmptyState
            icon={<FolderKanban className="size-5" />}
            title={q ? 'No collections match' : 'No collections yet'}
            description="Create a collection, then add documents to it from here or while uploading."
            action={can('collections:write') && !q && <Button onClick={() => setCreating(true)}>Create a collection</Button>}
          />
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {collections.data.items.map((c) => (
            <Link key={c.id} to={`/app/collections/${c.id}`} className="group">
              <Card className="h-full p-5 transition-colors group-hover:border-primary/50">
                <div className="flex items-start justify-between gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-primary-soft text-primary">
                    <FolderKanban className="size-4" />
                  </span>
                  {c.visibility === 'private' && (
                    <Badge tone="warning">
                      <Lock className="size-3" /> Private
                    </Badge>
                  )}
                </div>
                <p className="mt-3 font-medium">{c.name}</p>
                {c.description && <p className="mt-1 line-clamp-2 text-[13px] text-muted-foreground">{c.description}</p>}
                <p className="mt-3 text-xs text-muted-foreground">
                  {c.document_count} document{c.document_count === 1 ? '' : 's'} · updated {formatRelative(c.updated_at)}
                </p>
              </Card>
            </Link>
          ))}
        </div>
      )}
      {creating && <CollectionForm open={creating} onOpenChange={setCreating} />}
    </div>
  )
}

function CollectionDetail({ id }: { id: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { can } = useAuth()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [adding, setAdding] = useState(false)
  const [uploading, setUploading] = useState(false)

  const collection = useQuery({ queryKey: ['collections', id], queryFn: () => collectionsApi.get(id) })
  const documents = useQuery({
    queryKey: ['documents', { collection_id: id }],
    queryFn: () => documentsApi.list({ collection_id: id, page_size: 100 }),
  })
  const remove = useMutation({
    mutationFn: (docId: string) => collectionsApi.removeDocuments(id, [docId]),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['collections'] })
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
    onError: (error) => toast.error(error.message),
  })

  if (collection.isLoading) return <Skeleton className="m-8 h-64" />
  if (collection.isError || !collection.data)
    return <ErrorState className="py-24" title="Collection unavailable" error={collection.error} />
  const c = collection.data

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 lg:px-8">
      <Link to="/app/collections" className="mb-4 inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Collections
      </Link>
      <PageHeader
        title={c.name}
        description={c.description || `${c.document_count} documents`}
        actions={
          <>
            <Button variant="secondary" disabled={c.document_count === 0} onClick={() => navigate(`/app/chat?collection=${c.id}`)}>
              <MessageSquareText /> Chat with collection
            </Button>
            {c.can_modify && (
              <>
                <Button variant="secondary" onClick={() => setEditing(true)} aria-label="Edit collection">
                  <Pencil />
                </Button>
                <Button variant="ghost" className="text-danger" onClick={() => setDeleting(true)} aria-label="Delete collection">
                  <Trash2 />
                </Button>
              </>
            )}
          </>
        }
      />
      <Card>
        <CardHeader
          title="Documents"
          action={
            c.can_modify && (
              <div className="flex gap-2">
                {can('documents:write') && (
                  <Button size="sm" variant="secondary" onClick={() => setUploading(true)}>
                    Upload into collection
                  </Button>
                )}
                <Button size="sm" onClick={() => setAdding(true)}>
                  <Plus /> Add existing
                </Button>
              </div>
            )
          }
        />
        {documents.isLoading ? (
          <Skeleton className="m-4 h-24" />
        ) : !documents.data?.items.length ? (
          <EmptyState title="This collection is empty" description="Add documents you've already uploaded, or upload new ones into it." />
        ) : (
          <ul className="divide-y divide-border">
            {documents.data.items.map((doc) => (
              <li key={doc.id} className="flex items-center gap-3 px-5 py-3">
                <FileTypeIcon type={doc.file_type} />
                <Link to={`/app/documents/${doc.id}`} className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium hover:text-primary">{doc.title}</p>
                  <p className="truncate text-xs text-muted-foreground">{doc.original_filename}</p>
                </Link>
                <StatusBadge status={doc.status} progress={doc.progress} />
                {c.can_modify && (
                  <Button variant="ghost" size="icon-sm" aria-label={`Remove ${doc.title} from collection`} onClick={() => remove.mutate(doc.id)}>
                    <X />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {editing && <CollectionForm initial={c} open={editing} onOpenChange={setEditing} />}
      {adding && <AddDocumentsDialog collection={c} existing={documents.data?.items.map((d) => d.id) ?? []} onClose={() => setAdding(false)} />}
      <UploadDialog open={uploading} onOpenChange={setUploading} defaultCollectionId={c.id} />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete "${c.name}"?`}
        description="The collection is removed. Its documents stay in your library."
        confirmLabel="Delete collection"
        destructive
        onConfirm={async () => {
          try {
            await collectionsApi.remove(c.id)
            toast.success('Collection deleted')
            await queryClient.invalidateQueries({ queryKey: ['collections'] })
            navigate('/app/collections', { replace: true })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Delete failed')
          }
        }}
      />
    </div>
  )
}

function AddDocumentsDialog({ collection, existing, onClose }: { collection: CollectionOut; existing: string[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const q = useDebouncedValue(search)
  const [selected, setSelected] = useState<string[]>([])
  const documents = useQuery({
    queryKey: ['documents', 'add-to-collection', q],
    queryFn: () => documentsApi.list({ q: q || undefined, page_size: 50 }),
  })
  const add = useMutation({
    mutationFn: () => collectionsApi.addDocuments(collection.id, selected),
    onSuccess: () => {
      toast.success(`Added ${selected.length} document${selected.length > 1 ? 's' : ''}`)
      void queryClient.invalidateQueries({ queryKey: ['collections'] })
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      onClose()
    },
    onError: (error) => toast.error(error.message),
  })
  const candidates = (documents.data?.items ?? []).filter((d) => !existing.includes(d.id))
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent title={`Add documents to ${collection.name}`} className="max-w-lg">
        <Input className="mb-3" placeholder="Search documents" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search documents" />
        {documents.isLoading ? (
          <Skeleton className="h-40" />
        ) : candidates.length === 0 ? (
          <EmptyState className="py-8" title="No more documents to add" />
        ) : (
          <ul className="max-h-72 space-y-1 overflow-y-auto">
            {candidates.map((doc) => {
              const checked = selected.includes(doc.id)
              return (
                <li key={doc.id}>
                  <label className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 hover:bg-surface-2">
                    <input
                      type="checkbox"
                      className="size-4 accent-[var(--primary)]"
                      checked={checked}
                      onChange={() => setSelected((cur) => (checked ? cur.filter((x) => x !== doc.id) : [...cur, doc.id]))}
                    />
                    <FileTypeIcon type={doc.file_type} className="size-7" />
                    <span className="min-w-0 flex-1 truncate text-[13px]">{doc.title}</span>
                  </label>
                </li>
              )
            })}
          </ul>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => add.mutate()} loading={add.isPending} disabled={!selected.length}>
            Add {selected.length || ''}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
