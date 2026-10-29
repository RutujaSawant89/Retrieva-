import { AlertCircle, CheckCircle2, FileCode2, FileSpreadsheet, FileText, FileType2, Globe, Loader2 } from 'lucide-react'

import { Tooltip } from '@/components/ui/overlays'
import { Badge } from '@/components/ui/primitives'
import { isProcessing } from '@/services/documents'
import type { DocumentStatus } from '@/types/api'
import { cn } from '@/utils/cn'

/** Plain-language status, with the technical pipeline stage in the tooltip. */
const STATUS: Record<DocumentStatus, { label: string; detail: string }> = {
  uploaded: { label: 'Uploaded', detail: 'Received and waiting to be processed.' },
  queued: { label: 'Waiting', detail: 'Queued for processing.' },
  extracting: { label: 'Reading file', detail: 'Extracting text, pages and headings.' },
  chunking: { label: 'Splitting into passages', detail: 'Dividing the text into short, citable passages (chunking).' },
  embedding: { label: 'Indexing', detail: 'Creating semantic search vectors for each passage (embedding).' },
  indexing: { label: 'Finishing up', detail: 'Saving passages to the search index.' },
  completed: { label: 'Ready', detail: 'Processed and searchable. You can ask questions about it.' },
  failed: { label: 'Failed', detail: 'Processing failed — open the document to see why and retry.' },
}


export function StatusBadge({ status, progress }: { status: DocumentStatus; progress?: number }) {
  const meta = STATUS[status]
  const badge =
    status === 'completed' ? (
      <Badge tone="success">
        <CheckCircle2 className="size-3" aria-hidden />
        {meta.label}
      </Badge>
    ) : status === 'failed' ? (
      <Badge tone="danger">
        <AlertCircle className="size-3" aria-hidden />
        {meta.label}
      </Badge>
    ) : (
      <Badge tone="primary" aria-live="polite">
        <Loader2 className="size-3 animate-spin" aria-hidden />
        {meta.label}
        {isProcessing(status) && progress !== undefined && progress > 0 ? ` ${progress}%` : ''}
      </Badge>
    )
  return (
    <Tooltip content={meta.detail}>
      <span className="inline-flex cursor-default">{badge}</span>
    </Tooltip>
  )
}

const TYPE_ICON: Record<string, typeof FileText> = {
  pdf: FileType2,
  docx: FileText,
  txt: FileText,
  md: FileCode2,
  csv: FileSpreadsheet,
  html: Globe,
}

const TYPE_TONE: Record<string, string> = {
  pdf: 'text-danger bg-danger-soft',
  docx: 'text-primary bg-primary-soft',
  csv: 'text-success bg-success-soft',
  html: 'text-warning bg-warning-soft',
}

export function FileTypeIcon({ type, className }: { type: string; className?: string }) {
  const Icon = TYPE_ICON[type] ?? FileText
  return (
    <span
      className={cn(
        'flex size-8 shrink-0 items-center justify-center rounded-lg',
        TYPE_TONE[type] ?? 'bg-surface-2 text-muted-foreground',
        className,
      )}
      aria-hidden
    >
      <Icon className="size-4" />
    </span>
  )
}
