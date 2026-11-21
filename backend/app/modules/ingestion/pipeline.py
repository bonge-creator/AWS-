"""Ingestion pipeline — extract, chunk, classify, embed, persist.

Runs as a background task after upload. Each stage records its progress on the
ingestion job so the UI can show where a document is.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document
from app.db.models.ingestion_job import IngestionJob
from app.modules.ingestion.chunking import chunk_pages
from app.modules.ingestion.metadata import extract_metadata
from app.ports.factory import get_embedder, get_extractor, get_storage

STAGES = ["extract", "chunk", "classify", "embed", "persist", "complete"]


async def _set_stage(session: AsyncSession, job: IngestionJob, stage: str, progress: int):
    job.stage = stage
    job.progress = progress
    job.status = "running"
    job.started_at = job.started_at or datetime.now(timezone.utc)
    await session.flush()


async def ingest_document(session: AsyncSession, document_id: uuid.UUID) -> None:
    """Process one document end to end. Safe to re-run: chunks are replaced."""
    document = await session.get(Document, document_id)
    if document is None:
        return

    result = await session.execute(
        select(IngestionJob)
        .where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.id.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        job = IngestionJob(id=uuid.uuid4(), document_id=document_id, status="queued")
        session.add(job)
        await session.flush()

    document.status = "processing"
    try:
        await _set_stage(session, job, "extract", 10)

        storage = get_storage()
        extractor = get_extractor()
        raw = await storage.get_object(document.s3_key)
        extraction = await extractor.extract(raw, document.filename, document.content_type)

        await _set_stage(session, job, "chunk", 30)
        chunks = chunk_pages(extraction.pages)
        if not chunks:
            raise ValueError("No extractable text found in the document")

        await _set_stage(session, job, "classify", 45)
        metadata = extract_metadata(extraction.text, document.filename)
        document.doc_type = metadata.doc_type
        document.title = metadata.title or document.title
        document.expiry_date = metadata.expiry_date
        document.classification_confidence = metadata.confidence
        document.extracted_metadata = metadata.as_dict()
        document.page_count = extraction.page_count

        await _set_stage(session, job, "embed", 60)
        embedder = get_embedder()
        vectors = await embedder.embed([c.text for c in chunks])

        await _set_stage(session, job, "persist", 85)
        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        for chunk, vector in zip(chunks, vectors):
            session.add(
                DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    heading_path=chunk.heading_path,
                    embedding=vector,
                    embedding_model=embedder.model_id,
                )
            )

        document.status = "ready"
        document.indexed_at = datetime.now(timezone.utc)
        job.status = "succeeded"
        job.stage = "complete"
        job.progress = 100
        job.finished_at = datetime.now(timezone.utc)
        await session.commit()

    except Exception as exc:  # noqa: BLE001 - job status must record any failure
        document.status = "failed"
        job.status = "failed"
        job.error = f"{type(exc).__name__}: {exc}"
        job.finished_at = datetime.now(timezone.utc)
        await session.commit()
        raise
