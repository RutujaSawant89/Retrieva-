import type { RetrievalScopeInput } from '@/types/api'

export function scopeSummary(scope: RetrievalScopeInput | null | undefined): string {
  const docs = scope?.document_ids?.length ?? 0
  const cols = scope?.collection_ids?.length ?? 0
  if (!docs && !cols) return 'All documents'
  const parts = []
  if (docs) parts.push(`${docs} document${docs > 1 ? 's' : ''}`)
  if (cols) parts.push(`${cols} collection${cols > 1 ? 's' : ''}`)
  return parts.join(' + ')
}
