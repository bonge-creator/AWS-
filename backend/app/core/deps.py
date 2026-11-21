"""FastAPI dependency providers: database session + authenticated principal."""

import uuid
from typing import Annotated, Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.models.user import User
from app.db.session import get_db_session

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)] = None,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing credentials")
    payload = decode_token(credentials.credentials, settings.jwt_secret)
    if payload is None or payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired token")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedError("Invalid token subject")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise ForbiddenError("Admin only")
    return user


def require_staff(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "analyst"):
        raise ForbiddenError("Requires analyst or admin role")
    return user
