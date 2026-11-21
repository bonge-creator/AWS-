"""Chat routes — synchronous answers and SSE streaming."""

import asyncio
import json
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models.conversation import Conversation
from app.db.models.citation import Citation
from app.db.models.message import Message
from app.db.session import get_db_session
from app.modules.chat.service import (
    ABSTENTION_TEXT,
    SYSTEM_PROMPT,
    answer_question,
    build_context,
    plan_greeting,
    plan_keyword,
    plan_metadata_query,
    _extract_citation_indices,
)
from app.modules.documents.permissions import permission_filter
from app.modules.retrieval.service import search
from app.ports.factory import get_embedder, get_llm
from app.ports.llm import NO_ANSWER
from app.shared.audit import record_audit

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class AskRequest(BaseModel):
    question: str
    conversation_id: Optional[uuid.UUID] = None


class CitationOut(BaseModel):
    index: int
    document_id: uuid.UUID
    filename: str
    page_start: int
    page_end: int
    quote: str
    score: Optional[float] = None


class AnswerOut(BaseModel):
    answer: str
    found: bool
    citations: list[CitationOut] = []
    intent: str = "semantic"
    model: str = ""
    conversation_id: Optional[uuid.UUID] = None
    message_id: Optional[uuid.UUID] = None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    answer_found: Optional[bool] = None
    created_at: Optional[str] = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: Optional[str] = None
    created_at: Optional[str] = None


