"""Provenance: which chunk/document a message cites, with page references."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.message import Message


class Citation(Base):
    __tablename__ = "citations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_id = Column(PG_UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False)
    ordinal = Column(Integer, nullable=False)  # the [n] marker used in the answer text
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    quote = Column(Text, nullable=True)
    score = Column(Float, nullable=True)

    __table_args__ = (UniqueConstraint("message_id", "chunk_id", name="uq_citation_message_chunk"),)

    message = relationship("Message", back_populates="citations")
