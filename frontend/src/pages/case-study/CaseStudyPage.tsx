import { ArrowDown, ArrowRight, BookOpen, Check, ExternalLink, GitBranch, Info, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Logo } from '@/components/brand/Logo'
import { ChartCard } from '@/components/charts/Charts'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, Tooltip } from '@/components/ui/overlays'
import { Card } from '@/components/ui/primitives'
import { useAuth } from '@/contexts/AuthContext'
import { cn } from '@/utils/cn'

import {
  ARCHITECTURE,
  BEIR_SCIFACT,
  CHALLENGES,
  DOCS,
  FEATURE_STATUS,
  FEATURES,
  GALLERY,
  NORTHWIND,
  NOT_INCLUDED,
  PIPELINE,
  REPO_URL,
  TECH_STACK,
  TEST_RESULTS,
  docUrl,
} from './data'

const SECTIONS = [
  ['features', 'Features'],
  ['architecture', 'Architecture'],
  ['pipeline', 'Pipeline'],
  ['benchmarks', 'Benchmarks'],
  ['testing', 'Testing'],
  ['docs', 'Docs'],
] as const

function Section({ id, eyebrow, title, intro, children, className }: {
  id: string
  eyebrow: string
  title: string
  intro?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section id={id} className={cn('scroll-mt-20 py-16 sm:py-20', className)}>
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-primary">{eyebrow}</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
        {intro && <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">{intro}</p>}
        <div className="mt-10">{children}</div>
      </div>
    </section>
  )
}

function ArchitectureDiagram() {
  const [selected, setSelected] = useState('retrieval')
  const node = ARCHITECTURE.flatMap((l) => l.nodes).find((n) => n.id === selected)!
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-3" role="group" aria-label="Architecture components">
        {ARCHITECTURE.map((layer, i) => (
          <div key={layer.label}>
            <div className="flex flex-col gap-2 rounded-2xl border border-border bg-surface p-3 sm:flex-row sm:items-stretch">
              <p className="w-28 shrink-0 self-center text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                {layer.label}
              </p>
              <div className="grid flex-1 gap-2" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(150px, 1fr))` }}>
                {layer.nodes.map((n) => {
                  const active = n.id === selected
                  return (
                    <button
                      key={n.id}
                      type="button"
                      onClick={() => setSelected(n.id)}
                      aria-pressed={active}
                      className={cn(
                        'flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 text-left transition-all',
                        active
                          ? 'border-primary bg-primary-soft shadow-[0_0_0_3px_color-mix(in_srgb,var(--primary)_14%,transparent)]'
                          : 'border-border bg-background hover:border-border-strong',
                      )}
                    >
                      <n.icon className={cn('mt-0.5 size-4 shrink-0', active ? 'text-primary' : 'text-muted-foreground')} />
                      <span className="min-w-0">
                        <span className="block text-[13px] font-medium">{n.title}</span>
                        <span className="block text-[11.5px] text-muted-foreground">{n.subtitle}</span>
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
            {i < ARCHITECTURE.length - 1 && (
              <div className="flex justify-center py-1" aria-hidden>
                <ArrowDown className="size-4 text-border-strong" />
              </div>
            )}
          </div>
        ))}
      </div>
      <Card className="h-fit p-5 lg:sticky lg:top-20" aria-live="polite">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary-soft text-primary">
            <node.icon className="size-4" />
          </span>
          <div>
            <p className="text-sm font-semibold">{node.title}</p>
            <p className="text-xs text-muted-foreground">{node.subtitle}</p>
          </div>
        </div>
        <ul className="mt-4 space-y-2.5 text-[13px] leading-relaxed">
          {node.details.map((d) => (
            <li key={d} className="flex gap-2">
              <Check className="mt-1 size-3.5 shrink-0 text-primary" />
              <span>{d}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-[11.5px] text-muted-foreground">Select any component to see what it does.</p>
      </Card>
    </div>
  )
}

function PipelineExplorer() {
  const [selected, setSelected] = useState('fusion')
  const main = PIPELINE.filter((s) => !s.branch)
  const branches = PIPELINE.filter((s) => s.branch)
  const step = PIPELINE.find((s) => s.id === selected)!
  const parallel = new Set(['dense', 'sparse'])

  const StepButton = ({ id, title, index, tone }: { id: string; title: string; index?: number; tone?: 'answer' | 'abstain' }) => (
    <button
      type="button"
      onClick={() => setSelected(id)}
      aria-pressed={selected === id}
      className={cn(
        'flex w-full cursor-pointer items-center gap-2 rounded-xl border px-3 py-2.5 text-left text-[13px] font-medium transition-all',
        selected === id
          ? 'border-primary bg-primary text-primary-foreground'
          : tone === 'answer'
            ? 'border-success/30 bg-success-soft hover:border-success/60'
            : tone === 'abstain'
              ? 'border-warning/30 bg-warning-soft hover:border-warning/60'
              : 'border-border bg-surface hover:border-border-strong',
      )}
    >
      {index !== undefined && (
        <span
          className={cn(
            'flex size-5 shrink-0 items-center justify-center rounded-full text-[10.5px] font-semibold',
            selected === id ? 'bg-white/20' : 'bg-primary-soft text-primary',
          )}
        >
          {index}
        </span>
      )}
      {title}
    </button>
  )

  // Group dense + sparse into one row; they run in parallel.
  const rows: (typeof main)[] = []
  for (const s of main) {
    if (parallel.has(s.id) && rows.at(-1)?.every((p) => parallel.has(p.id))) rows.at(-1)!.push(s)
    else rows.push([s])
  }

  let n = 0
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="mx-auto w-full max-w-xl">
        {rows.map((row) => (
          <div key={row[0].id}>
            <div className={cn('grid gap-2', row.length > 1 && 'grid-cols-2')}>
              {row.map((s) => (
                <StepButton key={s.id} id={s.id} title={s.title} index={++n} />
              ))}
            </div>
            <div className="flex justify-center py-1" aria-hidden>
              <ArrowDown className="size-4 text-border-strong" />
            </div>
          </div>
        ))}
        <div className="grid grid-cols-2 gap-2">
          {branches.map((s) => (
            <StepButton key={s.id} id={s.id} title={s.title} tone={s.branch} />
          ))}
        </div>
      </div>
      <Card className="h-fit p-5 lg:sticky lg:top-20" aria-live="polite">
        <p className="text-sm font-semibold">{step.title}</p>
        <p className="mt-0.5 font-mono text-[11.5px] text-muted-foreground">{step.technical}</p>
        <p className="mt-3 text-[13.5px] leading-relaxed">{step.body}</p>
        <p className="mt-4 text-[11.5px] text-muted-foreground">
          Every run records these steps, so the &ldquo;How it was found&rdquo; tab in AI Chat shows what actually happened.
        </p>
      </Card>
    </div>
  )
}

export function CaseStudyPage() {
  const { status } = useAuth()
  const productLink = status === 'authenticated' ? '/app' : '/login'
  const [zoomed, setZoomed] = useState<(typeof GALLERY)[number] | null>(null)

  return (
    <div className="min-h-full bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border/70 bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" aria-label="Retrieva home">
            <Logo />
          </Link>
          <nav className="hidden items-center gap-1 md:flex" aria-label="Case study sections">
            {SECTIONS.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="rounded-md px-2.5 py-1.5 text-[13px] text-muted-foreground hover:bg-surface-2 hover:text-foreground">
                {label}
              </a>
            ))}
          </nav>
          <Button asChild size="sm">
            <Link to={productLink}>
              View product <ArrowRight />
            </Link>
          </Button>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="relative overflow-hidden border-b border-border">
          <div className="mx-auto max-w-6xl px-4 pb-16 pt-16 sm:px-6 sm:pt-24">
            <div className="mx-auto max-w-3xl text-center">
              <p className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted-foreground">
                <ShieldCheck className="size-3.5 text-primary" /> Engineering case study
              </p>
              <h1 className="mt-6 text-4xl font-semibold tracking-tight sm:text-6xl">RETRIEVA</h1>
              <p className="mt-4 text-lg font-medium text-primary sm:text-xl">
                Search Smarter. Retrieve Precisely. Trust Every Answer.
              </p>
              <p className="mx-auto mt-4 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
                An evidence-grounded document intelligence platform. Every answer cites the exact passage it came from, is
                independently verified, and is withheld when the evidence isn&apos;t there.
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-3">
                <Button asChild size="lg">
                  <a href="#architecture">Explore architecture</a>
                </Button>
                <Button asChild size="lg" variant="secondary">
                  <a href={REPO_URL} target="_blank" rel="noreferrer">
                    <GitBranch /> View GitHub
                  </a>
                </Button>
                <Button asChild size="lg" variant="ghost">
                  <Link to={productLink}>
                    View product <ArrowRight />
                  </Link>
                </Button>
              </div>
            </div>
            <figure className="mx-auto mt-14 max-w-5xl">
              <div className="overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_24px_60px_-24px_rgb(16_24_40/0.25)]">
                <img
                  src="/case-study/chat.png"
                  alt="Retrieva AI Chat answering a question with a cited, verified source shown in the evidence panel"
                  className="block w-full"
                  width={1440}
                  height={900}
                />
              </div>
              <figcaption className="mt-3 text-center text-xs text-muted-foreground">
                Real screenshot of the running product on the fictional Northwind sample documents.
              </figcaption>
            </figure>
          </div>
        </section>

        {/* Problem & solution */}
        <Section id="problem" eyebrow="Why it exists" title="Answers you can check, not just read">
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="p-6">
              <p className="text-sm font-semibold">The problem</p>
              <ul className="mt-3 space-y-2.5 text-[14px] leading-relaxed text-muted-foreground">
                <li>AI assistants answer confidently even when the source documents say nothing about the question.</li>
                <li>Citations are often decorative: they point to a document, not the passage, and nobody checks them.</li>
                <li>Search quality is rarely measured, so teams can&apos;t tell whether a change helped.</li>
                <li>Shared deployments risk one team&apos;s documents leaking into another&apos;s answers.</li>
              </ul>
            </Card>
            <Card className="border-primary/30 p-6">
              <p className="text-sm font-semibold text-primary">The approach</p>
              <ul className="mt-3 space-y-2.5 text-[14px] leading-relaxed">
                <li>Answers may only use labelled passages from your documents, and each citation opens the exact text.</li>
                <li>An independent verifier checks every sentence after the answer is written.</li>
                <li>When evidence is insufficient, Retrieva declines instead of guessing.</li>
                <li>Built-in evaluation and database-level isolation make quality and security measurable.</li>
              </ul>
            </Card>
          </div>
        </Section>

        {/* Features */}
        <Section
          id="features"
          eyebrow="Core features"
          title="What Retrieva does"
          intro="Plain-language names in the product, with the precise technique one hover away."
          className="bg-surface-2/50"
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <Card key={f.title} className="flex flex-col p-5">
                <div className="flex items-start justify-between gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-primary-soft text-primary">
                    <f.icon className="size-4" />
                  </span>
                  <Tooltip content={FEATURE_STATUS[f.status].hint}>
                    <span className="cursor-help rounded-full bg-success-soft px-2 py-0.5 text-[10.5px] font-medium text-success">
                      {FEATURE_STATUS[f.status].label}
                    </span>
                  </Tooltip>
                </div>
                <p className="mt-4 text-[15px] font-semibold">{f.title}</p>
                <p className="mt-0.5 text-[11.5px] text-muted-foreground">{f.technical}</p>
                <p className="mt-3 text-[13.5px] leading-relaxed text-muted-foreground">{f.body}</p>
              </Card>
            ))}
          </div>
          <Card className="mt-6 p-5">
            <p className="flex items-center gap-2 text-sm font-semibold">
              <Info className="size-4 text-muted-foreground" /> Optional or not included
            </p>
            <ul className="mt-3 grid gap-3 text-[13px] sm:grid-cols-2">
              {NOT_INCLUDED.map((item) => (
                <li key={item.title}>
                  <p className="font-medium">{item.title}</p>
                  <p className="text-muted-foreground">{item.body}</p>
                </li>
              ))}
            </ul>
          </Card>
        </Section>

        {/* Architecture */}
        <Section
          id="architecture"
          eyebrow="Technical architecture"
          title="A modular monolith with isolation in the database"
          intro="One API service with clear internal modules, a background worker for ingestion, and PostgreSQL holding documents, vectors and security policies."
        >
          <ArchitectureDiagram />
        </Section>

        {/* Pipeline */}
        <Section
          id="pipeline"
          eyebrow="Retrieval pipeline"
          title="From question to verified answer"
          intro="Select a step to see what it does. Semantic and keyword search run in parallel; the run ends in either a verified answer or an honest abstention."
          className="bg-surface-2/50"
        >
          <PipelineExplorer />
        </Section>

        {/* Benchmarks */}
        <Section
          id="benchmarks"
          eyebrow="Benchmarks"
          title="Measured, including where it didn't help"
          intro="BEIR SciFact: 5,183 scientific abstracts and 300 test queries with official relevance judgments, run on a laptop CPU."
        >
          <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
            <ChartCard
              kind="bar"
              title="BEIR SciFact — ranking quality"
              description="Higher is better"
              data={BEIR_SCIFACT.map((row) => ({ ...row, config: row.short }))}
              xKey="config"
              xLabel="Configuration"
              series={[
                { key: 'ndcg10', label: 'nDCG@10' },
                { key: 'mrr10', label: 'MRR@10' },
                { key: 'p1', label: 'P@1' },
              ]}
              format={(v) => (v === null || v === undefined ? '—' : Number(v).toFixed(3))}
              height={280}
            />
            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead className="border-b border-border bg-surface-2 text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">Configuration</th>
                      <th className="px-3 py-2.5 text-right font-medium">nDCG@10</th>
                      <th className="px-3 py-2.5 text-right font-medium">Recall@100</th>
                      <th className="px-3 py-2.5 text-right font-medium">Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {BEIR_SCIFACT.map((row) => {
                      const best = row.ndcg10 === Math.max(...BEIR_SCIFACT.map((r) => r.ndcg10))
                      return (
                        <tr key={row.config}>
                          <td className="px-4 py-2.5">{row.config}</td>
                          <td className={cn('px-3 py-2.5 text-right tabular-nums', best && 'font-semibold text-success')}>
                            {row.ndcg10.toFixed(4)}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{row.recall100.toFixed(4)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{row.latency}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <div className="space-y-2 border-t border-border p-4 text-[12.5px] leading-relaxed text-muted-foreground">
                <p>
                  <strong className="text-foreground">Transparency note:</strong> the MS MARCO cross-encoder{' '}
                  <em>lowered</em> nDCG@10 on SciFact (0.7235 → 0.6995). It was trained on web search queries; SciFact
                  queries are scientific claims. That is why Relevance Optimization is a toggle to validate per corpus.
                </p>
                <p>* Rerank latency was measured while other workloads shared the CPU, so it is an upper bound.</p>
              </div>
            </Card>
          </div>
          <Card className="mt-6 p-5">
            <p className="text-sm font-semibold">Northwind sample (3 documents, 18 questions, through the live API)</p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Configuration</th>
                    <th className="px-3 py-2 text-right font-medium">P@1</th>
                    <th className="px-3 py-2 text-right font-medium">Recall@5</th>
                    <th className="px-3 py-2 text-right font-medium">MRR</th>
                    <th className="px-3 py-2 text-right font-medium">nDCG@10</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {NORTHWIND.map((row) => (
                    <tr key={row.config}>
                      <td className="py-2 pr-4">{row.config}</td>
                      {[row.p1, row.recall5, row.mrr, row.ndcg10].map((v, i) => (
                        <td key={i} className="px-3 py-2 text-right tabular-nums">
                          {v.toFixed(3)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[12px] text-muted-foreground">
              The corpus is deliberately small, so differences are small and noisy; SciFact above is the meaningful benchmark.
            </p>
          </Card>
        </Section>

        {/* Engineering & security */}
        <Section
          id="security"
          eyebrow="Engineering & security"
          title="Secure by construction"
          className="bg-surface-2/50"
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ['Workspace isolation', 'PostgreSQL Row-Level Security on every tenant table, enforced through a non-superuser database role and tested against a real database.'],
              ['Sessions', 'Argon2id passwords, in-memory access tokens, rotating httpOnly SameSite=Strict refresh cookies with reuse detection.'],
              ['Access control', 'Four roles plus document- and collection-level permissions, checked on every endpoint; denied access is audited.'],
              ['Prompt-injection defenses', 'Document text is fenced and labelled as data; instruction-like passages are flagged in the evidence panel.'],
              ['Upload safety', 'Type and size validation, content sniffing, de-duplication and per-workspace storage paths.'],
              ['Operability', 'Rate limits, correlation IDs, structured logs, Prometheus metrics, OpenTelemetry traces and an audit log.'],
            ].map(([title, body]) => (
              <Card key={title} className="p-5">
                <p className="text-sm font-semibold">{title}</p>
                <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{body}</p>
              </Card>
            ))}
          </div>
        </Section>

        {/* Testing */}
        <Section
          id="testing"
          eyebrow="Testing & validation"
          title="Verified, with the numbers recorded"
          intro={`Results from the most recent full run on ${TEST_RESULTS.date}. Backend tests run against real PostgreSQL 16 + pgvector with RLS enforced.`}
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {TEST_RESULTS.items.map((t) => (
              <Card key={t.label} className="p-5">
                <p className="text-3xl font-semibold tabular-nums">{t.value}</p>
                <p className="mt-1 text-sm font-medium">{t.label}</p>
                <p className="mt-1 text-[12px] text-muted-foreground">{t.detail}</p>
              </Card>
            ))}
          </div>
        </Section>

        {/* Challenges */}
        <Section id="challenges" eyebrow="Challenges & decisions" title="What was hard, and what we chose" className="bg-surface-2/50">
          <div className="grid gap-4 md:grid-cols-2">
            {CHALLENGES.map((c) => (
              <Card key={c.title} className="p-5">
                <p className="text-[15px] font-semibold">{c.title}</p>
                <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
                  <span className="font-medium text-foreground">Problem. </span>
                  {c.problem}
                </p>
                <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
                  <span className="font-medium text-foreground">Decision. </span>
                  {c.decision}
                </p>
              </Card>
            ))}
          </div>
        </Section>

        {/* Tech stack */}
        <Section id="stack" eyebrow="Technology" title="Tech stack" intro="Only what the repository actually uses.">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {TECH_STACK.map((group) => (
              <Card key={group.group} className="p-5">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{group.group}</p>
                <ul className="mt-3 space-y-2.5">
                  {group.items.map((item) => (
                    <li key={item.name}>
                      <p className="text-[13.5px] font-medium">{item.name}</p>
                      <p className="text-[12px] text-muted-foreground">{item.use}</p>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        </Section>

        {/* Gallery */}
        <Section
          id="gallery"
          eyebrow="Product gallery"
          title="Screens from the running product"
          intro="Captured from the app with the fictional Northwind sample documents. No mock-ups."
          className="bg-surface-2/50"
        >
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {GALLERY.map((shot) => (
              <button
                key={shot.file}
                type="button"
                onClick={() => setZoomed(shot)}
                className="group cursor-zoom-in text-left"
                aria-label={`Enlarge screenshot: ${shot.title}`}
              >
                <div className="overflow-hidden rounded-xl border border-border bg-surface transition-shadow group-hover:shadow-[0_12px_32px_-16px_rgb(16_24_40/0.3)]">
                  <img src={`/case-study/${shot.file}`} alt={`${shot.title}: ${shot.caption}`} loading="lazy" className="block w-full" width={1440} height={900} />
                </div>
                <p className="mt-2.5 text-sm font-medium">{shot.title}</p>
                <p className="text-[12.5px] text-muted-foreground">{shot.caption}</p>
              </button>
            ))}
          </div>
        </Section>

        {/* Docs */}
        <Section id="docs" eyebrow="Documentation" title="Read the details">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {DOCS.map((doc) => (
              <a
                key={doc.path}
                href={docUrl(doc.path)}
                target="_blank"
                rel="noreferrer"
                className="group flex items-start gap-3 rounded-xl border border-border bg-surface p-4 transition-colors hover:border-primary/40"
              >
                <BookOpen className="mt-0.5 size-4 shrink-0 text-primary" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1 text-sm font-medium">
                    {doc.title} <ExternalLink className="size-3 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                  </span>
                  <span className="block text-[12.5px] text-muted-foreground">{doc.body}</span>
                </span>
              </a>
            ))}
          </div>
        </Section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-8 text-xs text-muted-foreground sm:flex-row sm:px-6">
          <Logo />
          <p>Search Smarter. Retrieve Precisely. Trust Every Answer.</p>
          <div className="flex gap-4">
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-foreground">
              GitHub
            </a>
            <Link to={productLink} className="hover:text-foreground">
              Product
            </Link>
            <Link to="/" className="hover:text-foreground">
              Home
            </Link>
          </div>
        </div>
      </footer>

      <Dialog open={!!zoomed} onOpenChange={(open) => !open && setZoomed(null)}>
        <DialogContent title={zoomed?.title ?? ''} description={zoomed?.caption} className="max-w-6xl">
          {zoomed && <img src={`/case-study/${zoomed.file}`} alt={`${zoomed.title}: ${zoomed.caption}`} className="w-full rounded-lg border border-border" />}
          <Button variant="ghost" size="sm" className="sr-only" onClick={() => setZoomed(null)}>
            <X /> Close
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}
