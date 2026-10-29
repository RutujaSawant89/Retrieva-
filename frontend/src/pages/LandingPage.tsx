import { motion } from 'framer-motion'
import {
  ArrowRight,
  BadgeCheck,
  Ban,
  FileSearch,
  FlaskConical,
  GitMerge,
  Layers,
  Lock,
  ScanSearch,
  ShieldCheck,
} from 'lucide-react'
import { Link } from 'react-router'

import { Logo } from '@/components/brand/Logo'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/AuthContext'

const PIPELINE = [
  { icon: Layers, title: 'Structure-aware ingestion', body: 'PDF, DOCX, HTML, Markdown, CSV and text are parsed with page numbers and headings preserved, then chunked by section.' },
  { icon: GitMerge, title: 'Hybrid retrieval', body: 'Dense embeddings and BM25 run side by side and are fused with Reciprocal Rank Fusion.' },
  { icon: ScanSearch, title: 'Cross-encoder reranking', body: 'Candidates are re-scored jointly with the query, so the evidence passed on is the evidence that answers.' },
  { icon: FileSearch, title: 'Grounded generation', body: 'Answers may only cite labelled passages. Instructions found inside documents are treated as data.' },
  { icon: BadgeCheck, title: 'Citation verification', body: 'Every citation is mapped back to its chunk, page and document, and every sentence is checked for support.' },
  { icon: Ban, title: 'Principled abstention', body: 'When the evidence is insufficient, Retrieva says so instead of guessing.' },
]

const PILLARS = [
  { icon: FlaskConical, title: 'Measured, not claimed', body: 'Built-in evaluation computes Precision@K, Recall@K, MRR, nDCG, faithfulness and citation precision on your own datasets, and compares retrieval strategies side by side.' },
  { icon: ShieldCheck, title: 'Isolated by design', body: 'Every organization is isolated by application checks and PostgreSQL Row-Level Security. Roles control who can upload, query, evaluate and administer.' },
  { icon: Lock, title: 'Secure sessions', body: 'Short-lived access tokens kept in memory, rotating httpOnly refresh cookies with reuse detection, rate limits and a full audit trail.' },
]

