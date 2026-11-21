"""Job-runner protocol — local background tasks or Lambda/SQS."""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable


class JobRunnerPort(ABC):
    @abstractmethod
    def schedule(self, coro_factory: Callable[[], Awaitable]) -> None:
        """Schedule a coroutine factory to run in the background."""