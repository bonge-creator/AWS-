"""Chunk-level passage — the unit of retrieval + embedding."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, Column, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import Vector

if TYPE_CHECKING:
    from app.db.models.document import Document


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    heading_path = Column(ARRAY(Text), nullable=False, default=list)
    embedding = Column(Vector(1024), nullable=False)
    # Provenance: vectors from different models are not comparable, so retrieval filters on this.
    embedding_model = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document = relationship("Document", back_populates="chunks")
