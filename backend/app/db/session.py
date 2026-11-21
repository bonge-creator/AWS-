"""Async database session factory."""

import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_pre_ping=True,  # Neon scales to zero and drops idle connections
    pool_recycle=120,
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


@contextlib.asynccontextmanager
async def keepalive(interval: float = 30.0) -> AsyncIterator[None]:
    """Keep the database compute awake while the app is running.

    The managed Postgres instance suspends its compute after a few minutes
    without traffic. A suspended compute drops the pooled connections, and
    the next query fails mid-flight with "connection was closed in the
    middle of operation" — a failure `pool_pre_ping` cannot catch, because
    the connection was alive when it was checked and died during the query.

    A cheap periodic query keeps the compute running, so the failure mode
    never arises. The connection is validated before use, so this also
    revives a connection the provider closed while we were not looking.
    """
    stop = asyncio.Event()

    async def _ping() -> None:
        while not stop.is_set():
            try:
                async with async_session() as session:
                    await session.execute(text("SELECT 1"))
            except Exception:  # noqa: BLE001 - a failed ping is retried
                pass
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval)

    task = asyncio.create_task(_ping())
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task