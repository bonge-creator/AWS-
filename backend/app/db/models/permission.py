"""Document-level ACL — per-document grants to a user or a role."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.enums import grantee_type_enum, permission_enum, user_role
from app.db.types import tstz, utcnow

if TYPE_CHECKING:
    from app.db.models.document import Document


class DocumentPermission(Base):
    __tablename__ = "document_permissions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    grantee_type = Column(grantee_type_enum(), nullable=False)
    grantee_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    grantee_role = Column(user_role(), nullable=True)
    permission = Column(permission_enum(), nullable=False)
    granted_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(tstz(), nullable=False, default=utcnow)

    __table_args__ = (
        # Exactly one grantee column is set, matching grantee_type.
        CheckConstraint(
            "(grantee_type = 'user' AND grantee_user_id IS NOT NULL AND grantee_role IS NULL) OR "
            "(grantee_type = 'role' AND grantee_role IS NOT NULL AND grantee_user_id IS NULL)",
            name="ck_document_permissions_grantee",
        ),
        # Partial unique indexes: no duplicate grant per (document, grantee, permission).
        Index(
            "uq_doc_perm_user",
            "document_id", "grantee_user_id", "permission",
            unique=True,
            postgresql_where="grantee_type = 'user'",
        ),
        Index(
            "uq_doc_perm_role",
            "document_id", "grantee_role", "permission",
            unique=True,
            postgresql_where="grantee_type = 'role'",
        ),
        Index("ix_document_permissions_grantee_user", "grantee_user_id"),
    )

    document = relationship("Document", back_populates="permissions")
