"""Document upload, listing, preview and download."""

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document
from app.db.models.user import User
from app.modules.documents.permissions import can_access_document, permission_filter
from app.ports.factory import get_storage

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def build_key(document_id: uuid.UUID, filename: str) -> str:
    """Opaque but identifiable key: originals are never served by raw filename."""
    safe = _SAFE_NAME.sub("_", filename).strip("._") or "document"
    return f"documents/{document_id}/{safe}"


async def upload_document(
    session: AsyncSession,
    *,
    user: User,
    filename: str,
    content_type: str,
    body: bytes,
) -> Document:
    """Validate and store an uploaded file, returning the pending document."""
    if not filename:
        raise ValidationError("A filename is required")
    if content_type not in settings.allowed_mime_types_list:
        raise ValidationError(
            f"Unsupported file type '{content_type}'. Allowed: "
            + ", ".join(settings.allowed_mime_types_list)
        )
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(body) == 0:
        raise ValidationError("The uploaded file is empty")
    if len(body) > max_bytes:
        raise ValidationError(f"File exceeds the {settings.max_upload_mb} MB limit")

    document_id = uuid.uuid4()
    key = build_key(document_id, filename)
    checksum = hashlib.sha256(body).hexdigest()

    storage = get_storage()
    await storage.put_object(
        key, body, content_type, metadata={"filename": filename, "uploaded_by": str(user.id)}
    )

    document = Document(
        id=document_id,
        s3_key=key,
        filename=filename,
        content_type=content_type,
        byte_size=len(body),
        checksum_sha256=checksum,
        status="uploaded",
        uploaded_by=user.id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(document)
    await session.flush()
    return document


async def get_document_for_read(
    session: AsyncSession, user: User, document_id: uuid.UUID
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found")
    if not await can_access_document(session, user, document_id, need="view"):
        raise ForbiddenError("You do not have access to this document")
    return document


async def list_documents(
    session: AsyncSession,
    user: User,
    *,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Document], int]:
    """List only the documents the user may read."""
    conditions = list(permission_filter(user))
    if doc_type:
        conditions.append(Document.doc_type == doc_type)
    if status:
        conditions.append(Document.status == status)
    if search:
        conditions.append(Document.filename.ilike(f"%{search}%"))

    total = await session.scalar(select(func.count()).select_from(Document).where(*conditions))
    stmt = (
        select(Document)
        .where(*conditions)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def document_chunks(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentChunk]:
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_download_url(
    session: AsyncSession, user: User, document_id: uuid.UUID
) -> tuple[str, int]:
    """Permission-checked download. Returns (url, expires_in_seconds)."""
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found")
    if not await can_access_document(session, user, document_id, need="download"):
        raise ForbiddenError("You do not have permission to download this document")
    storage = get_storage()
    expires = 60
    url = await storage.generate_presigned_url(document.s3_key, expires_in=expires)
    return url, expires


async def delete_document(session: AsyncSession, user: User, document_id: uuid.UUID) -> None:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found")
    if user.role != "admin" and not await can_access_document(
        session, user, document_id, need="manage"
    ):
        raise ForbiddenError("You do not have permission to delete this document")
    await session.delete(document)
    await session.flush()
