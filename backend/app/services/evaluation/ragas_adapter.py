"""Optional RAGAS integration.

RAGAS metrics need an LLM judge. When ``ragas`` is installed (``uv sync --extra ragas``) and an
OpenAI-compatible provider is configured, the standard RAGAS metrics are computed over the
run's generated answers and stored next to Retrieva's own metrics. Otherwise the run records why
RAGAS was skipped — no placeholder numbers are ever produced.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def ragas_scores(records: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    settings = get_settings()
    try:
        import ragas  # noqa: F401
    except ImportError:
        return {"status": "unavailable", "reason": "ragas is not installed (uv sync --extra ragas)"}
    if settings.llm_provider != "openai" or not settings.llm_model:
        return {
            "status": "unavailable",
            "reason": "RAGAS needs an OpenAI-compatible LLM_PROVIDER as the judge",
        }

    rows = [
        {
            "user_input": item["question"],
            "response": outcome["answer"],
            "retrieved_contexts": [r["excerpt"] for r in outcome["retrieved"]],
            "reference": item.get("reference_answer") or "",
        }
        for item, outcome in records
        if outcome.get("answer")
    ]
    if not rows:
        return {"status": "unavailable", "reason": "no generated answers to score"}
    try:
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas import EvaluationDataset, evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
            ResponseRelevancy,
        )

        llm = LangchainLLMWrapper(
            ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.llm_api_key or "none",
                base_url=settings.llm_base_url,
            )
        )
        embeddings = LangchainEmbeddingsWrapper(
            OpenAIEmbeddings(api_key=settings.llm_api_key or "none", base_url=settings.llm_base_url)
        )
        metrics = [Faithfulness(), ResponseRelevancy()]
        if all(r["reference"] for r in rows):
            metrics += [LLMContextPrecisionWithReference(), LLMContextRecall()]
        result = evaluate(EvaluationDataset.from_list(rows), metrics=metrics, llm=llm, embeddings=embeddings)
        frame = result.to_pandas()
        scores = {
            column: round(float(frame[column].mean()), 4)
            for column in frame.columns
            if column not in ("user_input", "response", "retrieved_contexts", "reference")
        }
        return {"status": "completed", "samples": len(rows), "scores": scores}
    except Exception as exc:  # RAGAS APIs change often; report instead of failing the run
        logger.warning("ragas_failed", exc_info=True)
        return {"status": "failed", "reason": f"{exc.__class__.__name__}: {exc}"[:500]}
