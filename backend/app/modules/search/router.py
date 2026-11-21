"""Semantic search endpoint — same permission boundary as the assistant."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db_session
from app.modules.retrieval.service import search
from app.ports.factory import get_embedder
from app.shared.audit import record_audit

router = APIRouter(prefix="/api/v1/search", tags=["search"])


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    doc_type: Optional[str] = None
    page_start: int
    page_end: int
    score: float
    excerpt: str


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]
    count: int


@router.get("", response_model=SearchOut)
async def semantic_search(
    q: str = Query(min_length=2),
    top_k: int = Query(default=10, le=50),
    doc_type: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    embedder = get_embedder()
    vector = (await embedder.embed([q]))[0]
    chunks = await search(
        session,
        user,
        vector,
        embedding_model=embedder.model_id,
        top_k=top_k,
        min_score=settings.min_score,
        doc_type=doc_type,
    )
    await record_audit(
        session,
        actor_id=user.id,
        action="search.query",
        resource_type="query",
        metadata={"query": q[:200], "hits": len(chunks)},
    )
    await session.commit()
    return SearchOut(
        query=q,
        count=len(chunks),
        hits=[
            SearchHit(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                filename=c.filename,
                doc_type=c.doc_type,
                page_start=c.page_start,
                page_end=c.page_end,
                score=round(c.score, 4),
                excerpt=" ".join(c.text.split())[:400],
            )
            for c in chunks
        ],
    )
