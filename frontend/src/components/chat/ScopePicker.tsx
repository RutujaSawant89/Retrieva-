import { useQuery } from '@tanstack/react-query'
import { Check, FolderOpen, Globe2, Search } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/overlays'
import { EmptyState, Input, Skeleton } from '@/components/ui/primitives'
import { useDebouncedValue } from '@/hooks/useDebounce'
import { collectionsApi } from '@/services/collections'
import { documentsApi } from '@/services/documents'
import type { RetrievalScopeInput } from '@/types/api'
import { cn } from '@/utils/cn'
import { scopeSummary } from '@/utils/scope'

export function ScopePicker({
  value,
  onChange,
  disabled,
}: {
  value: RetrievalScopeInput
  onChange: (scope: RetrievalScopeInput) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(value)
  const [search, setSearch] = useState('')
  const q = useDebouncedValue(search)

  const documents = useQuery({
    queryKey: ['documents', 'scope-picker', q],
    queryFn: () => documentsApi.list({ q: q || undefined, status: ['completed'], page_size: 50 }),
    enabled: open,
  })
  const collections = useQuery({
    queryKey: ['collections', 'scope-picker', q],
    queryFn: () => collectionsApi.list({ q: q || undefined, page_size: 50 }),
    enabled: open,
  })

  const toggle = (key: keyof RetrievalScopeInput, id: string) =>
    setDraft((cur) => ({
      ...cur,
      [key]: cur[key].includes(id) ? cur[key].filter((x) => x !== id) : [...cur[key], id],
    }))

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        disabled={disabled}
        onClick={() => {
          setDraft(value)
          setOpen(true)
        }}
        title={disabled ? 'The scope is fixed once a conversation starts' : 'Choose which documents to search'}
      >
        {value.document_ids.length || value.collection_ids.length ? <FolderOpen /> : <Globe2 />}
        {scopeSummary(value)}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title="Search scope"
          description="Limit this conversation to specific documents or collections. Leave empty to use every document you can access."
          className="max-w-lg"
        >
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input className="pl-8" placeholder="Filter" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Filter scope" />
          </div>
          <Tabs defaultValue="documents">
            <TabsList>
              <TabsTrigger value="documents">Documents ({draft.document_ids.length})</TabsTrigger>
              <TabsTrigger value="collections">Collections ({draft.collection_ids.length})</TabsTrigger>
            </TabsList>
            <TabsContent value="documents" className="mt-3">
              <PickList
                loading={documents.isLoading}
                items={(documents.data?.items ?? []).map((d) => ({ id: d.id, label: d.title, hint: d.original_filename }))}
                selected={draft.document_ids}
                onToggle={(id) => toggle('document_ids', id)}
                empty="No indexed documents"
              />
            </TabsContent>
            <TabsContent value="collections" className="mt-3">
              <PickList
                loading={collections.isLoading}
                items={(collections.data?.items ?? []).map((c) => ({
                  id: c.id,
                  label: c.name,
                  hint: `${c.document_count} documents`,
                }))}
                selected={draft.collection_ids}
                onToggle={(id) => toggle('collection_ids', id)}
                empty="No collections"
              />
            </TabsContent>
          </Tabs>
          <div className="mt-4 flex justify-between gap-2">
            <Button variant="ghost" onClick={() => setDraft({ document_ids: [], collection_ids: [] })}>
              Clear (all documents)
            </Button>
            <Button
              onClick={() => {
                onChange(draft)
                setOpen(false)
              }}
            >
              Apply scope
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function PickList({
  loading,
  items,
  selected,
  onToggle,
  empty,
}: {
  loading: boolean
  items: { id: string; label: string; hint?: string }[]
  selected: string[]
  onToggle: (id: string) => void
  empty: string
}) {
  if (loading) return <Skeleton className="h-40" />
  if (!items.length) return <EmptyState className="py-8" title={empty} />
  return (
    <ul className="max-h-72 space-y-1 overflow-y-auto" role="listbox" aria-multiselectable>
      {items.map((item) => {
        const active = selected.includes(item.id)
        return (
          <li key={item.id}>
            <button
              type="button"
              role="option"
              aria-selected={active}
              onClick={() => onToggle(item.id)}
              className={cn(
                'flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-left text-[13px]',
                active ? 'bg-primary-soft' : 'hover:bg-surface-2',
              )}
            >
              <span
                className={cn(
                  'flex size-4 items-center justify-center rounded border',
                  active ? 'border-primary bg-primary text-primary-foreground' : 'border-border-strong',
                )}
              >
                {active && <Check className="size-3" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{item.label}</span>
                {item.hint && <span className="block truncate text-xs text-muted-foreground">{item.hint}</span>}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
