"""Text cleaning that removes extraction artifacts while preserving structure.

Paragraph breaks (blank lines) and line breaks are kept because the structure-aware chunker
relies on them; only noise is removed.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from app.services.ingestion.types import Block

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​‌‍﻿]")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_SPACES = re.compile(r"[ \t ]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")
_PAGE_NUMBER_LINE = re.compile(r"^\s*(?:page\s+)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?\s*$", re.I)
_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}


def normalize_text(text: str) -> str:
    """Unicode-normalise, drop control characters, re-join hyphenated line breaks."""
    for ligature, replacement in _LIGATURES.items():
        text = text.replace(ligature, replacement)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _MANY_NEWLINES.sub("\n\n", "\n".join(lines)).strip()


def strip_page_furniture(pages: list[str], min_pages: int = 3, threshold: float = 0.6) -> list[str]:
    """Remove running headers/footers and bare page numbers from paginated text.

    A line counts as furniture when it (ignoring digits) appears in the first/last two lines
    of at least ``threshold`` of the pages.
    """
    if len(pages) < min_pages:
        return [_drop_page_numbers(p) for p in pages]

    def key(line: str) -> str:
        return re.sub(r"\d+", "#", line.strip().lower())

    def edge_indices(non_empty: list[int]) -> list[int]:
        # Short pages only have one header/footer line candidate each; otherwise two.
        depth = 2 if len(non_empty) >= 6 else 1
        return non_empty[:depth] + non_empty[-depth:]

    edge_counts: Counter[str] = Counter()
    for page in pages:
        lines = page.split("\n")
        non_empty = [i for i, ln in enumerate(lines) if ln.strip()]
        edge_counts.update({key(lines[i]) for i in edge_indices(non_empty)})
    furniture = {k for k, count in edge_counts.items() if k and count >= threshold * len(pages)}

    cleaned = []
    for page in pages:
        lines = page.split("\n")
        non_empty = [i for i, ln in enumerate(lines) if ln.strip()]
        edge_idx = set(edge_indices(non_empty))
        kept = [ln for i, ln in enumerate(lines) if not (i in edge_idx and key(ln) in furniture)]
        cleaned.append(_drop_page_numbers("\n".join(kept)))
    return cleaned


def _drop_page_numbers(page: str) -> str:
    return "\n".join(ln for ln in page.split("\n") if not _PAGE_NUMBER_LINE.match(ln))


def clean_blocks(blocks: list[Block]) -> list[Block]:
    """Normalise block text and drop empty or duplicate-adjacent blocks."""
    cleaned: list[Block] = []
    for block in blocks:
        if block.kind in ("code", "table"):
            text = _CONTROL.sub("", unicodedata.normalize("NFKC", block.text)).strip("\n")
        else:
            text = normalize_text(block.text)
        if not text:
            continue
        if cleaned and cleaned[-1].text == text and cleaned[-1].kind == block.kind:
            continue
        block.text = text
        cleaned.append(block)
    return cleaned
