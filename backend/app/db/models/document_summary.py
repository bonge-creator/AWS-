"""Per-document cached summary (map-reduce)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import tstz, utcnow

if TYPE_CHECKING:
    from app.db.models.document import Document


class DocumentSummary(Base):
    __tablename__ = "document_summaries"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), unique=True, nullable=False)
    summary = Column(Text, nullable=False)
    model = Column(Text, nullable=False)
    prompt_version = Column(Text, nullable=False, default="v1")
    generated_at = Column(tstz(), nullable=False, default=utcnow)

    document = relationship("Document", back_populates="summaries")
