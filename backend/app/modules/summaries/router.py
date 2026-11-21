"""Summary routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.models.document_summary import DocumentSummary
from app.db.session import get_db_session
from app.modules.documents.permissions import can_access_document
from app.modules.summaries.service import summarise_document
from app.shared.audit import record_audit

router = APIRouter(prefix="/api/v1/summaries", tags=["summaries"])


class SummaryOut(BaseModel):
    document_id: uuid.UUID
    summary: str
    model: str
    prompt_version: str
    generated_at: Optional[str] = None


@router.get("/{document_id}", response_model=SummaryOut)
async def get_summary(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    if not await can_access_document(session, user, document_id, need="view"):
        from app.core.errors import ForbiddenError

        raise ForbiddenError("You do not have access to this document")
    row = (
        await session.execute(
            select(DocumentSummary).where(DocumentSummary.document_id == document_id)
        )
    ).scalar_one_or_none()
    if row is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("No summary has been generated for this document yet")
    return SummaryOut(
        document_id=row.document_id,
        summary=row.summary,
        model=row.model,
        prompt_version=row.prompt_version,
        generated_at=row.generated_at.isoformat() if row.generated_at else None,
    )


@router.post("/{document_id}", response_model=SummaryOut)
async def create_summary(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    summary = await summarise_document(session, user, document_id)
    await record_audit(
        session,
        actor_id=user.id,
        action="summary.generate",
        resource_type="document",
        resource_id=document_id,
    )
    await session.commit()
    return SummaryOut(
        document_id=summary.document_id,
        summary=summary.summary,
        model=summary.model,
        prompt_version=summary.prompt_version,
        generated_at=summary.generated_at.isoformat() if summary.generated_at else None,
    )
