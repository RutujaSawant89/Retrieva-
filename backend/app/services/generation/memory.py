"""Controlled conversational memory.

Only the current conversation's own messages are ever used (conversations are scoped to one
user and organization). Recent turns are passed verbatim; older turns are folded into a
running summary so the context window stays bounded.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message, MessageRole
from app.services.generation.providers import ChatMessage, LLMError, get_llm

logger = logging.getLogger(__name__)

RECENT_TURNS = 6  # messages passed verbatim
SUMMARIZE_AFTER = 10  # messages before a summary is (re)built
MAX_SUMMARY_CHARS = 1500


def title_from(question: str) -> str:
    title = " ".join(question.split())
    return (title[:77] + "…") if len(title) > 80 else title or "New conversation"


def recent_turns(
    db: Session, conversation: Conversation, exclude_message_id: uuid.UUID | None = None
) -> list[tuple[str, str]]:
    stmt = (
        select(Message.role, Message.content, Message.status)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(RECENT_TURNS + 1)
    )
    if exclude_message_id is not None:
        stmt = stmt.where(Message.id != exclude_message_id)
    rows = list(reversed(db.execute(stmt).all()))
    turns = []
    for role, content, status in rows:
        if role == MessageRole.ASSISTANT and status != "answered":
            continue  # abstentions and errors carry no facts worth remembering
        turns.append((role.value, content))
    return turns[-RECENT_TURNS:]


def _extractive_summary(messages: list[tuple[str, str]]) -> str:
    questions = [text for role, text in messages if role == "user"]
    lines = [f"- Asked: {q[:160]}" for q in questions[-8:]]
    return "Earlier questions in this conversation:\n" + "\n".join(lines)


def maybe_summarize(db: Session, conversation: Conversation) -> None:
    count = db.scalar(select(func.count()).where(Message.conversation_id == conversation.id)) or 0
    if count < SUMMARIZE_AFTER or count - conversation.summary_message_count < SUMMARIZE_AFTER // 2:
        return
    rows = db.execute(
        select(Message.role, Message.content)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
        .limit(max(0, count - RECENT_TURNS))
    ).all()
    older = [(r.value, c) for r, c in rows]
    summary = None
    llm = get_llm()
    if llm is not None:
        transcript = "\n".join(f"{role.upper()}: {text[:500]}" for role, text in older[-20:])
        try:
            summary, _ = llm.complete(
                [
                    ChatMessage(
                        "system",
                        "Summarize this conversation in at most 8 bullet points: the questions asked, the key "
                        "facts established, and open threads. Only include facts stated in the conversation.",
                    ),
                    ChatMessage("user", transcript),
                ],
                max_tokens=300,
            )
        except LLMError:
            logger.warning("summary_failed", exc_info=True)
    conversation.summary = (summary or _extractive_summary(older))[:MAX_SUMMARY_CHARS]
    conversation.summary_message_count = count
