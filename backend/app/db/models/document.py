"""Document metadata + extracted metadata."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Column, Date, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.enums import doc_type_enum, document_status
from app.db.types import tstz, utcnow

if TYPE_CHECKING:
    from app.db.models.chunk import DocumentChunk
    from app.db.models.document_summary import DocumentSummary
    from app.db.models.ingestion_job import IngestionJob
    from app.db.models.permission import DocumentPermission


class Document(Base):
    __tablename__ = "documents"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    s3_key = Column(Text, unique=True, nullable=False)
    filename = Column(Text, nullable=False)
    content_type = Column(Text, nullable=False)
    byte_size = Column(BigInteger, nullable=False)
    checksum_sha256 = Column(Text, nullable=False)
    status = Column(document_status(), nullable=False, default="uploaded")
    doc_type = Column(doc_type_enum(), nullable=True, index=True)
    title = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)
    classification_confidence = Column(Float, nullable=True)
    extracted_metadata = Column(JSONB, nullable=True)
    expiry_date = Column(Date, nullable=True, index=True)
    uploaded_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(tstz(), nullable=False, default=utcnow)
    indexed_at = Column(tstz(), nullable=True)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
    permissions = relationship("DocumentPermission", back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
    ingestion_jobs = relationship("IngestionJob", back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
    summaries = relationship("DocumentSummary", back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
