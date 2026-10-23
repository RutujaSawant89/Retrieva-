import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { Field, Input } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { ApiError } from '@/services/http'

import { AuthLayout } from './AuthLayout'

export function LoginPage() {
  const { login, serverUnreachable } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/app'

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to sign in. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Sign in to Retrieva"
      subtitle="Search smarter. Retrieve precisely. Trust every answer."
      footer={
        <>
          New to Retrieva?{' '}
          <Link to="/register" className="font-medium text-primary hover:underline">
            Create an organization
          </Link>
        </>
      }
    >
      {serverUnreachable && (
        <p className="mb-4 rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning" role="status">
          The Retrieva API is not reachable right now. Retrying automatically…
        </p>
      )}
      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        <Field label="Work email" htmlFor="email">
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Password" htmlFor="password">
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && (
          <p className="rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" loading={submitting} disabled={!email || !password}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  )
}
