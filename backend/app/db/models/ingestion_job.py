"""Ingestion pipeline state."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.enums import job_status
from app.db.types import tstz

if TYPE_CHECKING:
    from app.db.models.document import Document


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(job_status(), nullable=False, default="queued")
    stage = Column(Text, nullable=True)
    progress = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    started_at = Column(tstz(), nullable=True)
    finished_at = Column(tstz(), nullable=True)

    document = relationship("Document", back_populates="ingestion_jobs")
