import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Logo } from '@/components/brand/Logo'

export function AuthLayout({ title, subtitle, children, footer }: {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <div className="flex min-h-full flex-col bg-background">
      <header className="px-6 py-5">
        <Link to="/" aria-label="Retrieva home">
          <Logo />
        </Link>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pb-16 pt-6 sm:pt-12">
        <div className="w-full max-w-[400px]">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">{subtitle}</p>
          <div className="mt-7 rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow-card)]">{children}</div>
          <p className="mt-5 text-center text-sm text-muted-foreground">{footer}</p>
        </div>
      </main>
    </div>
  )
}
