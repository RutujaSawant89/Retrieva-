"""Evidence and citation verification.

Runs independently of the generator, after generation. For each answer it:

1. splits the answer into claims (sentences) and extracts their citation labels;
2. validates each label against the context actually given to the model (fabricated or
   out-of-range labels are *invalid*);
3. scores whether each cited passage supports its claim (lexical precision of the claim's
   content words in the passage + best sentence-level embedding similarity, or an NLI model
   when configured), and checks that every number in the claim appears in a cited passage;
4. validates page references written in the answer against the cited passages' pages;
5. aggregates: citation validity, citation precision, evidence coverage, unsupported claims.

These are heuristic verifiers with known limits (documented in docs/EVALUATION.md); they are
reported as verification signals, never as model confidence.
"""

from __future__ import annotations

import re
import threading
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.core.config import get_settings
from app.services.embeddings.service import EmbeddingService
from app.services.generation.context import AssembledContext, numbers_in
from app.services.retrieval.analyzer import content_words
from app.services.retrieval.types import Evidence
from app.services.text import split_sentences

DEFAULT_LABEL_PATTERN = r"S\d+"


@lru_cache
def _patterns(label: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    group = re.compile(rf"\[((?:{label})(?:\s*[,;]\s*(?:{label}))*)\]")
    return group, re.compile(label)


def _label_key(label: str) -> tuple[str, int]:
    match = re.match(r"([A-Za-z]*)(\d+)", label)
    return (match.group(1), int(match.group(2))) if match else (label, 0)


_PAGE_REF = re.compile(r"\b(?:page|p\.)\s*(\d{1,4})\b", re.I)
_MARKDOWN_PREFIX = re.compile(r"^\s*(?:[-*+]|\d+[.)]|#{1,6}|>)\s*")

SUPPORTED = 0.55
PARTIAL = 0.35
MIN_CLAIM_WORDS = 3


class SupportScorer(Protocol):
    name: str

    def score(self, claim: str, passages: list[Evidence]) -> list[float]: ...


class HybridSupportScorer:
    """Lexical precision of the claim in the passage, blended with semantic similarity."""

    name = "lexical+embedding"

    def __init__(self, embedder: EmbeddingService | None) -> None:
        self.embedder = embedder

    def score(self, claim: str, passages: list[Evidence]) -> list[float]:
        claim_words = content_words(claim)
        out = []
        claim_vec = self.embedder.embed_query(claim) if self.embedder else None
        for passage in passages:
            words = content_words(passage.content)
            lexical = len(claim_words & words) / max(1, len(claim_words))
            if claim_vec is None:
                out.append(lexical)
                continue
            sentences = split_sentences(passage.content) or [passage.content]
            vectors = self.embedder.embed_documents(sentences)  # type: ignore[union-attr]
            semantic = float(np.clip(np.max(vectors @ claim_vec), 0.0, 1.0))
            out.append(0.5 * lexical + 0.5 * semantic)
        return out


class NLISupportScorer:
    """Entailment probability from an NLI cross-encoder (e.g. cross-encoder/nli-deberta-v3-xsmall)."""

    def __init__(self, model_name: str) -> None:
        self.name = f"nli:{model_name}"
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def score(self, claim: str, passages: list[Evidence]) -> list[float]:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import CrossEncoder

                    self._model = CrossEncoder(self.model_name, device="cpu")
        logits = np.asarray(
            self._model.predict([(p.content, claim) for p in passages], show_progress_bar=False)
        )
        if logits.ndim == 1:
            return [float(1 / (1 + np.exp(-x))) for x in logits]
        probs = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = probs / probs.sum(axis=1, keepdims=True)
        labels = [str(x).lower() for x in getattr(self._model.model.config, "id2label", {}).values()]
        entail = labels.index("entailment") if "entailment" in labels else 1
        return [float(p[entail]) for p in probs]


@dataclass
class ClaimCheck:
    text: str
    citations: list[str]
    valid_citations: list[str]
    invalid_citations: list[str]
    support: dict[str, float]
    best_support: float
    status: str  # supported | partial | unsupported | uncited
    missing_numbers: list[str] = field(default_factory=list)
    page_issues: list[str] = field(default_factory=list)


@dataclass
class VerificationReport:
    scorer: str
    claims: list[ClaimCheck]
    total_citations: int
    valid_citations: int
    invalid_labels: list[str]
    citation_validity: float | None  # valid / all citations
    citation_precision: float | None  # supporting citations / valid citations
    evidence_coverage: float | None  # supported claims / factual claims
    unsupported_claims: list[str]
    cited_labels: list[str]
    supporting_labels: list[str]
    page_reference_issues: list[str]
    low_support: bool

    def to_dict(self) -> dict:
        return asdict(self)


def strip_citations(text: str, label_pattern: str = DEFAULT_LABEL_PATTERN) -> str:
    return _patterns(label_pattern)[0].sub("", text).strip()


def extract_claims(answer: str, label_pattern: str = DEFAULT_LABEL_PATTERN) -> list[tuple[str, list[str]]]:
    citation_group, label_re = _patterns(label_pattern)
    claims: list[tuple[str, list[str]]] = []
    for line in answer.split("\n"):
        line = _MARKDOWN_PREFIX.sub("", line).strip()
        if not line or set(line) <= set("|-: "):
            continue
        for sentence in split_sentences(line):
            labels: list[str] = []
            for group in citation_group.findall(sentence):
                labels.extend(label_re.findall(group))
            claims.append((sentence, list(dict.fromkeys(labels))))
    # A citation at the start of the next sentence fragment (e.g. "...days. [S1]") attaches back.
    merged: list[tuple[str, list[str]]] = []
    for sentence, labels in claims:
        if merged and not content_words(strip_citations(sentence, label_pattern)) and labels:
            prev_sentence, prev_labels = merged[-1]
            merged[-1] = (f"{prev_sentence} {sentence}", list(dict.fromkeys(prev_labels + labels)))
        else:
            merged.append((sentence, labels))
    return merged


def _page_ok(page: int, item: Evidence) -> bool:
    if item.page_number is None:
        return False
    return item.page_number <= page <= (item.page_end or item.page_number)


class CitationVerifier:
    def __init__(self, scorer: SupportScorer, label_pattern: str = DEFAULT_LABEL_PATTERN) -> None:
        self.scorer = scorer
        self.label_pattern = label_pattern

    def verify(self, answer: str, context: AssembledContext) -> VerificationReport:
        by_label = context.by_label()
        claims: list[ClaimCheck] = []
        invalid_all: list[str] = []
        page_issues_all: list[str] = []
        total = valid = supporting = 0
        cited: set[str] = set()
        supporting_labels: set[str] = set()

        for sentence, labels in extract_claims(answer, self.label_pattern):
            claim_text = strip_citations(sentence, self.label_pattern)
            words = content_words(claim_text)
            valid_labels = [lbl for lbl in labels if lbl in by_label]
            invalid_labels = [lbl for lbl in labels if lbl not in by_label]
            invalid_all.extend(invalid_labels)
            total += len(labels)
            valid += len(valid_labels)
            cited.update(valid_labels)

            if len(words) < MIN_CLAIM_WORDS and not labels:
                continue  # connective text such as "In summary:" is not a factual claim

            passages = [by_label[lbl] for lbl in valid_labels]
            support = (
                dict(zip(valid_labels, self.scorer.score(claim_text, passages), strict=True))
                if passages
                else {}
            )
            claim_numbers = numbers_in(claim_text)
            cited_numbers = set().union(*(numbers_in(p.content) for p in passages)) if passages else set()
            missing = sorted(
                n
                for n in claim_numbers
                if n not in cited_numbers and len(n) > 0 and not _is_label_number(n, labels)
            )

            page_issues = []
            for page_ref in _PAGE_REF.findall(claim_text):
                if passages and not any(_page_ok(int(page_ref), p) for p in passages):
                    page_issues.append(f"page {page_ref} is not a page of the cited source(s)")
            page_issues_all.extend(page_issues)

            best = max(support.values(), default=0.0)
            if not labels:
                status = "uncited"
            elif not valid_labels:
                status = "unsupported"
            elif missing or page_issues:
                status = "unsupported" if best < SUPPORTED else "partial"
            elif best >= SUPPORTED:
                status = "supported"
            elif best >= PARTIAL:
                status = "partial"
            else:
                status = "unsupported"
            for lbl, value in support.items():
                if value >= PARTIAL:
                    supporting += 1
                    supporting_labels.add(lbl)
            claims.append(
                ClaimCheck(
                    text=claim_text,
                    citations=labels,
                    valid_citations=valid_labels,
                    invalid_citations=invalid_labels,
                    support={k: round(v, 3) for k, v in support.items()},
                    best_support=round(best, 3),
                    status=status,
                    missing_numbers=missing,
                    page_issues=page_issues,
                )
            )

        factual = [c for c in claims if len(content_words(c.text)) >= MIN_CLAIM_WORDS]
        supported_claims = [c for c in factual if c.status == "supported"]
        coverage = len(supported_claims) / len(factual) if factual else None
        report = VerificationReport(
            scorer=self.scorer.name,
            claims=claims,
            total_citations=total,
            valid_citations=valid,
            invalid_labels=sorted(set(invalid_all)),
            citation_validity=round(valid / total, 4) if total else None,
            citation_precision=round(supporting / valid, 4) if valid else None,
            evidence_coverage=round(coverage, 4) if coverage is not None else None,
            unsupported_claims=[c.text for c in factual if c.status in ("unsupported", "uncited")],
            cited_labels=sorted(cited, key=_label_key),
            supporting_labels=sorted(supporting_labels, key=_label_key),
            page_reference_issues=page_issues_all,
            low_support=coverage is not None and coverage < 0.5,
        )
        return report


def _is_label_number(number: str, labels: list[str]) -> bool:
    return any(number == str(_label_key(lbl)[1]) for lbl in labels)


@lru_cache
def get_support_scorer() -> SupportScorer:
    from app.services.embeddings.service import get_embedding_service

    model = get_settings().verifier_nli_model
    if model:
        return NLISupportScorer(model)
    return HybridSupportScorer(get_embedding_service())


def get_verifier() -> CitationVerifier:
    return CitationVerifier(get_support_scorer())
