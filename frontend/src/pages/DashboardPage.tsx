import { ShieldCheck } from 'lucide-react'

import { Badge, Card, CardHeader, PageHeader } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'

export function DashboardPage() {
  const { session } = useAuth()
  if (!session) return null
  const firstName = session.user.full_name.split(' ')[0]

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 lg:px-8">
      <PageHeader
        title={`Welcome, ${firstName}`}
        description={`You are signed in to ${session.organization.name}.`}
      />
      <Card>
        <CardHeader
          title="Your access"
          description="Permissions granted by your role in this organization."
          action={
            <Badge tone="primary" className="capitalize">
              <ShieldCheck className="size-3" /> {session.organization.role}
            </Badge>
          }
        />
        <div className="flex flex-wrap gap-1.5 p-5">
          {session.permissions.map((permission) => (
            <Badge key={permission} tone="outline" className="font-mono">
              {permission}
            </Badge>
          ))}
        </div>
      </Card>
    </div>
  )
}
