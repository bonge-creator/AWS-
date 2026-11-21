"""Audit logging helper — thin wrapper for consistent event recording."""

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog


async def record_audit(
    session: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    metadata: Optional[dict] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    log = AuditLog(
        actor_user_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip=ip,
        user_agent=user_agent,
        meta=metadata or {},
    )
    session.add(log)
    await session.flush()