"""Storage protocol — S3 or local filesystem, selected by config."""

from abc import ABC, abstractmethod
from typing import Optional


class StoragePort(ABC):
    @abstractmethod
    async def put_object(
        self,
        key: str,
        body: bytes,
        content_type: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store `body` under `key`. Returns the object key."""

    @abstractmethod
    async def get_object(self, key: str) -> bytes:
        """Return raw bytes for `key`."""

    @abstractmethod
    async def generate_presigned_url(self, key: str, expires_in: int = 60) -> str:
        """Return a short-lived URL the browser can fetch."""

    @abstractmethod
    async def object_exists(self, key: str) -> bool:
        """Return True if the object exists."""