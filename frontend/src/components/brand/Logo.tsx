import { cn } from '@/utils/cn'

/** Retrieva mark: a document stack with a retrieval cursor. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn('size-7', className)} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#5146E5" />
      <path d="M10 9.5h9.5a4 4 0 0 1 0 8H10z" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinejoin="round" />
      <path d="M10 9.5v13" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M16 17.5l5.5 5.5" stroke="#B4AEFF" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  )
}

export function Logo({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <LogoMark />
      {!compact && <span className="text-[15px] font-semibold tracking-tight text-foreground">Retrieva</span>}
    </span>
  )
}