@router.post("/ask", response_model=AnswerOut)
async def ask(
    payload: AskRequest,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    result = await answer_question(
        session, user, payload.question, conversation_id=payload.conversation_id
    )
    conversation_id = payload.conversation_id
    if conversation_id is None and result.message_id is not None:
        conversation_id = await session.scalar(
            select(Message.conversation_id).where(Message.id == result.message_id)
        )
    return AnswerOut(
        answer=result.text,
        found=result.found,
        citations=[
            CitationOut(
                index=c.index,
                document_id=c.document_id,
                filename=c.filename,
                page_start=c.page_start,
                page_end=c.page_end,
                quote=c.quote,
                score=c.score,
            )
            for c in result.citations
        ],
        intent=result.intent,
        model=result.model,
        conversation_id=conversation_id,
        message_id=result.message_id,
    )


@router.post("/stream")
async def stream(
    payload: AskRequest,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    """Server-sent events: evidence, answer deltas, citations, done."""
    return StreamingResponse(
        _event_stream(session, user, payload.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _event_stream(
    session: AsyncSession, user, question: str
) -> AsyncIterator[str]:
    question = (question or "").strip()
    if not question:
        yield await _sse("error", {"message": "A question is required"})
        return

    # Deterministic paths — answered without a model call.
    greeting_plan = plan_greeting(question)
    if greeting_plan:
        result = await answer_question(session, user, question, persist=True)
        yield await _sse(
            "evidence",
            {
                "intent": result.intent,
                "found": result.found,
                "passages": [
                    {
                        "index": c.index,
                        "document_id": str(c.document_id),
                        "filename": c.filename,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "quote": c.quote,
                    }
                    for c in result.citations
                ],
            },
        )
        yield await _sse("delta", {"text": result.text})
        yield await _sse(
            "citations",
            {
                "citations": [
                    {
                        "index": c.index,
                        "document_id": str(c.document_id),
                        "filename": c.filename,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "quote": c.quote,
                    }
                    for c in result.citations
                ]
            },
        )
        yield await _sse("done", {"found": result.found, "intent": result.intent})
        return

    # Deterministic metadata path — answered without a model call.
    plan = plan_metadata_query(question)
    if plan:
        result = await answer_question(session, user, question, persist=True)
        yield await _sse(
            "evidence",
            {
                "intent": result.intent,
                "found": result.found,
                "passages": [
                    {
                        "index": c.index,
                        "document_id": str(c.document_id),
                        "filename": c.filename,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "quote": c.quote,
                    }
                    for c in result.citations
                ],
            },
        )
        yield await _sse("delta", {"text": result.text})
        yield await _sse(
            "citations",
            {
                "citations": [
                    {
                        "index": c.index,
                        "document_id": str(c.document_id),
                        "filename": c.filename,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "quote": c.quote,
                    }
                    for c in result.citations
                ]
            },
        )
        yield await _sse("done", {"found": result.found, "intent": result.intent})
        return

    # Keyword search — deterministic ILIKE across all accessible documents.
    keyword_plan = plan_keyword(question)
    if keyword_plan:
        result = await answer_question(session, user, question, persist=True)
        yield await _sse(
            "evidence",
            {
                "intent": result.intent,
                "found": result.found,
                "passages": [
                    {
                        "index": c.index,
                        "document_id": str(c.document_id),
                        "filename": c.filename,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "quote": c.quote,
                    }
                    for c in result.citations
                ],
            },
        )
        yield await _sse("delta", {"text": result.text})
        yield await _sse(
            "citations",
            {
                "citations": [
                    {
                        "index": c.index,
                        "document_id": str(c.document_id),
                        "filename": c.filename,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "quote": c.quote,
                    }
                    for c in result.citations
                ]
            },
        )
        yield await _sse("done", {"found": result.found, "intent": result.intent})
        return

    embedder = get_embedder()
    query_vector = (await embedder.embed([question]))[0]
    chunks = await search(
        session,
        user,
        query_vector,
        embedding_model=embedder.model_id,
        top_k=settings.top_k,
        min_score=settings.min_score,
    )

    if not chunks:
        yield await _sse("evidence", {"intent": "semantic", "found": False, "passages": []})
        yield await _sse("delta", {"text": ABSTENTION_TEXT})
        yield await _sse("citations", {"citations": []})
        yield await _sse("done", {"found": False, "intent": "semantic"})
        await record_audit(
            session,
            actor_id=user.id,
            action="chat.answer",
            resource_type="conversation",
            metadata={"intent": "semantic", "found": False, "streamed": True},
        )
        await session.commit()
        return

    yield await _sse(
        "evidence",
        {
            "intent": "semantic",
            "found": True,
            "passages": [
                {
                    "index": i,
                    "document_id": str(c.document_id),
                    "filename": c.filename,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "score": round(c.score, 4),
                }
                for i, c in enumerate(chunks, start=1)
            ],
        },
    )

    llm = get_llm()
    context = build_context(chunks)
    collected: list[str] = []
    try:
        async for token in llm.generate_stream(SYSTEM_PROMPT, context, question):
            collected.append(token)
            yield await _sse("delta", {"text": token})
    except Exception as exc:  # noqa: BLE001 - stream must close cleanly
        yield await _sse("error", {"message": f"Generation failed: {exc}"})
        await session.rollback()
        return

    answer = "".join(collected).strip()
    if not answer or answer == NO_ANSWER or NO_ANSWER in answer[:20]:
        answer = ABSTENTION_TEXT
        found = False
        used: list[int] = []
    else:
        used = sorted(
            {i for i in _extract_citation_indices(answer) if 1 <= i <= len(chunks)}
        )
        found = bool(used)

    citations = [
        {
            "index": i,
            "document_id": str(chunks[i - 1].document_id),
            "filename": chunks[i - 1].filename,
            "page_start": chunks[i - 1].page_start,
            "page_end": chunks[i - 1].page_end,
            "quote": " ".join(chunks[i - 1].text.split())[:320],
            "score": round(chunks[i - 1].score, 4),
        }
        for i in used
    ]
    yield await _sse("citations", {"citations": citations})

    await record_audit(
        session,
        actor_id=user.id,
        action="chat.answer",
        resource_type="conversation",
        metadata={"intent": "semantic", "found": found, "citations": len(citations), "streamed": True},
    )
    await session.commit()
    yield await _sse("done", {"found": found, "intent": "semantic"})


@router.get("/conversations", response_model=list[ConversationOut])
async def conversations(
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
        .limit(100)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        ConversationOut(
            id=c.id,
            title=c.title,
            created_at=c.created_at.isoformat() if c.created_at else None,
        )
        for c in rows
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def conversation_messages(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        return []
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            answer_found=m.answer_found,
            created_at=m.created_at.isoformat() if m.created_at else None,
        )
        for m in rows
    ]
