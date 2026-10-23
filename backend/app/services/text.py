"""Shared text utilities: sentence splitting and approximate token counting."""

from __future__ import annotations

import re

_ABBREVIATIONS = {
    "e.g",
    "i.e",
    "etc",
    "vs",
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "inc",
    "ltd",
    "co",
    "corp",
    "fig",
    "no",
    "sec",
    "art",
    "approx",
    "u.s",
    "u.k",
    "st",
    "jr",
    "sr",
    "dept",
    "est",
    "al",
}
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, keeping common abbreviations and decimals intact."""
    text = text.strip()
    if not text:
        return []
    pieces: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        candidate = text[start : match.start()].rstrip()
        last_word = candidate.rsplit(None, 1)[-1].rstrip(".!?\"')]").lower() if candidate else ""
        if last_word in _ABBREVIATIONS or (len(last_word) == 1 and last_word.isalpha()):
            continue
        pieces.append(text[start : match.end()].strip())
        start = match.end()
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    # Lines within lists/tables are sentence-like units too.
    out: list[str] = []
    for piece in pieces:
        out.extend(part.strip() for part in piece.split("\n") if part.strip())
    return out


def approx_token_count(text: str) -> int:
    """Word-piece-like token estimate: words and punctuation, long words count extra."""
    count = 0
    for token in _TOKEN.findall(text):
        count += 1 + max(0, (len(token) - 1) // 8)
    return count
