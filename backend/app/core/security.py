"""Authentication primitives: argon2id hashing + HS256 JWT."""

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

import jwt
from argon2 import PasswordHasher

ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except Exception:
        return False


def create_access_token(
    user_id: uuid.UUID,
    role: str,
    secret: str,
    ttl_min: int,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ttl_min),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def create_refresh_token(user_id: uuid.UUID, secret: str, ttl_days: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(days=ttl_days),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> Optional[dict]:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None