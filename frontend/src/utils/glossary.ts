/**
 * Plain-language names for Retrieva's technical concepts.
 *
 * The UI shows `label` by default and keeps the precise technical name and an explanation one
 * hover away (InfoTip), so first-time users are not confronted with jargon while engineers can
 * still see exactly what runs.
 */
export interface Term {
  label: string
  technical: string
  description: string
}

export const TERMS = {
  smartSearch: {
    label: 'Smart Search',
    technical: 'Hybrid retrieval with Reciprocal Rank Fusion',
    description:
      'Runs a meaning-based search and a keyword search together and merges their rankings, so passages are found whether they use your exact words or say the same thing differently.',
  },
  semanticSearch: {
    label: 'Semantic Search',
    technical: 'Dense retrieval (BGE embeddings, pgvector cosine similarity)',
    description: 'Finds passages with the same meaning as your question, even when the wording differs.',
  },
  keywordSearch: {
    label: 'Keyword Search',
    technical: 'Sparse retrieval (Okapi BM25)',
    description: 'Finds passages containing your exact words — best for names, codes and specific terms.',
  },
  relevanceOptimization: {
    label: 'Relevance Optimization',
    technical: 'Cross-encoder reranking (MS MARCO MiniLM)',
    description:
      'A second model reads your question together with each candidate passage and re-orders them by how well they actually answer it.',
  },
  sourceVerification: {
    label: 'Source Verification',
    technical: 'Independent claim-level citation verification',
    description:
      'After an answer is written, every sentence is checked against the passage it cites. Invented citations, unsupported sentences and figures that do not appear in the sources are flagged.',
  },
  evidenceInsufficient: {
    label: 'Evidence Insufficient',
    technical: 'Abstention',
    description:
      'When your documents do not contain enough relevant evidence, Retrieva says so instead of guessing.',
  },
  searchQuality: {
    label: 'Search Quality Evaluation',
    technical: 'Retrieval and RAG evaluation (Precision@K, Recall@K, MRR, nDCG, faithfulness)',
    description:
      'Measures how reliably the right passages are found for a set of questions with known answers, so different search settings can be compared with real numbers.',
  },
  citationValidity: {
    label: 'Valid citations',
    technical: 'Citation validity',
    description: 'Share of citations in the answer that point to a source Retrieva actually provided.',
  },
  evidenceCoverage: {
    label: 'Supported sentences',
    technical: 'Evidence coverage',
    description: 'Share of factual sentences in the answer that are backed by the passage they cite.',
  },
  fusion: {
    label: 'Combined ranking',
    technical: 'Reciprocal Rank Fusion score',
    description: 'How highly the semantic and keyword searches ranked this passage, combined.',
  },
  chunk: {
    label: 'Passage',
    technical: 'Chunk',
    description: 'Documents are split into short passages so answers can point to the exact part that supports them.',
  },
} satisfies Record<string, Term>

export type TermKey = keyof typeof TERMS
