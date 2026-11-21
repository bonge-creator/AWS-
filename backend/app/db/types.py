"""Shared column types/helpers."""

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector  # noqa: F401  (re-exported)
from sqlalchemy import DateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def tstz() -> DateTime:
    """timestamptz column type."""
    return DateTime(timezone=True)
