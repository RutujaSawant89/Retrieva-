import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { linkCitations } from '@/utils/citations'
import { cn } from '@/utils/cn'

export type CitationTone = 'valid' | 'weak' | 'invalid' | 'neutral'

interface Props {
  content: string
  onCite?: (label: string) => void
  activeLabel?: string | null
  toneFor?: (label: string) => CitationTone
}

const TONES: Record<CitationTone, string> = {
  valid: 'bg-primary-soft text-primary hover:bg-primary hover:text-primary-foreground',
  weak: 'bg-warning-soft text-warning hover:brightness-95',
  invalid: 'bg-danger-soft text-danger line-through',
  neutral: 'bg-surface-2 text-muted-foreground',
}

export const AnswerMarkdown = memo(function AnswerMarkdown({ content, onCite, activeLabel, toneFor }: Props) {
  return (
    <div className="prose-answer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        // Generated text is untrusted: no raw HTML, and links never navigate away unnoticed.
        skipHtml
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith('#cite-')) {
              const label = href.slice(6)
              const tone = toneFor?.(label) ?? 'neutral'
              return (
                <button
                  type="button"
                  onClick={() => onCite?.(label)}
                  className={cn(
                    'mx-0.5 inline-flex -translate-y-px cursor-pointer items-center rounded px-1 py-px align-middle font-mono text-[10.5px] font-semibold transition-colors',
                    TONES[tone],
                    activeLabel === label && 'ring-2 ring-primary/40',
                  )}
                  aria-label={`Show source ${label}`}
                  title={tone === 'invalid' ? 'This citation does not match any provided source' : `Source ${label}`}
                >
                  {label}
                </button>
              )
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-primary underline">
                {children}
              </a>
            )
          },
        }}
      >
        {linkCitations(content)}
      </ReactMarkdown>
    </div>
  )
})
