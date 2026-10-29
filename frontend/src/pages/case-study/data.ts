/*
 * Content for the public case-study page.
 *
 * Every number here is copied from a report or test run committed to the repository
 * (evaluation/reports/*.md, PROJECT_STATUS.md). Update those sources first, then this file.
 */
import {
  BadgeCheck,
  Ban,
  Boxes,
  Database,
  FileStack,
  FileSearch,
  FlaskConical,
  GitCompareArrows,
  GitMerge,
  KeyRound,
  Layers,
  MonitorSmartphone,
  ScanSearch,
  Server,
  ShieldCheck,
  Sparkles,
  Workflow,
  type LucideIcon,
} from 'lucide-react'

export const REPO_URL = 'https://github.com/RutujaSawant89/Retrieva-'
export const docUrl = (path: string) => `${REPO_URL}/blob/main/${path}`

export type FeatureStatus = 'tested' | 'implemented'

export const FEATURE_STATUS: Record<FeatureStatus, { label: string; hint: string }> = {
  tested: { label: 'Implemented · tested', hint: 'Covered by the automated backend, frontend or end-to-end tests.' },
  implemented: { label: 'Implemented', hint: 'Working in the product; verified manually rather than by a dedicated test.' },
}

/** Optional or missing pieces, stated plainly (PROJECT_STATUS.md, "Known limitations"). */
export const NOT_INCLUDED: { title: string; body: string }[] = [
  { title: 'RAGAS adapter — optional, untested', body: 'Implemented, but needs ragas, LangChain and a judge model; runs record why it was skipped instead of writing placeholder values.' },
  { title: 'OCR — plug-in point only', body: 'Scanned PDFs are detected and reported; an OCR engine can be registered but none ships by default.' },
  { title: 'Knowledge-graph retrieval — not implemented', body: 'Listed as optional in the specification and deliberately left out.' },
  { title: 'SSO, MFA and email delivery — not implemented', body: 'Invitation links are shown to the admin instead of being emailed.' },
]

export interface Feature {
  icon: LucideIcon
  title: string
  technical: string
  body: string
  status: FeatureStatus
}

export const FEATURES: Feature[] = [
  {
    icon: FileStack,
    title: 'Document ingestion',
    technical: 'Structure-aware extraction and chunking',
    body: 'PDF, Word, HTML, Markdown, CSV and text are parsed with page numbers and headings preserved, split into passages and indexed in the background with live progress.',
    status: 'tested',
  },
  {
    icon: GitMerge,
    title: 'Smart Search',
    technical: 'Hybrid dense + BM25 retrieval, Reciprocal Rank Fusion (k=60)',
    body: 'A meaning-based search and a keyword search run side by side and their rankings are fused, so passages are found whichever way they are worded.',
    status: 'tested',
  },
  {
    icon: ScanSearch,
    title: 'Relevance Optimization',
    technical: 'MS MARCO MiniLM cross-encoder reranking',
    body: 'A second model reads the question with each candidate and re-orders them. A per-request toggle, because it does not help on every corpus (see benchmarks).',
    status: 'tested',
  },
  {
    icon: Sparkles,
    title: 'Grounded AI chat',
    technical: 'Streaming generation over labelled evidence (SSE)',
    body: 'Answers stream in and may only cite the labelled passages they were given. Instructions found inside documents are treated as content, never as commands.',
    status: 'tested',
  },
  {
    icon: BadgeCheck,
    title: 'Source Verification',
    technical: 'Independent claim-level citation verification',
    body: 'After an answer is written, every sentence is checked against the passage it cites: invented citations, unsupported sentences and missing figures are flagged.',
    status: 'tested',
  },
  {
    icon: Ban,
    title: 'Evidence Insufficient',
    technical: 'Abstention',
    body: 'When the documents do not support an answer, Retrieva says so instead of guessing.',
    status: 'tested',
  },
  {
    icon: FileSearch,
    title: 'Research reports',
    technical: 'Query decomposition, per-part retrieval, verified synthesis',
    body: 'Bigger questions are broken into parts, each searched separately, then written up as a cited report exportable to PDF, Word or Markdown.',
    status: 'tested',
  },
  {
    icon: GitCompareArrows,
    title: 'Document comparison',
    technical: 'Semantic passage alignment with figure-conflict detection',
    body: 'Two documents are aligned passage by passage to show what is the same, what changed, what was added or removed, and where numbers disagree.',
    status: 'tested',
  },
  {
    icon: FlaskConical,
    title: 'Search Quality Evaluation',
    technical: 'Precision@K, Recall@K, MRR, nDCG, faithfulness, citation precision',
    body: 'Upload questions with known answers and compare search configurations with measured numbers. A RAGAS adapter is included but optional and untested.',
    status: 'tested',
  },
  {
    icon: ShieldCheck,
    title: 'Multi-tenant security',
    technical: 'PostgreSQL Row-Level Security, RBAC, rotating refresh tokens',
    body: 'Each workspace is isolated in the database itself. Four roles control who can upload, ask, evaluate and administer; every sensitive action is audited.',
    status: 'tested',
  },
]

