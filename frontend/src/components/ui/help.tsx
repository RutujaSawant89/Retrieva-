/* Contextual help: term explanations, collapsible advanced sections, and callouts. */
import * as CollapsiblePrimitive from '@radix-ui/react-collapsible'
import { ChevronRight, HelpCircle, Info, Lightbulb } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { cn } from '@/utils/cn'
import { TERMS, type TermKey } from '@/utils/glossary'

import { Tooltip } from './overlays'

/** A small "?" that explains a term in plain language and names the technique behind it. */
export function InfoTip({ term, children, className }: { term?: TermKey; children?: ReactNode; className?: string }) {
  const entry = term ? TERMS[term] : null
  return (
    <Tooltip
      content={
        entry ? (
          <span className="block max-w-xs space-y-1">
            <span className="block">{entry.description}</span>
            <span className="block text-white/60">Technique: {entry.technical}</span>
          </span>
        ) : (
          children
        )
      }
    >
      <button
        type="button"
        className={cn(
          'inline-flex size-4 cursor-help items-center justify-center rounded-full text-muted-foreground/80 hover:text-foreground',
          className,
        )}
        aria-label={entry ? `About ${entry.label}` : 'More information'}
      >
        <HelpCircle className="size-3.5" />
      </button>
    </Tooltip>
  )
}

/** Friendly label with its explanation tooltip. */
export function TermLabel({ term, className }: { term: TermKey; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1', className)}>
      {TERMS[term].label}
      <InfoTip term={term} />
    </span>
  )
}

/** Collapsed-by-default section for advanced options and technical details. */
export function Disclosure({
  title,
  description,
  children,
  defaultOpen = false,
  className,
}: {
  title: string
  description?: string
  children: ReactNode
  defaultOpen?: boolean
  className?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <CollapsiblePrimitive.Root open={open} onOpenChange={setOpen} className={cn('rounded-lg border border-border', className)}>
      <CollapsiblePrimitive.Trigger asChild>
        <button
          type="button"
          className="flex w-full cursor-pointer items-center gap-2 px-3 py-2.5 text-left text-[13px] font-medium hover:bg-surface-2/60"
        >
          <ChevronRight className={cn('size-4 text-muted-foreground transition-transform', open && 'rotate-90')} />
          <span className="flex-1">
            {title}
            {description && <span className="block text-xs font-normal text-muted-foreground">{description}</span>}
          </span>
        </button>
      </CollapsiblePrimitive.Trigger>
      <CollapsiblePrimitive.Content className="border-t border-border px-3 py-3">{children}</CollapsiblePrimitive.Content>
    </CollapsiblePrimitive.Root>
  )
}

/** Inline guidance block. */
export function Callout({
  children,
  tone = 'info',
  title,
  className,
}: {
  children: ReactNode
  tone?: 'info' | 'tip'
  title?: string
  className?: string
}) {
  const Icon = tone === 'tip' ? Lightbulb : Info
  return (
    <div className={cn('flex gap-3 rounded-xl border border-primary/15 bg-primary-soft/60 p-4 text-[13px]', className)}>
      <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
      <div className="space-y-1 text-foreground/90">
        {title && <p className="font-medium text-foreground">{title}</p>}
        {children}
      </div>
    </div>
  )
}
