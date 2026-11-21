"""Retrieval evidence — audit trail of every chunk that reached the prompt."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import tstz, utcnow

if TYPE_CHECKING:
    from app.db.models.chunk import DocumentChunk
    from app.db.models.message import Message


class RetrievalEvidence(Base):
    __tablename__ = "retrieval_evidence"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(PG_UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False)
    rank = Column(Integer, nullable=False)
    score = Column(Float, nullable=False)
    token_count = Column(Integer, nullable=False)
    created_at = Column(tstz(), nullable=False, default=utcnow)

    message = relationship("Message", back_populates="evidence")
    chunk = relationship("DocumentChunk")
