"""Local background task runner — wraps FastAPI BackgroundTasks / asyncio."""

import asyncio
from typing import Awaitable, Callable

from app.ports.jobs import JobRunnerPort


class LocalJobRunner(JobRunnerPort):
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._semaphore = asyncio.Semaphore(max_workers)

    def schedule(self, coro_factory: Callable[[], Awaitable]) -> None:
        async def _wrapped():
            async with self._semaphore:
                try:
                    await coro_factory()
                except Exception:
                    import logging

                    logging.getLogger(__name__).exception("Background task failed")

        asyncio.create_task(_wrapped())