/* A single view model for assistant answers, whether streamed live or loaded from history. */
import type { ChatMessage, EvidenceOut, RetrievalTrace, VerificationReport } from '@/types/api'

export type Validation = 'valid' | 'weak' | 'uncited'

export interface EvidenceView {
  label: string
  documentId: string | null
  chunkId: string | null
  title: string
  pageNumber: number | null
  pageEnd: number | null
  section: string | null
  passage: string
  start: number | null
  end: number | null
  rerankScore: number | null
  fusionScore: number | null
  denseScore: number | null
  sparseScore: number | null
  validation: Validation
  supportScore: number | null
}

export interface AnswerView {
  id: string | null
  content: string
  status: 'streaming' | 'answered' | 'abstained' | 'error'
  evidence: EvidenceView[]
  trace: RetrievalTrace | null
  verification: VerificationReport | null
  provider: string | null
  model: string | null
  retrievalMs: number | null
  generationMs: number | null
  totalMs: number | null
  promptTokens: number | null
  completionTokens: number | null
  error?: string
}

export function locationOf(e: Pick<EvidenceView, 'pageNumber' | 'pageEnd' | 'section'>): string {
  const parts: string[] = []
  if (e.pageNumber) parts.push(e.pageEnd && e.pageEnd !== e.pageNumber ? `pp. ${e.pageNumber}–${e.pageEnd}` : `p. ${e.pageNumber}`)
  if (e.section) parts.push(e.section)
  return parts.join(' · ')
}

function validationFor(label: string, verification: VerificationReport | null): Validation {
  if (!verification?.cited_labels) return 'uncited'
  if (!verification.cited_labels.includes(label)) return 'uncited'
  return verification.supporting_labels.includes(label) ? 'valid' : 'weak'
}

function bestSupport(label: string, verification: VerificationReport | null): number | null {
  const values = (verification?.claims ?? []).map((c) => c.support[label]).filter((v): v is number => v !== undefined)
  return values.length ? Math.max(...values) : null
}

export function evidenceFromStream(items: EvidenceOut[], verification: VerificationReport | null): EvidenceView[] {
  return items.map((e) => ({
    label: e.label,
    documentId: e.document_id,
    chunkId: e.chunk_id,
    title: e.document_title,
    pageNumber: e.page_number,
    pageEnd: e.page_end,
    section: e.section,
    passage: e.content,
    start: e.start_char,
    end: e.end_char,
    rerankScore: e.scores.rerank,
    fusionScore: e.scores.fusion,
    denseScore: e.scores.dense,
    sparseScore: e.scores.sparse,
    validation: validationFor(e.label, verification),
    supportScore: bestSupport(e.label, verification),
  }))
}

export function answerFromMessage(message: ChatMessage): AnswerView {
  const trace = 'queries' in message.retrieval ? (message.retrieval as RetrievalTrace) : null
  const verification = 'claims' in message.verification ? (message.verification as VerificationReport) : null
  return {
    id: message.id,
    content: message.content,
    status: (['answered', 'abstained', 'error'].includes(message.status) ? message.status : 'answered') as AnswerView['status'],
    evidence: message.citations.map((c) => ({
      label: c.label,
      documentId: c.document_id,
      chunkId: c.chunk_id,
      title: c.document_title,
      pageNumber: c.page_number,
      pageEnd: c.page_end ?? null,
      section: c.section,
      passage: c.passage,
      start: c.start_char ?? null,
      end: c.end_char ?? null,
      rerankScore: c.rerank_score,
      fusionScore: c.retrieval_score,
      denseScore: null,
      sparseScore: null,
      validation: c.validation_status === 'invalid' ? 'weak' : (c.validation_status as Validation),
      supportScore: c.support_score,
    })),
    trace,
    verification,
    provider: message.llm_provider,
    model: message.llm_model,
    retrievalMs: message.retrieval_ms,
    generationMs: message.generation_ms,
    totalMs: message.total_ms,
    promptTokens: message.prompt_tokens,
    completionTokens: message.completion_tokens,
  }
}
