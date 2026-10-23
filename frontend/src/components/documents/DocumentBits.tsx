import { FileCode2, FileSpreadsheet, FileText, FileType2, Globe, Loader2 } from 'lucide-react'

import { Badge } from '@/components/ui/primitives'
import { isProcessing } from '@/services/documents'
import type { DocumentStatus } from '@/types/api'
import { cn } from '@/utils/cn'

const STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: 'Uploaded',
  queued: 'Queued',
  extracting: 'Extracting',
  chunking: 'Chunking',
  embedding: 'Embedding',
  indexing: 'Indexing',
  completed: 'Indexed',
  failed: 'Failed',
}

export function StatusBadge({ status, progress }: { status: DocumentStatus; progress?: number }) {
  if (status === 'completed') return <Badge tone="success">{STATUS_LABEL[status]}</Badge>
  if (status === 'failed') return <Badge tone="danger">{STATUS_LABEL[status]}</Badge>
  return (
    <Badge tone="primary" aria-live="polite">
      <Loader2 className="size-3 animate-spin" aria-hidden />
      {STATUS_LABEL[status]}
      {isProcessing(status) && progress !== undefined && progress > 0 ? ` ${progress}%` : ''}
    </Badge>
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
