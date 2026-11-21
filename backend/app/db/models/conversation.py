"""Conversation — owned by one user; holds message history."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import tstz, utcnow

if TYPE_CHECKING:
    from app.db.models.message import Message


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(Text, nullable=True)
    created_at = Column(tstz(), nullable=False, default=utcnow)

    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan",
        passive_deletes=True, order_by="Message.created_at",
    )