export function LandingPage() {
  const { status } = useAuth()
  const authed = status === 'authenticated'

  return (
    <div className="min-h-full bg-background">
      <header className="sticky top-0 z-30 border-b border-border/70 bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Logo />
          <nav className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <Link to="/case-study">Case study</Link>
            </Button>
            {authed ? (
              <Button asChild size="sm">
                <Link to="/app">
                  Open workspace <ArrowRight />
                </Link>
              </Button>
            ) : (
              <>
                <Button asChild variant="ghost" size="sm">
                  <Link to="/login">Sign in</Link>
                </Button>
                <Button asChild size="sm">
                  <Link to="/register">Get started</Link>
                </Button>
              </>
            )}
          </nav>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-4 pb-16 pt-16 sm:px-6 sm:pt-24">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="max-w-3xl"
        >
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-muted-foreground">
            <span className="size-1.5 rounded-full bg-success" /> Enterprise AI Retrieval & Intelligence Platform
          </p>
          <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-[56px]">
            Search smarter. Retrieve precisely.{' '}
            <span className="text-primary">Trust every answer.</span>
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted-foreground">
            Retrieva turns your document collections into an evidence-grounded knowledge base. Every answer shows where it
            came from, which passages support it, and whether those passages actually say what the answer claims.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link to={authed ? '/app' : '/register'}>
                {authed ? 'Open workspace' : 'Create your organization'} <ArrowRight />
              </Link>
            </Button>
            {!authed && (
              <Button asChild size="lg" variant="secondary">
                <Link to="/login">Sign in</Link>
              </Button>
            )}
            <Button asChild size="lg" variant="ghost">
              <Link to="/case-study">How it&apos;s built</Link>
            </Button>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="mt-14 overflow-hidden rounded-2xl border border-border bg-surface shadow-[var(--shadow-pop)]"
          aria-label="Illustration of an evidence-grounded answer"
        >
          <div className="flex items-center gap-1.5 border-b border-border px-4 py-2.5">
            <span className="size-2.5 rounded-full bg-border-strong" />
            <span className="size-2.5 rounded-full bg-border-strong" />
            <span className="size-2.5 rounded-full bg-border-strong" />
            <span className="ml-3 text-xs text-muted-foreground">Illustrative example</span>
          </div>
          <div className="grid gap-0 md:grid-cols-[1.4fr_1fr]">
            <div className="p-6">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Question</p>
              <p className="mt-1 font-medium">What notice period does the vendor agreement require for termination?</p>
              <p className="mt-5 text-xs font-medium uppercase tracking-wide text-muted-foreground">Answer</p>
              <p className="mt-1 leading-relaxed">
                Either party may terminate for convenience with <strong>ninety (90) days' written notice</strong>{' '}
                <Cite n={1} />. Termination for material breach requires a <strong>30-day cure period</strong> after
                notice <Cite n={2} />.
              </p>
              <div className="mt-5 flex flex-wrap gap-2 text-xs">
                <Pill tone="success">2 of 2 citations valid</Pill>
                <Pill tone="success">All sentences supported</Pill>
              </div>
            </div>
            <div className="border-t border-border bg-evidence p-6 md:border-l md:border-t-0">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Evidence</p>
              <Evidence n={1} source="Vendor-Agreement.pdf · p. 12 · §14.2 Termination for Convenience">
                "…either party may terminate this Agreement upon ninety (90) days' prior written notice…"
              </Evidence>
              <Evidence n={2} source="Vendor-Agreement.pdf · p. 12 · §14.3 Termination for Cause">
                "…provided the breaching party fails to cure within thirty (30) days of receipt of notice…"
              </Evidence>
            </div>
          </div>
        </motion.div>
      </section>

      <section className="border-t border-border bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight">A retrieval pipeline you can inspect</h2>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            Each stage can be enabled, disabled and benchmarked independently, so quality decisions are backed by
            experiments instead of intuition.
          </p>
          <div className="mt-10 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
            {PIPELINE.map((step, index) => (
              <div key={step.title} className="bg-surface p-6">
                <div className="flex items-center gap-3">
                  <span className="flex size-8 items-center justify-center rounded-lg bg-primary-soft text-primary">
                    <step.icon className="size-4" />
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">0{index + 1}</span>
                </div>
                <h3 className="mt-4 font-medium">{step.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="grid gap-8 md:grid-cols-3">
          {PILLARS.map((pillar) => (
            <div key={pillar.title}>
              <pillar.icon className="size-5 text-primary" />
              <h3 className="mt-3 font-medium">{pillar.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{pillar.body}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-6 text-sm text-muted-foreground sm:px-6">
          <Logo />
          <span>Search Smarter. Retrieve Precisely. Trust Every Answer.</span>
        </div>
      </footer>
    </div>
  )
}

function Cite({ n }: { n: number }) {
  return (
    <sup className="mx-0.5 rounded bg-primary-soft px-1 py-px font-mono text-[10px] font-semibold text-primary">S{n}</sup>
  )
}

function Pill({ children, tone }: { children: string; tone: 'success' }) {
  return (
    <span className={tone === 'success' ? 'rounded-md bg-success-soft px-2 py-1 font-medium text-success' : ''}>
      {children}
    </span>
  )
}

function Evidence({ n, source, children }: { n: number; source: string; children: string }) {
  return (
    <div className="mt-3 rounded-lg border border-border bg-surface p-3">
      <div className="flex items-center gap-2">
        <Cite n={n} />
        <span className="truncate text-xs text-muted-foreground">{source}</span>
      </div>
      <p className="mt-1.5 text-sm leading-relaxed">{children}</p>
    </div>
  )
}
