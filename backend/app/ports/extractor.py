"""Extraction protocol — Textract or local PDF parsing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExtractionResult:
    text: str
    page_count: int
    pages: list  # [{"page": int, "text": str}, ...]


class ExtractorPort(ABC):
    @abstractmethod
    async def extract(
        self,
        document_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> ExtractionResult:
        """Return extracted text + page mapping."""