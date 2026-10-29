import type { RetrievalOptions } from '@/types/api'

import { TERMS } from './glossary'

export const STRATEGY_TERMS = {
  hybrid: TERMS.smartSearch,
  dense: TERMS.semanticSearch,
  sparse: TERMS.keywordSearch,
} as const

/** One-line, plain-language summary of the active search settings. */
export function settingsSummary(options: RetrievalOptions): string {
  const method = STRATEGY_TERMS[options.strategy].label
  return options.rerank ? `${method} · optimized` : method
}

/** Friendly names for the pipeline's stage timings. */
export const STAGE_NAMES: Record<string, string> = {
  plan: 'Understanding the question',
  access: 'Checking access',
  sparse_index: 'Loading keyword index',
  embed_query: 'Preparing semantic search',
  dense: 'Semantic search',
  sparse: 'Keyword search',
  fusion: 'Combining rankings',
  load: 'Loading passages',
  dedupe: 'Removing duplicates',
  rerank: 'Relevance optimization',
  compression: 'Trimming passages',
}

export const stageName = (stage: string) => STAGE_NAMES[stage] ?? stage.replace(/_/g, ' ')