export interface ArchNode {
  id: string
  title: string
  subtitle: string
  icon: LucideIcon
  details: string[]
}

export interface ArchLayer {
  label: string
  nodes: ArchNode[]
}

export const ARCHITECTURE: ArchLayer[] = [
  {
    label: 'Client',
    nodes: [
      {
        id: 'spa',
        title: 'Web app',
        subtitle: 'React 19 · TypeScript · Vite',
        icon: MonitorSmartphone,
        details: [
          'Single-page app with TanStack Query for server state and React Router for navigation.',
          'Access token kept in memory only; the refresh token is an httpOnly, SameSite=Strict cookie.',
          'Answers stream over Server-Sent Events; citations open the exact highlighted passage.',
        ],
      },
    ],
  },
  {
    label: 'API',
    nodes: [
      {
        id: 'api',
        title: 'FastAPI service',
        subtitle: 'Versioned REST API · /api/v1',
        icon: Server,
        details: [
          'Modular monolith: auth, documents, collections, chat, search, research, comparison, evaluation, analytics, admin.',
          'Every request sets the workspace on the database connection so Row-Level Security applies to every query.',
          'Rate limits, correlation IDs, structured logs, Prometheus metrics and OpenTelemetry traces.',
        ],
      },
      {
        id: 'auth',
        title: 'Auth & access',
        subtitle: 'Argon2id · JWT · RBAC',
        icon: KeyRound,
        details: [
          'Argon2id password hashing; short-lived JWT access tokens.',
          'Rotating refresh tokens with reuse detection: replaying an old token revokes the whole session family.',
          'Roles: admin, analyst, researcher, viewer — plus per-document and per-collection permissions.',
        ],
      },
    ],
  },
  {
    label: 'Services',
    nodes: [
      {
        id: 'ingestion',
        title: 'Ingestion worker',
        subtitle: 'Celery + Redis (or in-process)',
        icon: Layers,
        details: [
          'Validates, de-duplicates and stores uploads, then extracts text with page and section structure.',
          'Four chunking strategies; embeddings are reused for unchanged passages.',
          'Each stage reports progress and timing so the UI can show exactly where a document is.',
        ],
      },
      {
        id: 'retrieval',
        title: 'Retrieval engine',
        subtitle: 'Dense · BM25 · RRF · reranking',
        icon: Workflow,
        details: [
          'Semantic search with BGE-small embeddings in pgvector (HNSW) and an in-house Okapi BM25 index.',
          'Rankings fused with Reciprocal Rank Fusion; optional cross-encoder reranking, de-duplication and compression.',
          'Follow-up rewriting, multi-query and keyword expansion trigger automatically when useful.',
        ],
      },
      {
        id: 'generation',
        title: 'Answer & verification',
        subtitle: 'Grounded generation · verifier',
        icon: BadgeCheck,
        details: [
          'LLM providers: OpenAI-compatible (e.g. Ollama), Anthropic, or a no-model extractive mode.',
          'Evidence is labelled S1…Sn; the model may only cite those labels.',
          'An independent verifier checks every sentence, citation, page reference and figure after generation.',
        ],
      },
      {
        id: 'evaluation',
        title: 'Evaluation',
        subtitle: 'IR + RAG metrics · experiments',
        icon: FlaskConical,
        details: [
          'Versioned question sets; experiments run the real pipeline per configuration.',
          'Stores dataset version, models and full configuration with every run for reproducibility.',
        ],
      },
    ],
  },
  {
    label: 'Data & operations',
    nodes: [
      {
        id: 'postgres',
        title: 'PostgreSQL 16 + pgvector',
        subtitle: 'Row-Level Security',
        icon: Database,
        details: [
          'Documents, passages, vectors, conversations, evaluations and audit logs in one database.',
          'The app connects as a non-superuser role, so RLS policies cannot be bypassed by the application.',
          'Schema managed by Alembic migrations, checked for model drift in CI.',
        ],
      },
      {
        id: 'ops',
        title: 'Observability & deploy',
        subtitle: 'Prometheus · Grafana · Docker',
        icon: Boxes,
        details: [
          'Prometheus (multiprocess) metrics with a Grafana dashboard and alert rules.',
          'Docker images for API, worker and web; Compose files for production and development.',
          'GitHub Actions CI: lint, typecheck, tests against real PostgreSQL, migrations, Docker builds, end-to-end tests.',
        ],
      },
    ],
  },
]

