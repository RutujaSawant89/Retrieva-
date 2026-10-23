"""Text analysis for sparse retrieval: tokenization, stop words, Snowball stemming.

The same analyzer is used for indexing and querying, which is what makes BM25 term matching
consistent. Numbers and alphanumeric identifiers (e.g. ``AES-256``, ``ISO27001``) are kept
because exact terminology matching is BM25's main advantage over dense retrieval.
"""

from __future__ import annotations

import re
from functools import lru_cache

import snowballstemmer

_TOKEN = re.compile(r"[a-z0-9]+(?:[.'][a-z0-9]+)*", re.UNICODE)

STOP_WORDS = frozenset(
    """
    a about above after again against all am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further had
    has have having he her here hers herself him himself his how i if in into is it its itself just
    me more most my myself no nor not now of off on once only or other our ours ourselves out over
    own same she should so some such than that the their theirs them themselves then there these
    they this those through to too under until up very was we were what when where which while who
    whom why will with would you your yours yourself yourselves also may might must shall within
    upon whether
    """.split()  # noqa: SIM905
)

_stemmer = snowballstemmer.stemmer("english")


@lru_cache(maxsize=200_000)
def _stem(token: str) -> str:
    return _stemmer.stemWord(token)


def analyze(text: str, *, keep_stop_words: bool = False) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    out: list[str] = []
    for token in tokens:
        token = token.replace("'", "")
        if not keep_stop_words and token in STOP_WORDS:
            continue
        if len(token) == 1 and not token.isdigit():
            continue
        # Short tokens are usually acronyms (AES, SLA, KPI) and identifiers: keep them verbatim.
        out.append(token if len(token) <= 3 or any(c.isdigit() for c in token) else _stem(token))
    return out


def content_words(text: str) -> set[str]:
    """Stemmed non-stop-word terms; used for lexical support and overlap measures."""
    return set(analyze(text))
