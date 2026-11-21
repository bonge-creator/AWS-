"""Document summaries — map-reduce over a document's chunks."""

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document
from app.db.models.document_summary import DocumentSummary
from app.modules.documents.permissions import can_access_document
from app.ports.factory import get_llm

SUMMARY_SYSTEM = (
    "You summarise one section of a business document. "
    "State the key facts: parties, dates, obligations, amounts, and terms. "
    "Use only the text you are given. If the section is empty, say so. "
    "Output one short bullet per fact, each beginning with '- '. "
    "Do not add a source line, title, or preamble."
)

REDUCE_SYSTEM = (
    "You combine section summaries of a single document into one coherent summary. "
    "Keep concrete facts, dates and figures. Use only the supplied summaries. "
    "Output one short bullet per fact, each beginning with '- '. "
    "Do not add a source line, title, or preamble."
)

_BULLET_RE = re.compile(r"^\s*(?:[-•*]|\d+\.)\s+", re.M)
_BULLET_LINE_RE = re.compile(r"^\s*(?:[-•*]|\d+\.)\s+(.*)$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_REF_PREFIX_RE = re.compile(r"^\[\d+\]\s*")


def _bulletize(text: str) -> str:
    """Normalise a summary into one '- ' bullet per line.

    Handles both already-bulleted text and plain paragraphs.
    Also strips [n] passage-reference prefixes that the model may add.
    """
    text = (text or "").strip()
    if not text:
        return text
    # Strip [n] passage-reference prefixes (e.g. [1] ) from the start.
    text = _REF_PREFIX_RE.sub("", text)
    if _BULLET_RE.search(text):
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            m = _BULLET_LINE_RE.match(stripped)
            lines.append(f"- {m.group(1).strip()}" if m else stripped)
        return "\n".join(lines)
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]
    return "\n".join(f"- {s}" for s in sentences) or text


async def summarise_document(
    session: AsyncSession,
    user,
    document_id: uuid.UUID,
    *,
    max_sections: int = 12,
) -> DocumentSummary:
    """Summarise a document the user may read, and cache the result."""
    if not await can_access_document(session, user, document_id, need="view"):
        from app.core.errors import ForbiddenError

        raise ForbiddenError("You do not have access to this document")

    chunks = (
        await session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
    ).scalars().all()
    if not chunks:
        from app.core.errors import ValidationError

        raise ValidationError("This document has no indexed content to summarise")

    llm = get_llm()

    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    filename = document.filename if document else "document"

    section_summaries: list[str] = []
    models_used: list[str] = []
    for chunk in chunks[:max_sections]:
        response = await llm.summarise(
            SUMMARY_SYSTEM,
            f"[1] pages {chunk.page_start}-{chunk.page_end}\n{chunk.text}",
        )
        text = response.text.strip() if response.text else ""
        if text:
            section_summaries.append(text)
            if response.model:
                models_used.append(response.model)

    if not section_summaries:
        summary_text = "This document contains no summarisable text."
    elif len(section_summaries) == 1:
        summary_text = section_summaries[0]
    else:
        combined = "\n\n".join(f"[{i}] {s}" for i, s in enumerate(section_summaries, start=1))
        response = await llm.summarise(
            REDUCE_SYSTEM,
            combined,
            "Write a single consolidated summary of this document as a list of short bullet points.",
        )
        summary_text = (
            response.text.strip()
            if response.text and response.text.strip()
            else "\n\n".join(section_summaries)
        )
        if response.model:
            models_used.append(response.model)

    page_start = min(chunk.page_start for chunk in chunks[:max_sections])
    page_end = max(chunk.page_end for chunk in chunks[:max_sections])
    header = f"Source: {filename} — pages {page_start}–{page_end}"
    summary_text = f"{header}\n{_bulletize(summary_text)}"

    existing = (
        await session.execute(
            select(DocumentSummary).where(DocumentSummary.document_id == document_id)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = DocumentSummary(
            id=uuid.uuid4(), document_id=document_id, summary="", model="", prompt_version="v1"
        )
        session.add(existing)
    existing.summary = summary_text
    # Record the engine that actually produced the text — the model id when a
    # model answered, or the fallback marker when it did not. Recording the
    # adapter class here would claim a model that never ran.
    existing.model = ", ".join(dict.fromkeys(models_used)) or "unknown"
    existing.prompt_version = "v1"
    existing.generated_at = datetime.now(timezone.utc)
    await session.flush()
    return existing