export interface PipelineStep {
  id: string
  title: string
  technical: string
  body: string
  branch?: 'answer' | 'abstain'
}

export const PIPELINE: PipelineStep[] = [
  { id: 'query', title: 'User question', technical: 'Query', body: 'A question, optionally limited to chosen documents or collections. Follow-ups are rewritten into complete questions using the conversation.' },
  { id: 'plan', title: 'Query planning', technical: 'Rewrite · multi-query · overview detection', body: 'Decides whether to rephrase, ask in several ways, or treat the question as a request for a document overview.' },
  { id: 'dense', title: 'Semantic search', technical: 'Dense retrieval (BGE-small, pgvector)', body: 'Finds passages with the same meaning as the question, even with different wording.' },
  { id: 'sparse', title: 'Keyword search', technical: 'Sparse retrieval (Okapi BM25)', body: 'Finds passages with the exact words — names, codes, clause numbers.' },
  { id: 'fusion', title: 'Combine rankings', technical: 'Reciprocal Rank Fusion (k = 60)', body: 'Merges the two rankings by position rather than raw score, so neither search dominates.' },
  { id: 'rerank', title: 'Relevance Optimization', technical: 'Cross-encoder reranking (optional)', body: 'Re-reads the top candidates together with the question and re-orders them. Toggleable per request.' },
  { id: 'evidence', title: 'Evidence selection', technical: 'De-duplication · compression · context budget', body: 'Removes near-duplicates, trims to relevant sentences and labels the final passages S1…Sn.' },
  { id: 'generate', title: 'Answer writing', technical: 'Grounded LLM generation (streamed)', body: 'The model writes an answer citing only the labelled passages; document text is never treated as instructions.' },
  { id: 'verify', title: 'Source Verification', technical: 'Independent claim-level verification', body: 'Each sentence is checked against its cited passage: valid labels, support, page references and figures.' },
  { id: 'answer', title: 'Verified answer', technical: 'Answer + citations + verification report', body: 'Shown with clickable sources and a verification summary.', branch: 'answer' },
  { id: 'abstain', title: 'Evidence insufficient', technical: 'Abstention', body: 'If the evidence is too weak, Retrieva declines rather than guessing and says what is missing.', branch: 'abstain' },
]

/** evaluation/reports/beir_scifact.md — 5,183 documents, 300 queries, CPU. */
export const BEIR_SCIFACT = [
  { config: 'Keyword (BM25)', short: 'Keyword', ndcg10: 0.6852, recall100: 0.9176, mrr10: 0.646, p1: 0.5333, latency: '0.9 ms' },
  { config: 'Semantic (dense)', short: 'Semantic', ndcg10: 0.7127, recall100: 0.9417, mrr10: 0.6822, p1: 0.6067, latency: '62.1 ms' },
  { config: 'Smart Search (hybrid RRF)', short: 'Smart Search', ndcg10: 0.7235, recall100: 0.9717, mrr10: 0.689, p1: 0.6, latency: '63.0 ms' },
  { config: 'Hybrid + reranking', short: '+ Reranking', ndcg10: 0.6995, recall100: 0.9717, mrr10: 0.6668, p1: 0.5833, latency: '7,048 ms*' },
]

/** evaluation/reports/northwind_strategies.md — 3 documents, 18 questions. */
export const NORTHWIND = [
  { config: 'Keyword (BM25)', p1: 1.0, recall5: 1.0, mrr: 1.0, ndcg10: 1.0 },
  { config: 'Semantic (dense)', p1: 0.944, recall5: 0.944, mrr: 0.944, ndcg10: 0.944 },
  { config: 'Smart Search (hybrid RRF)', p1: 0.944, recall5: 1.0, mrr: 0.972, ndcg10: 0.98 },
  { config: 'Hybrid + reranking', p1: 1.0, recall5: 1.0, mrr: 1.0, ndcg10: 1.0 },
]

