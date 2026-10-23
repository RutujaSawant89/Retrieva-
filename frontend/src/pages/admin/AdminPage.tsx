import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, MailPlus, Search, Trash2, UserMinus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  ConfirmDialog,
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
  PageHeader,
  Skeleton,
} from '@/components/ui/primitives'
import { Pagination } from '@/components/ui/table'
import { useAuth } from '@/contexts/AuthContext'
import { adminApi } from '@/services/admin'
import type { InvitationOut, MemberOut, RoleName } from '@/types/api'
import { formatDateTime, formatRelative } from '@/utils/format'

const ROLE_OPTIONS: { value: RoleName; label: string }[] = [
  { value: 'admin', label: 'Admin' },
  { value: 'analyst', label: 'Analyst' },
  { value: 'researcher', label: 'Researcher' },
  { value: 'viewer', label: 'Viewer' },
]

export function AdminPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 lg:px-8">
      <PageHeader
        title="Organization"
        description="Members, roles, invitations and the audit trail for your organization."
      />
      <Tabs defaultValue="members">
        <TabsList>
          <TabsTrigger value="members">Members</TabsTrigger>
          <TabsTrigger value="invitations">Invitations</TabsTrigger>
          <TabsTrigger value="audit">Audit log</TabsTrigger>
          <TabsTrigger value="organization">Settings</TabsTrigger>
        </TabsList>
        <TabsContent value="members" className="mt-5">
          <MembersTab />
        </TabsContent>
        <TabsContent value="invitations" className="mt-5">
          <InvitationsTab />
        </TabsContent>
        <TabsContent value="audit" className="mt-5">
          <AuditTab />
        </TabsContent>
        <TabsContent value="organization" className="mt-5">
          <OrganizationTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function MembersTab() {
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [removing, setRemoving] = useState<MemberOut | null>(null)

  const query = useQuery({
    queryKey: ['admin', 'users', page, q],
    queryFn: () => adminApi.users({ page, q }),
    placeholderData: keepPreviousData,
  })

  const setRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: RoleName }) => adminApi.setRole(userId, role),
    onSuccess: () => {
      toast.success('Role updated')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <Card>
      <CardHeader
        title="Members"
        description="Roles take effect immediately on the member's next request."
        action={
          <div className="relative w-56">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input
              placeholder="Search members"
              className="pl-8"
              value={q}
              onChange={(e) => {
                setQ(e.target.value)
                setPage(1)
              }}
              aria-label="Search members"
            />
          </div>
        }
      />
      {query.isLoading ? (
        <div className="space-y-2 p-5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : query.data && query.data.items.length === 0 ? (
        <EmptyState title="No members match your search" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-5 py-2.5 font-medium">Member</th>
                <th className="px-5 py-2.5 font-medium">Role</th>
                <th className="px-5 py-2.5 font-medium">Joined</th>
                <th className="px-5 py-2.5 font-medium">Last sign-in</th>
                <th className="px-5 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {query.data?.items.map((member) => {
                const isSelf = member.user_id === session?.user.id
                return (
                  <tr key={member.user_id}>
                    <td className="px-5 py-3">
                      <p className="font-medium">
                        {member.full_name} {isSelf && <Badge tone="primary">You</Badge>}
                      </p>
                      <p className="text-xs text-muted-foreground">{member.email}</p>
                    </td>
                    <td className="w-44 px-5 py-3">
                      <Select
                        aria-label={`Role for ${member.full_name}`}
                        value={member.role}
                        options={ROLE_OPTIONS}
                        disabled={setRole.isPending}
                        onValueChange={(role) => setRole.mutate({ userId: member.user_id, role: role as RoleName })}
                      />
                    </td>
                    <td className="px-5 py-3 text-muted-foreground">{formatDateTime(member.joined_at)}</td>
                    <td className="px-5 py-3 text-muted-foreground">
                      {member.last_login_at ? formatRelative(member.last_login_at) : 'Never'}
                    </td>
                    <td className="px-5 py-3 text-right">
                      {!isSelf && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Remove ${member.full_name}`}
                          onClick={() => setRemoving(member)}
                        >
                          <UserMinus />
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {query.data && <Pagination page={page} pageSize={query.data.page_size} total={query.data.total} onPage={setPage} />}
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Remove ${removing?.full_name ?? 'member'}?`}
        description="They lose access to this organization immediately. Their documents remain in the organization."
        confirmLabel="Remove member"
        destructive
        onConfirm={async () => {
          if (!removing) return
          try {
            await adminApi.removeMember(removing.user_id)
            toast.success('Member removed')
            await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Could not remove member')
          }
        }}
      />
    </Card>
  )
}

function inviteLink(invitation: InvitationOut): string {
  const params = new URLSearchParams({ invite: invitation.token ?? '', email: invitation.email })
  return `${window.location.origin}/register?${params.toString()}`
}

function InvitationsTab() {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<RoleName>('viewer')
  const [created, setCreated] = useState<InvitationOut | null>(null)

  const query = useQuery({ queryKey: ['admin', 'invitations'], queryFn: adminApi.invitations })
  const invite = useMutation({
    mutationFn: () => adminApi.invite(email, role),
    onSuccess: (invitation) => {
      setCreated(invitation)
      setEmail('')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'invitations'] })
    },
    onError: (error) => toast.error(error.message),
  })
  const revoke = useMutation({
    mutationFn: (id: string) => adminApi.revokeInvitation(id),
    onSuccess: () => {
      toast.success('Invitation revoked')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'invitations'] })
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Invite a member"
          description="Invitations expire after 7 days. Retrieva does not send email; share the link securely."
        />
        <form
          className="flex flex-wrap items-end gap-3 p-5"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            invite.mutate()
          }}
        >
          <div className="min-w-60 flex-1">
            <Field label="Email" htmlFor="invite_email">
              <Input id="invite_email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
          </div>
          <div className="w-44">
            <Field label="Role" htmlFor="invite_role">
              <Select id="invite_role" value={role} options={ROLE_OPTIONS} onValueChange={(v) => setRole(v as RoleName)} />
            </Field>
          </div>
          <Button type="submit" loading={invite.isPending} disabled={!email}>
            <MailPlus /> Create invitation
          </Button>
        </form>
        {created?.token && (
          <div className="mx-5 mb-5 rounded-lg border border-primary/30 bg-primary-soft p-3">
            <p className="text-[13px] font-medium text-foreground">
              Invitation link for {created.email} — shown once
            </p>
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded bg-surface px-2 py-1 font-mono text-xs">
                {inviteLink(created)}
              </code>
              <Button
                size="sm"
                variant="secondary"
                onClick={async () => {
                  await navigator.clipboard.writeText(inviteLink(created))
                  toast.success('Link copied')
                }}
              >
                <Copy /> Copy
              </Button>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Invitations" />
        {query.isLoading ? (
          <div className="p-5">
            <Skeleton className="h-10" />
          </div>
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} />
        ) : !query.data?.length ? (
          <EmptyState title="No invitations yet" description="Invite colleagues to collaborate in this organization." />
        ) : (
          <ul className="divide-y divide-border">
            {query.data.map((inv) => {
              const expired = new Date(inv.expires_at).getTime() < Date.now()
              return (
                <li key={inv.id} className="flex items-center gap-4 px-5 py-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{inv.email}</p>
                    <p className="text-xs capitalize text-muted-foreground">
                      {inv.role} · created {formatRelative(inv.created_at)}
                    </p>
                  </div>
                  {inv.accepted_at ? (
                    <Badge tone="success">Accepted</Badge>
                  ) : expired ? (
                    <Badge tone="warning">Expired</Badge>
                  ) : (
                    <Badge tone="primary">Pending</Badge>
                  )}
                  {!inv.accepted_at && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Revoke invitation for ${inv.email}`}
                      onClick={() => revoke.mutate(inv.id)}
                    >
                      <Trash2 />
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </div>
  )
}

function AuditTab() {
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')
  const query = useQuery({
    queryKey: ['admin', 'audit', page, action],
    queryFn: () => adminApi.auditLogs({ page, action }),
    placeholderData: keepPreviousData,
  })

  return (
    <Card>
      <CardHeader
        title="Audit log"
        description="Security-relevant actions in this organization, newest first."
        action={
          <Input
            className="w-56"
            placeholder="Filter by action prefix, e.g. auth."
            value={action}
            onChange={(e) => {
              setAction(e.target.value)
              setPage(1)
            }}
            aria-label="Filter by action"
          />
        }
      />
      {query.isLoading ? (
        <div className="space-y-2 p-5">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-8" />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : !query.data?.items.length ? (
        <EmptyState title="No audit events" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-5 py-2.5 font-medium">When</th>
                <th className="px-5 py-2.5 font-medium">Action</th>
                <th className="px-5 py-2.5 font-medium">Actor</th>
                <th className="px-5 py-2.5 font-medium">Resource</th>
                <th className="px-5 py-2.5 font-medium">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {query.data.items.map((log) => (
                <tr key={log.id}>
                  <td className="whitespace-nowrap px-5 py-2.5 text-muted-foreground">{formatDateTime(log.created_at)}</td>
                  <td className="px-5 py-2.5">
                    <code className="font-mono text-xs">{log.action}</code>
                  </td>
                  <td className="px-5 py-2.5">{log.user_email ?? '—'}</td>
                  <td className="px-5 py-2.5 text-muted-foreground">
                    {log.resource_type ? `${log.resource_type}` : '—'}
                    {log.resource_id && <span className="ml-1 font-mono text-[11px]">{log.resource_id.slice(0, 8)}</span>}
                  </td>
                  <td className="px-5 py-2.5 font-mono text-xs text-muted-foreground">{log.ip_address ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {query.data && <Pagination page={page} pageSize={query.data.page_size} total={query.data.total} onPage={setPage} />}
    </Card>
  )
}

function OrganizationTab() {
  const { session, updateSession } = useAuth()
  const query = useQuery({ queryKey: ['admin', 'organization'], queryFn: adminApi.organization })
  const [name, setName] = useState<string | null>(null)
  const rename = useMutation({
    mutationFn: (value: string) => adminApi.renameOrganization(value),
    onSuccess: (org) => {
      toast.success('Organization renamed')
      if (session) {
        updateSession({
          organization: { ...session.organization, name: org.name },
          organizations: session.organizations.map((o) => (o.id === org.id ? { ...o, name: org.name } : o)),
        })
      }
    },
    onError: (error) => toast.error(error.message),
  })

  if (query.isLoading) return <Skeleton className="h-40" />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  const value = name ?? query.data?.name ?? ''

  return (
    <Card>
      <CardHeader title="Organization settings" description={`Slug: ${query.data?.slug}`} />
      <form
        className="space-y-4 p-5"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          rename.mutate(value.trim())
        }}
      >
        <Field label="Organization name" htmlFor="org_name">
          <Input id="org_name" value={value} onChange={(e) => setName(e.target.value)} maxLength={200} />
        </Field>
        <div className="flex justify-end">
          <Button type="submit" loading={rename.isPending} disabled={value.trim().length < 2 || value === query.data?.name}>
            Save
          </Button>
        </div>
      </form>
    </Card>
  )
}
