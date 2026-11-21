"""Auth request/response schemas."""

import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserCreateRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "analyst", "viewer"] = "viewer"


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    role: Literal["admin", "analyst", "viewer"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: str

    @classmethod
    def of(cls, user) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at.isoformat() if user.created_at else "",
        )
