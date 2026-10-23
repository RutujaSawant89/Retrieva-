"""Evaluation dataset parsing and validation.

Accepted formats:

* JSON — ``{"items": [...]}`` or a bare list of items
* JSONL — one item per line
* CSV — columns ``question``, ``relevant_passages`` (``||``-separated), ``reference_answer``,
  ``relevant_documents`` (``||``-separated titles)

Item fields: ``question`` (required), ``relevant_passages`` (exact or near-exact snippets from the
documents that answer the question), ``relevant_documents`` (document titles, for document-level
relevance), ``reference_answer`` (for context recall). At least one relevance target is required.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.core.errors import ValidationFailedError

MAX_ITEMS = 1000


def _split(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split("||") if part.strip()]


def normalize_items(raw_items: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationFailedError("The dataset must contain at least one item")
    if len(raw_items) > MAX_ITEMS:
        raise ValidationFailedError(f"Datasets are limited to {MAX_ITEMS} items")
    items: list[dict[str, Any]] = []
    problems: list[str] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            problems.append(f"item {index}: must be an object")
            continue
        question = str(raw.get("question", "")).strip()
        passages = _split(raw.get("relevant_passages"))
        documents = _split(raw.get("relevant_documents"))
        reference = str(raw.get("reference_answer") or "").strip() or None
        if not question:
            problems.append(f"item {index}: question is required")
            continue
        if not passages and not documents:
            problems.append(f"item {index}: provide relevant_passages or relevant_documents")
            continue
        items.append(
            {
                "question": question[:2000],
                "relevant_passages": [p[:2000] for p in passages[:20]],
                "relevant_documents": [d[:500] for d in documents[:20]],
                "reference_answer": reference[:4000] if reference else None,
            }
        )
    if problems:
        raise ValidationFailedError("The dataset has invalid items", details={"problems": problems[:50]})
    return items


def parse_dataset_file(filename: str, data: bytes) -> list[dict[str, Any]]:
    text = data.decode("utf-8-sig", errors="replace")
    lower = filename.lower()
    try:
        if lower.endswith(".jsonl"):
            raw = [json.loads(line) for line in text.splitlines() if line.strip()]
        elif lower.endswith(".json"):
            parsed = json.loads(text)
            raw = parsed.get("items", []) if isinstance(parsed, dict) else parsed
        elif lower.endswith(".csv"):
            raw = list(csv.DictReader(io.StringIO(text)))
        else:
            raise ValidationFailedError("Dataset files must be .json, .jsonl or .csv")
    except (json.JSONDecodeError, csv.Error) as exc:
        raise ValidationFailedError(f"Could not parse the dataset: {exc}") from exc
    return normalize_items(raw)
