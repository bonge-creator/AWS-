"""Embedding protocol — Bedrock Titan or local BGE-M3 (both 1024-dim)."""

from abc import ABC, abstractmethod
from typing import List


class EmbedderPort(ABC):
    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Return one 1024-dim vector per input text."""

    @property
    def dimensions(self) -> int:
        return 1024

    @property
    def model_id(self) -> str:
        raise NotImplementedError