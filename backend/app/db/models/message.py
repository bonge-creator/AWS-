"""A single chat message plus its persisted citations + retrieval evidence."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.enums import message_role
from app.db.types import tstz, utcnow

if TYPE_CHECKING:
    from app.db.models.citation import Citation
    from app.db.models.conversation import Conversation
    from app.db.models.evidence import RetrievalEvidence


class Message(Base):
    __tablename__ = "messages"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(message_role(), nullable=False)
    content = Column(Text, nullable=False)
    # For assistant messages: False means the model abstained ("not in the archive").
    answer_found = Column(Boolean, nullable=True)
    created_at = Column(tstz(), nullable=False, default=utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    citations = relationship("Citation", back_populates="message", cascade="all, delete-orphan", passive_deletes=True)
    evidence = relationship("RetrievalEvidence", back_populates="message", cascade="all, delete-orphan", passive_deletes=True)
