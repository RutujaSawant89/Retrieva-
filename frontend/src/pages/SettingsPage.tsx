import { useMutation } from '@tanstack/react-query'
import { Monitor, Moon, Sun } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardHeader, Field, Input, PageHeader } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { useTheme, type ThemePreference } from '@/contexts/ThemeContext'
import { authApi } from '@/services/auth'
import { ApiError } from '@/services/http'
import { cn } from '@/utils/cn'
import { formatDateTime } from '@/utils/format'
import { passwordChecks } from '@/utils/password'

export function SettingsPage() {
  const { session, updateSession, logout } = useAuth()
  const navigate = useNavigate()
  const { preference, setPreference } = useTheme()
  const [fullName, setFullName] = useState(session?.user.full_name ?? '')
  const [passwords, setPasswords] = useState({ current: '', next: '' })
  const [passwordErrors, setPasswordErrors] = useState<Record<string, string>>({})

  const profile = useMutation({
    mutationFn: () => authApi.updateProfile(fullName.trim()),
    onSuccess: (user) => {
      updateSession({ user })
      toast.success('Profile updated')
    },
    onError: (error) => toast.error(error.message),
  })

  const password = useMutation({
    mutationFn: () => authApi.changePassword(passwords.current, passwords.next),
    onSuccess: async () => {
      toast.success('Password changed. Please sign in again.')
      await logout()
      navigate('/login', { replace: true })
    },
    onError: (error) => {
      if (error instanceof ApiError) setPasswordErrors(error.fieldErrors)
      toast.error(error.message)
    },
  })

  if (!session) return null
  const checks = passwordChecks(passwords.next, session.user.email)

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 lg:px-8">
      <PageHeader title="Settings" description="Manage your profile, security and appearance." />

      <div className="space-y-6">
        <Card>
          <CardHeader title="Profile" description={`Member since ${formatDateTime(session.user.created_at)}`} />
          <form
            className="space-y-4 p-5"
            onSubmit={(event: FormEvent) => {
              event.preventDefault()
              profile.mutate()
            }}
          >
            <Field label="Full name" htmlFor="full_name">
              <Input id="full_name" value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={200} />
            </Field>
            <Field label="Email" htmlFor="email" hint="Email changes are not supported yet.">
              <Input id="email" value={session.user.email} disabled />
            </Field>
            <div className="flex justify-end">
              <Button
                type="submit"
                loading={profile.isPending}
                disabled={!fullName.trim() || fullName.trim() === session.user.full_name}
              >
                Save profile
              </Button>
            </div>
          </form>
        </Card>

        <Card>
          <CardHeader title="Password" description="Changing your password signs out all other sessions." />
          <form
            className="space-y-4 p-5"
            onSubmit={(event: FormEvent) => {
              event.preventDefault()
              setPasswordErrors({})
              password.mutate()
            }}
          >
            <Field label="Current password" htmlFor="current_password" error={passwordErrors.current_password}>
              <Input
                id="current_password"
                type="password"
                autoComplete="current-password"
                value={passwords.current}
                onChange={(e) => setPasswords((p) => ({ ...p, current: e.target.value }))}
              />
            </Field>
            <Field label="New password" htmlFor="new_password" error={passwordErrors.new_password}>
              <Input
                id="new_password"
                type="password"
                autoComplete="new-password"
                value={passwords.next}
                onChange={(e) => setPasswords((p) => ({ ...p, next: e.target.value }))}
              />
            </Field>
            <ul className="space-y-1 text-xs">
              {checks.map((check) => (
                <li key={check.label} className={check.ok ? 'text-success' : 'text-muted-foreground'}>
                  {check.ok ? '✓' : '○'} {check.label}
                </li>
              ))}
            </ul>
            <div className="flex justify-end">
              <Button
                type="submit"
                loading={password.isPending}
                disabled={!passwords.current || !checks.every((c) => c.ok)}
              >
                Change password
              </Button>
            </div>
          </form>
        </Card>

        <Card>
          <CardHeader title="Appearance" description="Choose how Retrieva looks on this device." />
          <div className="grid grid-cols-3 gap-3 p-5" role="radiogroup" aria-label="Theme">
            {(
              [
                { value: 'light', label: 'Light', icon: Sun },
                { value: 'dark', label: 'Dark', icon: Moon },
                { value: 'system', label: 'System', icon: Monitor },
              ] as { value: ThemePreference; label: string; icon: typeof Sun }[]
            ).map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={preference === option.value}
                onClick={() => setPreference(option.value)}
                className={cn(
                  'flex cursor-pointer flex-col items-center gap-2 rounded-lg border px-3 py-4 text-sm transition-colors',
                  preference === option.value
                    ? 'border-primary bg-primary-soft text-primary'
                    : 'border-border hover:bg-surface-2',
                )}
              >
                <option.icon className="size-5" />
                {option.label}
              </button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
