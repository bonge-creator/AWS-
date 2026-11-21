"""Admin routes — user management and the audit trail."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.core.errors import NotFoundError, ValidationError
from app.core.security import hash_password
from app.db.models.audit import AuditLog
from app.db.models.document import Document
from app.db.models.user import User
from app.db.session import get_db_session
from app.modules.auth.schemas import UserCreateRequest, UserOut, UserUpdateRequest
from app.modules.auth.service import create_user
from app.shared.audit import record_audit

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class AuditOut(BaseModel):
    id: uuid.UUID
    actor_user_id: Optional[uuid.UUID] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[uuid.UUID] = None
    ip: Optional[str] = None
    meta: Optional[dict] = None
    created_at: Optional[str] = None


class UserListOut(BaseModel):
    items: list[UserOut]
    total: int


class StatsOut(BaseModel):
    users: int
    documents: int
    ready_documents: int
    conversations: int
    citations: int


@router.get("/users", response_model=UserListOut)
async def list_users(
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    total = await session.scalar(select(func.count()).select_from(User))
    rows = (
        await session.execute(
            select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return UserListOut(items=[UserOut.of(u) for u in rows], total=int(total or 0))


@router.post("/users", response_model=UserOut, status_code=201)
async def add_user(
    payload: UserCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    user = await create_user(
        session,
        email=payload.email,
        display_name=payload.display_name,
        password=payload.password,
        role=payload.role,
        actor_id=admin.id,
    )
    await session.commit()
    return UserOut.of(user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    await session.flush()
    await record_audit(
        session,
        actor_id=admin.id,
        action="user.update",
        resource_type="user",
        resource_id=user.id,
        metadata={"fields": payload.model_dump(exclude_none=True, exclude={"password"})},
    )
    await session.commit()
    return UserOut.of(user)


@router.delete("/users/{user_id}", status_code=204)
async def deactivate_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    if user.id == admin.id:
        raise ValidationError("You cannot deactivate your own account")
    user.is_active = False
    await record_audit(
        session,
        actor_id=admin.id,
        action="user.deactivate",
        resource_type="user",
        resource_id=user.id,
    )
    await session.commit()


@router.get("/audit", response_model=list[AuditOut])
async def audit_logs(
    limit: int = Query(default=100, le=500),
    action: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        AuditOut(
            id=r.id,
            actor_user_id=r.actor_user_id,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            ip=r.ip,
            meta=r.meta,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


@router.get("/stats", response_model=StatsOut)
async def stats(
    session: AsyncSession = Depends(get_db_session),
    admin=Depends(require_admin),
):
    from app.db.models.citation import Citation
    from app.db.models.conversation import Conversation

    async def count(model) -> int:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)

    return StatsOut(
        users=await count(User),
        documents=await count(Document),
        ready_documents=int(
            await session.scalar(
                select(func.count()).select_from(Document).where(Document.status == "ready")
            )
            or 0
        ),
        conversations=await count(Conversation),
        citations=await count(Citation),
    )
