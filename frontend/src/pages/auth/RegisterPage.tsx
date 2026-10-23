import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { Field, Input } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { ApiError } from '@/services/http'
import { cn } from '@/utils/cn'
import { passwordChecks } from '@/utils/password'

import { AuthLayout } from './AuthLayout'

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const invitationToken = params.get('invite') ?? undefined

  const [form, setForm] = useState({ full_name: '', email: params.get('email') ?? '', password: '', organization_name: '' })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const checks = useMemo(() => passwordChecks(form.password, form.email), [form.password, form.email])

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }))

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setFieldErrors({})
    setSubmitting(true)
    try {
      await register({
        email: form.email,
        full_name: form.full_name,
        password: form.password,
        ...(invitationToken ? { invitation_token: invitationToken } : { organization_name: form.organization_name }),
      })
      navigate('/app', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors)
        setError(err.message)
      } else {
        setError('Registration failed. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const ready =
    form.full_name.trim() && form.email && checks.every((c) => c.ok) && (invitationToken || form.organization_name.trim().length >= 2)

  return (
    <AuthLayout
      title={invitationToken ? 'Join your team on Retrieva' : 'Create your organization'}
      subtitle={
        invitationToken
          ? 'You were invited to an organization. Create your account to accept.'
          : 'You will be the administrator of a new, isolated workspace.'
      }
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        <Field label="Full name" htmlFor="full_name" error={fieldErrors.full_name}>
          <Input id="full_name" autoComplete="name" value={form.full_name} onChange={set('full_name')} required />
        </Field>
        <Field label="Work email" htmlFor="email" error={fieldErrors.email}>
          <Input id="email" type="email" autoComplete="email" value={form.email} onChange={set('email')} required />
        </Field>
        {!invitationToken && (
          <Field label="Organization name" htmlFor="organization_name" error={fieldErrors.organization_name}>
            <Input id="organization_name" value={form.organization_name} onChange={set('organization_name')} required />
          </Field>
        )}
        <Field label="Password" htmlFor="password" error={fieldErrors.password}>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={set('password')}
            aria-describedby="password-rules"
            required
          />
        </Field>
        <ul id="password-rules" className="space-y-1 text-xs">
          {checks.map((check) => (
            <li key={check.label} className={cn(check.ok ? 'text-success' : 'text-muted-foreground')}>
              {check.ok ? '✓' : '○'} {check.label}
            </li>
          ))}
        </ul>
        {error && (
          <p className="rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" loading={submitting} disabled={!ready}>
          {invitationToken ? 'Create account and join' : 'Create organization'}
        </Button>
      </form>
    </AuthLayout>
  )
}
