"""Authentication service — login, refresh, user provisioning."""

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.db.models.user import User
from app.shared.audit import record_audit


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    # Case-insensitive lookup, matching the lower(email) unique index.
    result = await session.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
    return result.scalar_one_or_none()


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(session, email)
    if user is None or not verify_password(password, user.password_hash):
        # Same message either way — do not reveal which accounts exist.
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise ForbiddenError("This account is deactivated")
    return user


def issue_tokens(user: User) -> dict:
    access = create_access_token(
        user.id, user.role, settings.jwt_secret, settings.jwt_access_ttl_min
    )
    refresh = create_refresh_token(user.id, settings.jwt_secret, settings.jwt_refresh_ttl_days)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl_min * 60,
    }


async def refresh_access_token(session: AsyncSession, refresh_token: str) -> dict:
    payload = decode_token(refresh_token, settings.jwt_secret)
    if payload is None or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedError("Invalid refresh token")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid refresh token")
    return issue_tokens(user)


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    display_name: str,
    password: str,
    role: str,
    actor_id: uuid.UUID | None = None,
) -> User:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValidationError("A valid email address is required")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters")
    if role not in {"admin", "analyst", "viewer"}:
        raise ValidationError(f"Unknown role: {role}")
    if await get_user_by_email(session, email) is not None:
        raise ValidationError("A user with that email already exists")

    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=display_name.strip() or email,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await record_audit(
        session,
        actor_id=actor_id,
        action="user.create",
        resource_type="user",
        resource_id=user.id,
        metadata={"email": email, "role": role},
    )
    return user
