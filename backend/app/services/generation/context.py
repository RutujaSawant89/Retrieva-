"""Context assembly: select, label and budget the evidence passed to the LLM.

Every passage keeps a traceable label (``S1``…) that maps to exactly one chunk. Passages are
added in relevance order until the token budget is reached. Passages from different documents
that discuss the same topic but state different figures are flagged as potential conflicts.
Retrieved text is treated as untrusted: instruction-like content is detected and reported, and
passages are wrapped so they cannot close the source envelope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations

from app.services.retrieval.analyzer import content_words
from app.services.retrieval.types import Evidence
from app.services.text import approx_token_count

_NUMBER = re.compile(
    r"(?<![\w.])(?:[$€£]\s?)?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![\w.])(?:[$€£]\s?)?\d+(?:\.\d+)?%?"
)
_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|rules)"
    r"|you\s+are\s+now\s+|new\s+instructions?\s*:|system\s+prompt|<\s*/?\s*(system|source|instructions?)\s*>"
    r"|reveal\s+(your|the)\s+(prompt|instructions|system)|act\s+as\s+(an?\s+)?(admin|developer|system)",
    re.I,
)
TOPIC_OVERLAP_FOR_CONFLICT = 0.35


@dataclass
class Conflict:
    labels: tuple[str, str]
    reason: str


@dataclass
class AssembledContext:
    items: list[Evidence]
    dropped_for_budget: int = 0
    token_estimate: int = 0
    conflicts: list[Conflict] = field(default_factory=list)
    suspicious_labels: list[str] = field(default_factory=list)

    def by_label(self) -> dict[str, Evidence]:
        return {item.label: item for item in self.items}


def normalize_number(raw: str) -> str:
    return raw.replace(",", "").replace(" ", "").lstrip("$€£").rstrip("%")


def numbers_in(text: str) -> set[str]:
    return {normalize_number(m) for m in _NUMBER.findall(text)}


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def location(item: Evidence) -> str:
    parts = []
    if item.page_number:
        parts.append(
            f"p. {item.page_number}"
            if item.page_end in (None, item.page_number)
            else f"pp. {item.page_number}–{item.page_end}"
        )
    if item.section:
        parts.append(item.section)
    return ", ".join(parts)


def _escape(text: str) -> str:
    return re.sub(r"<\s*/?\s*source[^>]*>", "[removed tag]", text, flags=re.I)


def detect_conflicts(items: list[Evidence]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    words = {item.label: content_words(item.text) for item in items}
    nums = {item.label: numbers_in(item.text) for item in items}
    for a, b in combinations(items, 2):
        if a.document_id == b.document_id:
            continue
        wa, wb = words[a.label], words[b.label]
        if not wa or not wb:
            continue
        overlap = len(wa & wb) / min(len(wa), len(wb))
        if overlap < TOPIC_OVERLAP_FOR_CONFLICT:
            continue
        only_a, only_b = nums[a.label] - nums[b.label], nums[b.label] - nums[a.label]
        if only_a and only_b:
            conflicts.append(
                Conflict(
                    labels=(a.label, b.label),
                    reason=f"Sources discuss the same topic but state different figures "
                    f"({', '.join(sorted(only_a)[:3])} vs {', '.join(sorted(only_b)[:3])})",
                )
            )
    return conflicts


def assemble(evidence: list[Evidence], token_budget: int) -> AssembledContext:
    items: list[Evidence] = []
    used = 0
    dropped = 0
    for item in evidence:
        cost = approx_token_count(item.text) + 30  # envelope + metadata
        if items and used + cost > token_budget:
            dropped += 1
            continue
        items.append(item)
        used += cost
    for i, item in enumerate(items, start=1):
        item.label = f"S{i}"
    return AssembledContext(
        items=items,
        dropped_for_budget=dropped,
        token_estimate=used,
        conflicts=detect_conflicts(items),
        suspicious_labels=[item.label for item in items if looks_like_injection(item.text)],
    )


def render_sources(context: AssembledContext) -> str:
    blocks = []
    for item in context.items:
        attrs = f'id="{item.label}" document="{_escape(item.document_title)}"'
        loc = location(item)
        if loc:
            attrs += f' location="{_escape(loc)}"'
        blocks.append(f"<source {attrs}>\n{_escape(item.text)}\n</source>")
    return "\n\n".join(blocks)
