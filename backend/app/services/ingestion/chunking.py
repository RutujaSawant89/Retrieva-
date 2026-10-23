"""Chunking strategies.

All strategies consume the structural blocks of an ``ExtractedDocument`` and produce ``Chunk``
objects that keep page ranges, heading paths and character offsets into the document's
``full_text`` — the information citations need to point back at the source.

* ``recursive`` — character budget, splitting on progressively finer separators.
* ``token``     — token budget with token overlap (uses the embedding model's tokenizer).
* ``semantic``  — sentence embeddings; split where adjacent-sentence similarity drops.
* ``structure`` — never crosses section boundaries; packs whole blocks, splits oversized ones.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from app.services.ingestion.types import Block, Chunk, ExtractedDocument
from app.services.text import approx_token_count, split_sentences

Strategy = Literal["recursive", "token", "semantic", "structure"]
TokenCounter = Callable[[str], int]
SentenceEmbedder = Callable[[list[str]], np.ndarray]

DEFAULT_SEPARATORS = ("\n\n", "\n", ". ", "; ", ", ", " ")


@dataclass
class ChunkingConfig:
    strategy: Strategy = "structure"
    chunk_size: int = 900  # characters (recursive / structure / semantic cap)
    chunk_overlap: int = 150  # characters (recursive) — token strategy uses token_overlap
    max_tokens: int = 256  # hard cap for every strategy (embedding model context)
    token_overlap: int = 32
    separators: Sequence[str] = field(default_factory=lambda: DEFAULT_SEPARATORS)
    semantic_breakpoint_percentile: float = 20.0  # split at the lowest-similarity 20% gaps
    min_chunk_chars: int = 120

    def validate(self) -> None:
        if self.chunk_size < 100:
            raise ValueError("chunk_size must be at least 100 characters")
        if not 0 <= self.chunk_overlap < self.chunk_size // 2:
            raise ValueError("chunk_overlap must be >= 0 and less than half of chunk_size")
        if self.max_tokens < 32:
            raise ValueError("max_tokens must be at least 32")
        if not 0 <= self.token_overlap < self.max_tokens // 2:
            raise ValueError("token_overlap must be less than half of max_tokens")


@dataclass
class _Span:
    """A piece of text with its source location, used while assembling chunks."""

    text: str
    start: int
    end: int
    page: int | None
    heading_path: list[str]


def _spans_from_blocks(blocks: list[Block]) -> list[_Span]:
    return [_Span(b.text, b.start, b.end, b.page, b.heading_path) for b in blocks if b.kind != "heading"]


def _make_chunk(
    spans: list[_Span], index: int, count: TokenCounter, joiner: str = "\n\n", source: str | None = None
) -> Chunk:
    """Build a chunk from consecutive spans.

    With ``source`` (the document's full text) the chunk text is sliced from the original, which
    preserves the exact separators between fine-grained pieces.
    """
    if source is not None:
        text = source[spans[0].start : spans[-1].end].strip()
    else:
        text = joiner.join(s.text for s in spans).strip()
    pages = [s.page for s in spans if s.page is not None]
    return Chunk(
        text=text,
        index=index,
        token_count=count(text),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        heading_path=list(spans[0].heading_path),
        start=spans[0].start,
        end=spans[-1].end,
    )


def _split_text(text: str, size: int, separators: Sequence[str]) -> list[str]:
    """Recursively split ``text`` into pieces no longer than ``size`` characters."""
    if len(text) <= size:
        return [text]
    for i, sep in enumerate(separators):
        if sep not in text:
            continue
        parts = text.split(sep)
        out: list[str] = []
        current = ""
        for j, part in enumerate(parts):
            piece = part + (sep if j < len(parts) - 1 else "")
            if len(current) + len(piece) <= size:
                current += piece
                continue
            if current:
                out.append(current)
            if len(piece) > size:
                out.extend(_split_text(piece, size, separators[i + 1 :]))
                current = ""
            else:
                current = piece
        if current:
            out.append(current)
        return [p for p in out if p.strip()]
    return [text[k : k + size] for k in range(0, len(text), size)]


def _sub_spans(span: _Span, pieces: list[str]) -> list[_Span]:
    """Locate split pieces inside ``span`` so offsets stay exact."""
    out: list[_Span] = []
    cursor = 0
    for piece in pieces:
        stripped = piece.strip()
        if not stripped:
            continue
        found = span.text.find(stripped, cursor)
        if found < 0:
            found = cursor
        out.append(
            _Span(
                stripped, span.start + found, span.start + found + len(stripped), span.page, span.heading_path
            )
        )
        cursor = found + len(stripped)
    return out


def _enforce_token_cap(chunks: list[Chunk], cfg: ChunkingConfig, count: TokenCounter) -> list[Chunk]:
    """Split any chunk that exceeds the model token budget (embedding models truncate silently)."""
    out: list[Chunk] = []
    for chunk in chunks:
        if chunk.token_count <= cfg.max_tokens:
            out.append(chunk)
            continue
        ratio = cfg.max_tokens / max(1, chunk.token_count)
        size = max(100, int(len(chunk.text) * ratio * 0.95))
        span = _Span(chunk.text, chunk.start, chunk.end, chunk.page_start, chunk.heading_path)
        for sub in _sub_spans(span, _split_text(chunk.text, size, cfg.separators)):
            piece = Chunk(
                text=sub.text,
                index=0,
                token_count=count(sub.text),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                heading_path=chunk.heading_path,
                start=sub.start,
                end=sub.end,
            )
            out.extend(
                _enforce_token_cap([piece], cfg, count) if piece.token_count > cfg.max_tokens else [piece]
            )
    for i, chunk in enumerate(out):
        chunk.index = i
    return out


# --------------------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------------------


def chunk_recursive(doc: ExtractedDocument, cfg: ChunkingConfig, count: TokenCounter) -> list[Chunk]:
    # Split into units smaller than the overlap so whole units can be carried between chunks.
    unit = max(60, min(cfg.chunk_size // 3, cfg.chunk_overlap or cfg.chunk_size // 3))
    spans: list[_Span] = []
    for span in _spans_from_blocks(doc.blocks):
        spans.extend(_sub_spans(span, _split_text(span.text, unit, cfg.separators)))
    chunks: list[Chunk] = []
    window: list[_Span] = []
    length = 0
    for span in spans:
        if window and length + len(span.text) > cfg.chunk_size:
            chunks.append(_make_chunk(window, len(chunks), count, source=doc.full_text))
            # Carry trailing spans forward as overlap.
            carry: list[_Span] = []
            carried = 0
            for prev in reversed(window):
                if carried + len(prev.text) > cfg.chunk_overlap:
                    break
                carry.insert(0, prev)
                carried += len(prev.text)
            window, length = carry, carried
        window.append(span)
        length += len(span.text)
    if window:
        chunks.append(_make_chunk(window, len(chunks), count, source=doc.full_text))
    return chunks


def chunk_token(doc: ExtractedDocument, cfg: ChunkingConfig, count: TokenCounter) -> list[Chunk]:
    """Pack sentences into windows of ``max_tokens`` with ``token_overlap`` tokens of overlap."""
    sentences: list[_Span] = []
    for span in _spans_from_blocks(doc.blocks):
        sentences.extend(_sub_spans(span, split_sentences(span.text)))
    chunks: list[Chunk] = []
    window: list[_Span] = []
    tokens = 0
    for sent in sentences:
        n = count(sent.text)
        if window and tokens + n > cfg.max_tokens:
            chunks.append(_make_chunk(window, len(chunks), count, source=doc.full_text))
            carry: list[_Span] = []
            carried = 0
            for prev in reversed(window):
                m = count(prev.text)
                if carried + m > cfg.token_overlap:
                    break
                carry.insert(0, prev)
                carried += m
            window, tokens = carry, carried
        window.append(sent)
        tokens += n
    if window:
        chunks.append(_make_chunk(window, len(chunks), count, source=doc.full_text))
    return chunks


def chunk_semantic(
    doc: ExtractedDocument, cfg: ChunkingConfig, count: TokenCounter, embed: SentenceEmbedder | None
) -> list[Chunk]:
    """Greg Kamradt-style semantic chunking: break where neighbouring sentences diverge."""
    if embed is None:
        raise ValueError("semantic chunking requires a sentence embedder")
    sentences: list[_Span] = []
    for span in _spans_from_blocks(doc.blocks):
        sentences.extend(_sub_spans(span, split_sentences(span.text)))
    if len(sentences) <= 2:
        return [_make_chunk(sentences, 0, count, joiner=" ")] if sentences else []

    # Embed each sentence with a little neighbouring context to smooth noise.
    windows = [" ".join(s.text for s in sentences[max(0, i - 1) : i + 2]) for i in range(len(sentences))]
    vectors = embed(windows)
    vectors = vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9, None)
    similarity = np.sum(vectors[:-1] * vectors[1:], axis=1)
    threshold = float(np.percentile(similarity, cfg.semantic_breakpoint_percentile))

    chunks: list[Chunk] = []
    window: list[_Span] = [sentences[0]]
    length = len(sentences[0].text)
    for i in range(1, len(sentences)):
        sent = sentences[i]
        section_changed = sent.heading_path != window[-1].heading_path
        boundary = similarity[i - 1] <= threshold and length >= cfg.min_chunk_chars
        if section_changed or boundary or length + len(sent.text) > cfg.chunk_size:
            chunks.append(_make_chunk(window, len(chunks), count, joiner=" "))
            window, length = [], 0
        window.append(sent)
        length += len(sent.text)
    if window:
        chunks.append(_make_chunk(window, len(chunks), count, joiner=" "))
    return chunks


def chunk_structure(doc: ExtractedDocument, cfg: ChunkingConfig, count: TokenCounter) -> list[Chunk]:
    """Pack whole blocks within a section; split only blocks that exceed the budget.

    Small trailing sections are merged forward only within the same parent heading, so a
    chunk never mixes unrelated sections.
    """
    sections: list[list[_Span]] = []
    for span in _spans_from_blocks(doc.blocks):
        if sections and sections[-1][-1].heading_path == span.heading_path:
            sections[-1].append(span)
        else:
            sections.append([span])

    chunks: list[Chunk] = []
    for section in sections:
        window: list[_Span] = []
        length = 0
        for span in section:
            pieces = (
                [span]
                if len(span.text) <= cfg.chunk_size
                else _sub_spans(span, _split_text(span.text, cfg.chunk_size, cfg.separators))
            )
            for piece in pieces:
                if window and length + len(piece.text) > cfg.chunk_size:
                    chunks.append(_make_chunk(window, len(chunks), count))
                    window, length = [], 0
                window.append(piece)
                length += len(piece.text) + 2
        if window:
            chunks.append(_make_chunk(window, len(chunks), count))

    # Merge tiny chunks into the previous chunk of the same parent section. A merged chunk
    # spans sibling sections, so its heading path becomes their common parent and each part
    # keeps its own heading inline — the citation location must never name only one of them.
    merged: list[Chunk] = []
    for chunk in chunks:
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and len(chunk.text) < cfg.min_chunk_chars
            and prev.heading_path[:-1] == chunk.heading_path[:-1]
            and len(prev.text) + len(chunk.text) <= cfg.chunk_size * 1.25
        ):
            if prev.heading_path != chunk.heading_path and chunk.heading_path:
                sections = list(prev.metadata.get("sections") or prev.heading_path[-1:])
                if "sections" not in prev.metadata and prev.heading_path:
                    prev.text = f"{prev.heading_path[-1]}\n{prev.text}"
                sections.append(chunk.heading_path[-1])
                prev.metadata["sections"] = sections
                prev.heading_path = chunk.heading_path[:-1]
                prev.text = f"{prev.text}\n\n{chunk.heading_path[-1]}\n{chunk.text}"
            else:
                prev.text = f"{prev.text}\n\n{chunk.text}"
            prev.end = chunk.end
            prev.token_count = count(prev.text)
            if chunk.page_end is not None:
                prev.page_end = max(prev.page_end or chunk.page_end, chunk.page_end)
                prev.page_start = prev.page_start or chunk.page_start
            continue
        merged.append(chunk)
    for i, chunk in enumerate(merged):
        chunk.index = i
    return merged


def chunk_document(
    doc: ExtractedDocument,
    cfg: ChunkingConfig,
    count: TokenCounter = approx_token_count,
    embed: SentenceEmbedder | None = None,
) -> list[Chunk]:
    cfg.validate()
    if not doc.full_text:
        doc.finalize()
    if cfg.strategy == "recursive":
        chunks = chunk_recursive(doc, cfg, count)
    elif cfg.strategy == "token":
        chunks = chunk_token(doc, cfg, count)
    elif cfg.strategy == "semantic":
        chunks = chunk_semantic(doc, cfg, count, embed)
    elif cfg.strategy == "structure":
        chunks = chunk_structure(doc, cfg, count)
    else:  # pragma: no cover - guarded by the Literal type and API validation
        raise ValueError(f"Unknown chunking strategy: {cfg.strategy}")
    chunks = [c for c in chunks if c.text.strip()]
    return _enforce_token_cap(chunks, cfg, count)
