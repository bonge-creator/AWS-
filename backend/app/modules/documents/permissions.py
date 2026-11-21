"""Document-level access control — the single source of truth for permissions.

Every read path (list, preview, download, retrieval, summary) resolves through
this module, so a grant made in the admin UI is immediately effective and a
revoke immediately removes access.
"""

import uuid
from typing import Optional, Sequence

from sqlalchemy import Select, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document
from app.db.models.permission import DocumentPermission
from app.db.models.user import User

# A grant of "download" or "manage" implies the right to view.
VIEWING_PERMISSIONS = ("view", "download", "manage")


def permission_filter(user: User) -> list:
    """SQL conditions matching documents `user` is allowed to read.

    Admins bypass the ACL entirely. The uploader always keeps access to their
    own document. Otherwise a direct user grant or a role grant applies.

    The two access paths are combined with OR, and the whole thing is returned
    as a *single* condition. Callers splat the result into `.where(*conditions)`,
    which ANDs its arguments — returning the paths as separate list entries
    would require a document to be both uploaded by the caller *and* granted to
    them, which would silently hide every document a role grant was meant to
    expose.
    """
    if user.role == "admin":
        return [text("TRUE")]

    granted = select(DocumentPermission.document_id).where(
        DocumentPermission.permission.in_(VIEWING_PERMISSIONS),
        or_(
            (DocumentPermission.grantee_type == "user")
            & (DocumentPermission.grantee_user_id == user.id),
            (DocumentPermission.grantee_type == "role")
            & (DocumentPermission.grantee_role == user.role),
        ),
    )
    return [or_(Document.uploaded_by == user.id, Document.id.in_(granted))]


async def permitted_document_ids(session: AsyncSession, user: User) -> list[uuid.UUID]:
    """Document IDs `user` may read — used by metadata queries."""
    stmt = select(Document.id).where(*permission_filter(user))
    rows = await session.execute(stmt)
    return [r[0] for r in rows]


async def can_access_document(
    session: AsyncSession, user: User, document_id: uuid.UUID, need: str = "view"
) -> bool:
    """Check a specific capability on a specific document."""
    if user.role == "admin":
        return True
    doc = await session.get(Document, document_id)
    if doc is None:
        return False
    if doc.uploaded_by == user.id:
        return True
    if need == "view":
        wanted = VIEWING_PERMISSIONS
    elif need == "download":
        wanted = ("download", "manage")
    else:  # manage
        wanted = ("manage",)
    stmt = select(DocumentPermission.id).where(
        DocumentPermission.document_id == document_id,
        DocumentPermission.permission.in_(wanted),
        or_(
            (DocumentPermission.grantee_type == "user")
            & (DocumentPermission.grantee_user_id == user.id),
            (DocumentPermission.grantee_type == "role")
            & (DocumentPermission.grantee_role == user.role),
        ),
    )
    result = await session.execute(stmt)
    return result.first() is not None


async def grant(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    grantee_type: str,
    permission: str,
    grantee_user_id: Optional[uuid.UUID] = None,
    grantee_role: Optional[str] = None,
    granted_by: Optional[uuid.UUID] = None,
) -> DocumentPermission:
    """Create a grant. Re-granting the same capability is a no-op."""
    if grantee_type == "user":
        if grantee_user_id is None:
            raise ValueError("grantee_user_id is required for user grants")
        grantee_role = None
    elif grantee_type == "role":
        if grantee_role is None:
            raise ValueError("grantee_role is required for role grants")
        grantee_user_id = None
    else:
        raise ValueError(f"Unknown grantee_type: {grantee_type}")
    if permission not in ("view", "download", "manage"):
        raise ValueError(f"Unknown permission: {permission}")

    stmt = select(DocumentPermission).where(
        DocumentPermission.document_id == document_id,
        DocumentPermission.grantee_type == grantee_type,
        DocumentPermission.permission == permission,
    )
    if grantee_type == "user":
        stmt = stmt.where(DocumentPermission.grantee_user_id == grantee_user_id)
    else:
        stmt = stmt.where(DocumentPermission.grantee_role == grantee_role)

    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    perm = DocumentPermission(
        id=uuid.uuid4(),
        document_id=document_id,
        grantee_type=grantee_type,
        grantee_user_id=grantee_user_id,
        grantee_role=grantee_role,
        permission=permission,
        granted_by=granted_by,
    )
    session.add(perm)
    await session.flush()
    return perm


async def revoke(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    grantee_type: str,
    permission: str,
    grantee_user_id: Optional[uuid.UUID] = None,
    grantee_role: Optional[str] = None,
) -> int:
    stmt = select(DocumentPermission).where(
        DocumentPermission.document_id == document_id,
        DocumentPermission.grantee_type == grantee_type,
        DocumentPermission.permission == permission,
    )
    if grantee_type == "user":
        stmt = stmt.where(DocumentPermission.grantee_user_id == grantee_user_id)
    else:
        stmt = stmt.where(DocumentPermission.grantee_role == grantee_role)
    rows = (await session.execute(stmt)).scalars().all()
    for row in rows:
        await session.delete(row)
    await session.flush()
    return len(rows)


async def list_permissions(
    session: AsyncSession, document_id: uuid.UUID
) -> Sequence[DocumentPermission]:
    stmt = (
        select(DocumentPermission)
        .where(DocumentPermission.document_id == document_id)
        .order_by(DocumentPermission.granted_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
