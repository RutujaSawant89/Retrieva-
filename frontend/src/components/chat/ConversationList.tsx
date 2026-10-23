import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquarePlus, MoreHorizontal, Pencil, Search, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { NavLink, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  ConfirmDialog,
  Dialog,
  DialogContent,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/overlays'
import { Input, Skeleton } from '@/components/ui/primitives'
import { useDebouncedValue } from '@/hooks/useDebounce'
import { chatApi } from '@/services/chat'
import type { ConversationOut } from '@/types/api'
import { cn } from '@/utils/cn'
import { formatRelative } from '@/utils/format'

export function ConversationList({ activeId, onNavigate }: { activeId: string | null; onNavigate?: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const q = useDebouncedValue(search)
  const [renaming, setRenaming] = useState<ConversationOut | null>(null)
  const [deleting, setDeleting] = useState<ConversationOut | null>(null)
  const [title, setTitle] = useState('')

  const conversations = useQuery({
    queryKey: ['conversations', q],
    queryFn: () => chatApi.conversations({ q: q || undefined }),
  })
  const rename = useMutation({
    mutationFn: () => chatApi.renameConversation(renaming!.id, title.trim()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      void queryClient.invalidateQueries({ queryKey: ['conversation', renaming?.id] })
      setRenaming(null)
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 p-3">
        <Button
          className="w-full"
          onClick={() => {
            navigate('/app/chat')
            onNavigate?.()
          }}
        >
          <MessageSquarePlus /> New chat
        </Button>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Search chats"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search conversations"
          />
        </div>
      </div>
      <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-3" aria-label="Conversations">
        {conversations.isLoading ? (
          <div className="space-y-2 px-1">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-9" />
            ))}
          </div>
        ) : conversations.data?.items.length === 0 ? (
          <p className="px-3 py-6 text-center text-xs text-muted-foreground">
            {q ? 'No chats match your search' : 'Your conversations will appear here'}
          </p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.data?.items.map((c) => (
              <li key={c.id} className="group relative">
                <NavLink
                  to={`/app/chat/${c.id}`}
                  onClick={onNavigate}
                  className={cn(
                    'block rounded-lg py-2 pl-3 pr-8 text-[13px]',
                    c.id === activeId ? 'bg-primary-soft text-primary' : 'text-foreground hover:bg-surface-2',
                  )}
                >
                  <span className="block truncate font-medium">{c.title}</span>
                  <span className="block text-[11px] text-muted-foreground">{formatRelative(c.updated_at)}</span>
                </NavLink>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="absolute right-1 top-2 opacity-0 focus:opacity-100 group-hover:opacity-100"
                      aria-label={`Actions for ${c.title}`}
                    >
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuItem
                      onSelect={() => {
                        setTitle(c.title)
                        setRenaming(c)
                      }}
                    >
                      <Pencil /> Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem destructive onSelect={() => setDeleting(c)}>
                      <Trash2 /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </li>
            ))}
          </ul>
        )}
      </nav>

      <Dialog open={renaming !== null} onOpenChange={(open) => !open && setRenaming(null)}>
        <DialogContent title="Rename conversation">
          <form
            className="space-y-4"
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              rename.mutate()
            }}
          >
            <Input value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} aria-label="Conversation title" autoFocus />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={() => setRenaming(null)}>
                Cancel
              </Button>
              <Button type="submit" loading={rename.isPending} disabled={!title.trim()}>
                Save
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this conversation?"
        description="Its messages and citations are permanently deleted."
        confirmLabel="Delete"
        destructive
        onConfirm={async () => {
          if (!deleting) return
          try {
            await chatApi.deleteConversation(deleting.id)
            toast.success('Conversation deleted')
            await queryClient.invalidateQueries({ queryKey: ['conversations'] })
            if (deleting.id === activeId) navigate('/app/chat', { replace: true })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Delete failed')
          }
        }}
      />
    </div>
  )
}
