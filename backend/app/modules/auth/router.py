"""Auth routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db_session
from app.modules.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from app.modules.auth.service import authenticate, issue_tokens, refresh_access_token
from app.shared.audit import record_audit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    user = await authenticate(session, payload.email, payload.password)
    await record_audit(
        session,
        actor_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_db_session)):
    return await refresh_access_token(session, payload.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user=Depends(get_current_user)):
    return UserOut.of(user)
