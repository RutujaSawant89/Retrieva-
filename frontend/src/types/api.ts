/* Types mirroring backend/app/schemas. Keep in sync with the OpenAPI spec (/api/openapi.json). */

export type RoleName = 'admin' | 'analyst' | 'researcher' | 'viewer'

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface UserOut {
  id: string
  email: string
  full_name: string
  created_at: string
  last_login_at: string | null
}

export interface OrganizationSummary {
  id: string
  name: string
  slug: string
  role: RoleName
}

export interface SessionOut {
  access_token: string
  token_type: string
  expires_at: string
  user: UserOut
  organization: OrganizationSummary
  organizations: OrganizationSummary[]
  permissions: string[]
}

export interface MessageOut {
  message: string
}

export interface MemberOut {
  user_id: string
  email: string
  full_name: string
  role: RoleName
  is_active: boolean
  joined_at: string
  last_login_at: string | null
}

export interface InvitationOut {
  id: string
  email: string
  role: RoleName
  expires_at: string
  accepted_at: string | null
  created_at: string
  token: string | null
}

export interface AuditLogOut {
  id: string
  user_id: string | null
  user_email: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  ip_address: string | null
  correlation_id: string | null
  details: Record<string, unknown>
  created_at: string
}

export interface RoleOut {
  name: RoleName
  description: string
  permissions: string[]
}

export interface OrganizationOut {
  id: string
  name: string
  slug: string
  created_at: string
}

/* ------------------------------------------------------------------ documents */

export type DocumentStatus =
  | 'uploaded'
  | 'queued'
  | 'extracting'
  | 'chunking'
  | 'embedding'
  | 'indexing'
  | 'completed'
  | 'failed'

export type Visibility = 'organization' | 'private'
export type ChunkingStrategy = 'recursive' | 'token' | 'semantic' | 'structure'

export interface DocumentOut {
  id: string
  title: string
  original_filename: string
  file_type: string
  mime_type: string
  file_size: number
  content_hash: string
  category: string | null
  visibility: Visibility
  page_count: number | null
  status: DocumentStatus
  progress: number
  error_message: string | null
  chunk_count: number
  embedding_model: string | null
  chunking_strategy: string | null
  owner_id: string | null
  owner_name: string | null
  created_at: string
  updated_at: string
  indexed_at: string | null
  collection_ids: string[]
}

export interface IngestionJobOut {
  id: string
  status: DocumentStatus
  progress: number
  attempts: number
  error_message: string | null
  stage_timings: Record<string, number>
  config: Record<string, unknown>
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface DocumentDetail extends DocumentOut {
  metadata: Record<string, unknown>
  latest_job: IngestionJobOut | null
  can_modify: boolean
}

export interface UploadResult {
  filename: string
  outcome: 'created' | 'duplicate' | 'rejected'
  document: DocumentOut | null
  duplicate_of: string | null
  error: string | null
}

export interface ChunkOut {
  id: string
  chunk_index: number
  content: string
  token_count: number
  page_number: number | null
  page_end: number | null
  section: string | null
  heading_path: string[]
  start_char: number
  end_char: number
}

export interface ContentBlock {
  text: string
  kind: string
  page: number | null
  level: number
  heading_path: string[]
  start: number
  end: number
}

export interface DocumentContent {
  document_id: string
  page_count: number | null
  blocks: ContentBlock[]
}

/* ------------------------------------------------------------------ retrieval */

export interface RetrievalOptions {
  strategy: 'dense' | 'sparse' | 'hybrid'
  top_k: number
  candidate_k: number
  rrf_k: number
  dense_weight: number
  sparse_weight: number
  metric: 'cosine' | 'inner_product'
  rerank: boolean
  rewrite: boolean | 'auto'
  multi_query: boolean | 'auto'
  expansion: boolean | 'auto'
  metadata_boost: boolean
  compression: boolean
  dedupe: boolean
  relevance_threshold: number | null
}

export interface RetrievalScopeInput {
  document_ids: string[]
  collection_ids: string[]
}

export interface EvidenceOut {
  label: string
  chunk_id: string
  document_id: string
  document_title: string
  file_type: string
  page_number: number | null
  page_end: number | null
  section: string | null
  location: string
  content: string
  compressed: string | null
  start_char: number
  end_char: number
  scores: { dense: number | null; sparse: number | null; fusion: number | null; rerank: number | null }
  ranks: { dense: number | null; sparse: number | null; final: number | null }
}

export interface SearchResponse {
  query: string
  queries: string[]
  decisions: string[]
  timings_ms: Record<string, number>
  total_ms: number
  candidates_considered: number
  reranker: string | null
  embedding_model: string | null
  results: EvidenceOut[]
}

export interface SearchHistoryItem {
  id: string
  kind: string
  query: string
  rewritten_queries: string[]
  strategy: string
  result_count: number
  top_score: number | null
  success: boolean
  retrieval_ms: number
  created_at: string
}

/* ------------------------------------------------------------------ chat */

export interface ClaimCheck {
  text: string
  citations: string[]
  valid_citations: string[]
  invalid_citations: string[]
  support: Record<string, number>
  best_support: number
  status: 'supported' | 'partial' | 'unsupported' | 'uncited'
  missing_numbers: string[]
  page_issues: string[]
}

export interface VerificationReport {
  scorer: string
  claims: ClaimCheck[]
  total_citations: number
  valid_citations: number
  invalid_labels: string[]
  citation_validity: number | null
  citation_precision: number | null
  evidence_coverage: number | null
  unsupported_claims: string[]
  cited_labels: string[]
  supporting_labels: string[]
  page_reference_issues: string[]
  low_support: boolean
}

export interface RetrievalTrace {
  queries: string[]
  decisions: string[]
  timings_ms: Record<string, number>
  total_ms: number
  candidates_considered: number
  reranker: string | null
  embedding_model: string | null
  config: Partial<RetrievalOptions>
  conflicts: { labels: string[]; reason: string }[]
  suspicious_sources: string[]
  dropped_for_budget: number
  abstention_reason?: string | null
  evidence?: EvidenceOut[]
}

export interface CitationOut {
  id: string
  label: string
  chunk_id: string | null
  document_id: string | null
  document_title: string
  page_number: number | null
  page_end: number | null
  section: string | null
  passage: string
  start_char: number | null
  end_char: number | null
  retrieval_score: number | null
  rerank_score: number | null
  cited_in_answer: boolean
  validation_status: 'valid' | 'weak' | 'uncited' | 'invalid'
  support_score: number | null
}

export type MessageStatus = 'answered' | 'abstained' | 'error'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status: MessageStatus | string
  retrieval: RetrievalTrace | Record<string, never>
  verification: VerificationReport | Record<string, never>
  llm_provider: string | null
  llm_model: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  retrieval_ms: number | null
  generation_ms: number | null
  total_ms: number | null
  created_at: string
  citations: CitationOut[]
}

export interface ConversationOut {
  id: string
  title: string
  scope: Partial<RetrievalScopeInput>
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConversationDetail extends ConversationOut {
  summary: string | null
  messages: ChatMessage[]
}

/* ------------------------------------------------------------------ collections */

export interface CollectionOut {
  id: string
  name: string
  description: string
  visibility: Visibility
  created_by: string | null
  created_at: string
  updated_at: string
  document_count: number
  can_modify: boolean
}
