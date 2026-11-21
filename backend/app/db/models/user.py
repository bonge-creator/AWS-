"""User model — identity + role + argon2id credentials."""

import uuid

from sqlalchemy import Boolean, Column, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base
from app.db.enums import user_role
from app.db.types import tstz, utcnow


class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(user_role(), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(tstz(), nullable=False, default=utcnow)
    updated_at = Column(tstz(), nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        # Case-insensitive uniqueness: Alice@x.com and alice@x.com are one account.
        Index("uq_users_email_lower", func.lower(email), unique=True),
    )