export const TECH_STACK: { group: string; items: { name: string; use: string }[] }[] = [
  {
    group: 'Frontend',
    items: [
      { name: 'React 19 + TypeScript', use: 'UI' },
      { name: 'Vite', use: 'Build & dev server' },
      { name: 'Tailwind CSS 4', use: 'Design tokens & styling' },
      { name: 'Radix UI', use: 'Accessible primitives' },
      { name: 'TanStack Query', use: 'Server state' },
      { name: 'Recharts', use: 'Charts' },
    ],
  },
  {
    group: 'Backend',
    items: [
      { name: 'FastAPI', use: 'REST + SSE API' },
      { name: 'SQLAlchemy 2 + Alembic', use: 'ORM & migrations' },
      { name: 'Celery + Redis', use: 'Background ingestion' },
      { name: 'Argon2 + PyJWT', use: 'Authentication' },
      { name: 'pypdf · python-docx · BeautifulSoup', use: 'Document extraction' },
    ],
  },
  {
    group: 'Data & AI',
    items: [
      { name: 'PostgreSQL 16 + pgvector', use: 'Storage, vectors, RLS' },
      { name: 'BAAI bge-small-en-v1.5', use: 'Embeddings' },
      { name: 'MS MARCO MiniLM cross-encoder', use: 'Reranking' },
      { name: 'OpenAI-compatible / Anthropic / extractive', use: 'Answer generation' },
    ],
  },
  {
    group: 'Quality & operations',
    items: [
      { name: 'pytest · Vitest · Playwright', use: 'Testing' },
      { name: 'ruff · oxlint · tsc', use: 'Static checks' },
      { name: 'Prometheus · Grafana · OpenTelemetry', use: 'Observability' },
      { name: 'Docker Compose · GitHub Actions', use: 'Deploy & CI' },
    ],
  },
]

export const CHALLENGES: { title: string; problem: string; decision: string }[] = [
  {
    title: 'Reranking is not a free win',
    problem: 'The cross-encoder improved the small Northwind set but lowered nDCG@10 on BEIR SciFact (0.724 → 0.700).',
    decision: 'Made Relevance Optimization a per-request toggle and built the evaluation framework so each corpus can be measured instead of assumed.',
  },
  {
    title: 'Trusting citations',
    problem: 'Language models cite sources that do not support the sentence, or invent labels and figures.',
    decision: 'Added an independent verifier that runs after generation and reports validity, coverage and missing figures as signals — never as model confidence.',
  },
  {
    title: 'Tenant isolation that survives bugs',
    problem: 'Application-level filters alone fail open if one query forgets the workspace condition.',
    decision: 'Enforced isolation with PostgreSQL Row-Level Security under a non-superuser role, tested against a real database.',
  },
  {
    title: 'Refresh tokens and lost responses',
    problem: 'Strict refresh-token rotation logged users out when a refresh response was lost on the network.',
    decision: 'A short successor re-issue window recovers lost responses, while genuine replays still revoke the token family.',
  },
  {
    title: '"What is this document about?"',
    problem: 'Overview questions match no specific passage, so the system abstained on reasonable requests.',
    decision: 'Detects overview questions and answers from each document’s opening passages, still cited and verified.',
  },
]

export const DOCS: { title: string; path: string; body: string }[] = [
  { title: 'README', path: 'README.md', body: 'Setup, configuration and a tour of the features.' },
  { title: 'Architecture', path: 'ARCHITECTURE.md', body: 'Components, data model, retrieval pipeline and scaling path.' },
  { title: 'Security', path: 'SECURITY.md', body: 'Threat model, authentication, isolation and prompt-injection defenses.' },
  { title: 'Evaluation', path: 'docs/EVALUATION.md', body: 'Metrics, datasets, experiments and how to reproduce the benchmarks.' },
  { title: 'Project status', path: 'PROJECT_STATUS.md', body: 'What is done, how it was verified, and known limitations.' },
  { title: 'Deployment', path: 'docs/DEPLOYMENT.md', body: 'Docker Compose, environment variables and operations.' },
]

export const GALLERY: { file: string; title: string; caption: string }[] = [
  { file: 'chat.png', title: 'AI Chat', caption: 'A cited answer with its verified source open in the evidence panel.' },
  { file: 'dashboard.png', title: 'Dashboard', caption: 'Quick actions, workspace health and recent activity.' },
  { file: 'documents.png', title: 'Documents', caption: 'Drag-and-drop upload with plain-language processing status.' },
  { file: 'search.png', title: 'Search Explorer', caption: 'Every passage with its semantic, keyword, combined and relevance scores.' },
  { file: 'research.png', title: 'Research', caption: 'A multi-part question answered as a structured, cited report.' },
  { file: 'evaluation.png', title: 'Search Quality Evaluation', caption: 'Search configurations compared on a labelled question set.' },
]

/** Most recent full local run of each suite (update together with PROJECT_STATUS.md). */
export const TEST_RESULTS = {
  date: '29 October 2026',
  items: [
    { value: '114', label: 'Backend tests passed', detail: 'pytest on real PostgreSQL 16 + pgvector, RLS enforced via a non-superuser role.' },
    { value: '13', label: 'Frontend tests passed', detail: 'Vitest + Testing Library: auth flows, token refresh, validation.' },
    { value: 'E2E', label: 'Workflow test passing', detail: 'Playwright: upload → index → ask → cited answer → open source passage.' },
    { value: '0', label: 'Lint & type errors', detail: 'ruff, oxlint and tsc; CI runs the same checks plus migrations and Docker builds.' },
  ],
}
