"""Chunking — split extracted pages into retrieval-sized passages.

Passages are page-aware: a chunk never spans a page boundary, so every chunk
can cite an exact page range in the original PDF.
"""

import re
from dataclasses import dataclass, field
from typing import List

TARGET_CHARS = 1100
OVERLAP_CHARS = 150
MIN_CHARS = 120

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


@dataclass
class Chunk:
    text: str
    page_start: int
    page_end: int
    chunk_index: int = 0
    heading_path: List[str] = field(default_factory=list)

    @property
    def token_count(self) -> int:
        # ~4 characters per token is close enough for budget accounting.
        return max(1, len(self.text) // 4)


def _split_long(text: str, target: int, overlap: int) -> List[str]:
    """Split an oversized paragraph on sentence boundaries, then hard-cut."""
    sentences = _SENTENCE_END.split(text)
    pieces: List[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= target or not current:
            current = f"{current} {sentence}".strip() if current else sentence
            continue
        pieces.append(current)
        # Carry the tail forward so a fact spanning a split is still retrievable.
        tail = current[-overlap:] if overlap else ""
        current = f"{tail} {sentence}".strip() if tail else sentence
    if current:
        pieces.append(current)

    out: List[str] = []
    for piece in pieces:
        while len(piece) > target * 2:
            out.append(piece[: target * 2].strip())
            piece = piece[target * 2 - overlap :]
        if piece.strip():
            out.append(piece.strip())
    return out


def _extract_heading(paragraph: str) -> str | None:
    stripped = paragraph.strip()
    if not stripped:
        return None
    first_line = stripped.split("\n", 1)[0].strip()
    # Numbered section headings, e.g. "3.2 Termination" or "ARTICLE IV - RENEWAL".
    if re.match(r"^(?:\d+(?:\.\d+)*|ARTICLE\s+\w+|SECTION\s+\d+)\b[.:\s]", first_line, re.I):
        return first_line[:200]
    if first_line.isupper() and 3 <= len(first_line) <= 90:
        return first_line[:200]
    return None


def chunk_pages(pages: List[dict]) -> List[Chunk]:
    """Turn [{page, text}, ...] into page-aware chunks."""
    chunks: List[Chunk] = []
    for page in pages:
        number = int(page.get("page") or 1)
        text = (page.get("text") or "").strip()
        if not text:
            continue

        paragraphs = [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]
        heading: str | None = None
        buffer: List[str] = []
        chunks_before = len(chunks)

        def flush(force: bool = False):
            nonlocal buffer
            if not buffer:
                return
            body = "\n\n".join(buffer)
            if force or len(body) >= MIN_CHARS:
                chunks.append(
                    Chunk(
                        text=body,
                        page_start=number,
                        page_end=number,
                        heading_path=[heading] if heading else [],
                    )
                )
            buffer = []

        for paragraph in paragraphs:
            found = _extract_heading(paragraph)
            if found:
                flush()
                heading = found
                # A heading belongs to the section it introduces; keep it in the body
                # so the passage still reads correctly out of context.
                buffer.append(paragraph)
                continue
            if sum(len(p) for p in buffer) + len(paragraph) > TARGET_CHARS:
                flush()
            buffer.append(paragraph)
        # A short page — a small CSV, a one-line note, an image caption — would
        # otherwise produce no chunk at all and become invisible to retrieval and
        # summarisation. Force the last flush so every page with text yields at
        # least one chunk.
        flush(force=(len(chunks) == chunks_before))

    # Hard-wrap any single oversized paragraph.
    expanded: List[Chunk] = []
    for chunk in chunks:
        if len(chunk.text) <= TARGET_CHARS * 2:
            expanded.append(chunk)
            continue
        for piece in _split_long(chunk.text, TARGET_CHARS, OVERLAP_CHARS):
            expanded.append(
                Chunk(
                    text=piece,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    heading_path=chunk.heading_path,
                )
            )

    for index, chunk in enumerate(expanded):
        chunk.chunk_index = index
    return expanded
