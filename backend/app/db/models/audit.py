"""Audit trail: security-relevant events (auth, access, retrieval, admin changes)."""

import uuid

from sqlalchemy import Column, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from app.db.base import Base
from app.db.types import tstz, utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(Text, nullable=False)
    resource_type = Column(Text, nullable=True)
    resource_id = Column(PG_UUID(as_uuid=True), nullable=True)
    ip = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)
    # `metadata` is reserved on declarative classes, so the attribute is `meta`.
    meta = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(tstz(), nullable=False, default=utcnow)

    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_actor", "actor_user_id"),
    )
