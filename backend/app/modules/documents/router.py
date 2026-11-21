"""Document routes — upload, list, preview, download, permissions."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.errors import ForbiddenError, NotFoundError
from app.db.models.document import Document
from app.db.session import get_db_session
from app.modules.documents import service
from app.modules.documents.permissions import (
    can_access_document,
    grant,
    list_permissions,
    revoke,
)
from app.ports.factory import get_job_runner, get_storage
from app.shared.audit import record_audit

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    title: Optional[str] = None
    content_type: str
    byte_size: int
    status: str
    doc_type: Optional[str] = None
    expiry_date: Optional[str] = None
    classification_confidence: Optional[float] = None
    page_count: Optional[int] = None
    uploaded_by: Optional[uuid.UUID] = None
    created_at: Optional[str] = None
    indexed_at: Optional[str] = None
    extracted_metadata: Optional[dict] = None

    @classmethod
    def of(cls, doc) -> "DocumentOut":
        return cls(
            id=doc.id,
            filename=doc.filename,
            title=doc.title,
            content_type=doc.content_type,
            byte_size=doc.byte_size,
            status=doc.status,
            doc_type=doc.doc_type,
            expiry_date=doc.expiry_date.isoformat() if doc.expiry_date else None,
            classification_confidence=doc.classification_confidence,
            page_count=doc.page_count,
            uploaded_by=doc.uploaded_by,
            created_at=doc.created_at.isoformat() if doc.created_at else None,
            indexed_at=doc.indexed_at.isoformat() if doc.indexed_at else None,
            extracted_metadata=doc.extracted_metadata,
        )


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int


class PermissionOut(BaseModel):
    id: uuid.UUID
    grantee_type: str
    grantee_user_id: Optional[uuid.UUID] = None
    grantee_role: Optional[str] = None
    permission: str
    granted_by: Optional[uuid.UUID] = None
    granted_at: Optional[str] = None


class GrantRequest(BaseModel):
    grantee_type: str  # "user" | "role"
    permission: str  # "view" | "download" | "manage"
    grantee_user_id: Optional[uuid.UUID] = None
    grantee_role: Optional[str] = None


class RevokeRequest(BaseModel):
    grantee_type: str
    permission: str
    grantee_user_id: Optional[uuid.UUID] = None
    grantee_role: Optional[str] = None


class DownloadOut(BaseModel):
    url: str
    expires_in: int


@router.post("", response_model=DocumentOut, status_code=201)
async def upload(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    body = await file.read()
    document = await service.upload_document(
        session,
        user=user,
        filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        body=body,
    )
    await record_audit(
        session,
        actor_id=user.id,
        action="document.upload",
        resource_type="document",
        resource_id=document.id,
        metadata={"filename": document.filename, "bytes": document.byte_size},
    )
    await session.commit()

    # Ingestion runs in the background; the document becomes searchable shortly.
    from app.modules.ingestion.pipeline import ingest_document
    from app.db.session import async_session

    async def _run() -> None:
        async with async_session() as bg:
            try:
                await ingest_document(bg, document.id)
            except Exception:  # noqa: BLE001 - failure is recorded on the job
                pass

    get_job_runner().schedule(_run)
    return DocumentOut.of(document)


@router.get("", response_model=DocumentListOut)
async def list_all(
    doc_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    docs, total = await service.list_documents(
        session, user, doc_type=doc_type, status=status, search=search, limit=limit, offset=offset
    )
    return DocumentListOut(items=[DocumentOut.of(d) for d in docs], total=total)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_one(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    document = await service.get_document_for_read(session, user, document_id)
    return DocumentOut.of(document)


@router.get("/{document_id}/preview")
async def preview(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    """The extracted text of the document, page by page."""
    document = await service.get_document_for_read(session, user, document_id)
    chunks = await service.document_chunks(session, document_id)
    return {
        "id": str(document.id),
        "filename": document.filename,
        "doc_type": document.doc_type,
        "expiry_date": document.expiry_date.isoformat() if document.expiry_date else None,
        "status": document.status,
        "pages": [
            {
                "chunk_index": c.chunk_index,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "text": c.text,
            }
            for c in chunks
        ],
    }


@router.get("/{document_id}/download", response_model=DownloadOut)
async def download(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    url, expires = await service.get_download_url(session, user, document_id)
    await record_audit(
        session,
        actor_id=user.id,
        action="document.download",
        resource_type="document",
        resource_id=document_id,
    )
    await session.commit()
    return DownloadOut(url=url, expires_in=expires)


@router.get("/raw")
async def raw_object(
    key: str = Query(min_length=1),
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    """Serve the stored original for the local storage backend.

    The local adapter's "presigned URL" points back here because there is no
    object store to sign against. The key is never trusted on its own: it is
    resolved to a document and the caller's download permission is re-checked
    before a single byte is returned.
    """
    stmt = select(Document).where(Document.s3_key == key)
    document = (await session.execute(stmt)).scalar_one_or_none()
    if document is None:
        raise NotFoundError("Document not found")
    if not await can_access_document(session, user, document.id, need="download"):
        raise ForbiddenError("You do not have permission to download this document")

    storage = get_storage()
    body = await storage.get_object(document.s3_key)
    await record_audit(
        session,
        actor_id=user.id,
        action="document.download",
        resource_type="document",
        resource_id=document.id,
    )
    await session.commit()
    return Response(
        content=body,
        media_type=document.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{document.filename}"',
            "Content-Length": str(len(body)),
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{document_id}/permissions", response_model=list[PermissionOut])
async def permissions(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    await service.get_document_for_read(session, user, document_id)
    rows = await list_permissions(session, document_id)
    return [
        PermissionOut(
            id=p.id,
            grantee_type=p.grantee_type,
            grantee_user_id=p.grantee_user_id,
            grantee_role=p.grantee_role,
            permission=p.permission,
            granted_by=p.granted_by,
            granted_at=p.granted_at.isoformat() if p.granted_at else None,
        )
        for p in rows
    ]


@router.post("/{document_id}/permissions", response_model=PermissionOut, status_code=201)
async def add_permission(
    document_id: uuid.UUID,
    payload: GrantRequest,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    await service.get_document_for_read(session, user, document_id)
    perm = await grant(
        session,
        document_id,
        grantee_type=payload.grantee_type,
        permission=payload.permission,
        grantee_user_id=payload.grantee_user_id,
        grantee_role=payload.grantee_role,
        granted_by=user.id,
    )
    await record_audit(
        session,
        actor_id=user.id,
        action="permission.grant",
        resource_type="document",
        resource_id=document_id,
        metadata={
            "grantee_type": payload.grantee_type,
            "grantee_user_id": str(payload.grantee_user_id) if payload.grantee_user_id else None,
            "grantee_role": payload.grantee_role,
            "permission": payload.permission,
        },
    )
    await session.commit()
    return PermissionOut(
        id=perm.id,
        grantee_type=perm.grantee_type,
        grantee_user_id=perm.grantee_user_id,
        grantee_role=perm.grantee_role,
        permission=perm.permission,
        granted_by=perm.granted_by,
        granted_at=perm.granted_at.isoformat() if perm.granted_at else None,
    )


@router.delete("/{document_id}/permissions")
async def remove_permission(
    document_id: uuid.UUID,
    payload: RevokeRequest,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    await service.get_document_for_read(session, user, document_id)
    removed = await revoke(
        session,
        document_id,
        grantee_type=payload.grantee_type,
        permission=payload.permission,
        grantee_user_id=payload.grantee_user_id,
        grantee_role=payload.grantee_role,
    )
    await record_audit(
        session,
        actor_id=user.id,
        action="permission.revoke",
        resource_type="document",
        resource_id=document_id,
        metadata={"grantee_type": payload.grantee_type, "permission": payload.permission},
    )
    await session.commit()
    return {"removed": removed}


@router.delete("/{document_id}", status_code=204)
async def delete(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    await service.delete_document(session, user, document_id)
    await record_audit(
        session,
        actor_id=user.id,
        action="document.delete",
        resource_type="document",
        resource_id=document_id,
    )
    await session.commit()
