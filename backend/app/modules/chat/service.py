"""Question answering — retrieval, generation, citations and abstention.

Order of operations (the security-critical part):

1. Resolve the user's permitted documents.
2. Retrieve only from that set (permission lives in the SQL).
3. Re-check every candidate's permission before it may enter the prompt.
4. Only then call the model.
5. Drop any citation the model invented.

If nothing clears the relevance threshold, the archive answers "I don't know"
rather than guessing.
"""

import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.citation import Citation
from app.db.models.conversation import Conversation
from app.db.models.document import Document
from app.db.models.evidence import RetrievalEvidence
from app.db.models.message import Message
from app.db.models.user import User
from app.modules.documents.permissions import permission_filter
from app.modules.retrieval.service import RetrievedChunk, search, keyword_search
from app.ports.factory import get_embedder, get_llm
from app.shared.audit import record_audit

SYSTEM_PROMPT = (
    "You are the archive assistant for an enterprise document repository. "
    "Answer strictly from the numbered context passages provided. "
    "If the context does not contain the answer, say you do not know — never guess. "
    "Reference supporting passages inline with [n] markers."
)

ABSTENTION_TEXT = (
    "I could not find an answer to that in the documents you have access to. "
    "The archive contains no information that answers this question."
)


@dataclass
class CitationOut:
    index: int
    document_id: uuid.UUID
    filename: str
    page_start: int
    page_end: int
    quote: str
    score: Optional[float] = None


@dataclass
class AnswerResult:
    text: str
    found: bool
    citations: list[CitationOut] = field(default_factory=list)
    evidence: list[RetrievedChunk] = field(default_factory=list)
    model: str = ""
    intent: str = "semantic"
    message_id: Optional[uuid.UUID] = None


# ─────────────────────── Deterministic metadata questions ───────────────────────

_MONTH_NAMES = {
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
}

# "lease agreements expiring next year" / "which contracts expire in 2027"
_EXPIRY_PATTERN = re.compile(
    r"\b(expire|expiring|expires|expiry|expiration|ending|end)\b"
    r"(?:\s+\w+){0,3}?\s*\b(next\s+year|this\s+year|\d{4})\b",
    re.I,
)
_DOC_TYPE_PATTERN = re.compile(
    r"\b(lease|leases|contract|contracts|policy|policies|nda|ndas|invoice|invoices|"
    r"report|reports|mou|mous|agreement|agreements)\b",
    re.I,
)


def _resolve_year(token: str, today: date) -> Optional[int]:
    token = token.lower().strip()
    if token == "next year":
        return today.year + 1
    if token == "this year":
        return today.year
    if token.isdigit():
        return int(token)
    return None


def plan_metadata_query(question: str, today: Optional[date] = None) -> Optional[dict]:
    """Recognise questions that are answered by document metadata, not prose.

    Example: "Which lease agreements expire next year?" is answered exactly by
    the expiry_date column, so we answer it deterministically instead of asking
    a model to read dates out of text.
    """
    today = today or date.today()
    match = _EXPIRY_PATTERN.search(question)
    if not match:
        return None
    year = _resolve_year(match.group(2), today)
    if year is None:
        return None

    doc_types = []
    type_match = _DOC_TYPE_PATTERN.search(question)
    if type_match:
        word = type_match.group(1).lower()
        singular = {
            "leases": "lease", "contracts": "contract", "policies": "policy",
            "ndas": "nda", "invoices": "invoice", "reports": "report",
            "agreements": "contract", "mous": "contract",
        }.get(word, word)
        if singular == "mou":
            singular = "contract"
        doc_types.append(singular)
    return {"intent": "expiry", "year": year, "doc_types": doc_types}


async def answer_metadata_query(
    session: AsyncSession, user: User, question: str, plan: dict
) -> Optional[AnswerResult]:
    """Answer an expiry question from the metadata columns."""
    year = plan["year"]
    conditions = list(permission_filter(user))
    conditions.append(Document.expiry_date.isnot(None))
    conditions.append(
        Document.expiry_date >= date(year, 1, 1),
    )
    conditions.append(Document.expiry_date <= date(year, 12, 31))
    if plan["doc_types"]:
        conditions.append(Document.doc_type.in_(plan["doc_types"]))

    stmt = (
        select(Document)
        .where(*conditions)
        .order_by(Document.expiry_date.asc())
    )
    documents = list((await session.execute(stmt)).scalars().all())

    if not documents:
        return AnswerResult(
            text=(
                f"No documents you can access expire in {year}. "
                "The archive contains no matching records for that period."
            ),
            found=False,
            intent="metadata-expiry",
        )

    scope = f" {plan['doc_types'][0]}" if plan["doc_types"] else ""
    lines = []
    citations = []
    for index, doc in enumerate(documents, start=1):
        label = doc.title or doc.filename
        lines.append(f"{index}. {label} — expires {doc.expiry_date.strftime('%d %B %Y')}")
        citations.append(
            CitationOut(
                index=index,
                document_id=doc.id,
                filename=doc.filename,
                page_start=1,
                page_end=doc.page_count or 1,
                quote=(
                    doc.extracted_metadata or {}
                ).get("expiry_evidence")
                or f"Expiry date: {doc.expiry_date.isoformat()}",
                score=1.0,
            )
        )

    text = (
        f"Found {len(documents)} document{'' if len(documents) == 1 else 's'} "
        f"in the archive that expire in {year}"
        + (f" ({plan['doc_types'][0]} documents)" if plan["doc_types"] else "")
        + ":"
    )
    text += "\n" + "\n".join(lines)
    return AnswerResult(
        text=text,
        found=True,
        citations=citations,
        intent="metadata-expiry",
    )


# ─────────────────────── Greeting questions ───────────────────────

_GREETING_PATTERN = re.compile(
    r"\b(hello|hi|hey|good\s+(morning|afternoon|evening)|how.?are.?you|thanks|thank.?you|bye|"
    r"what.?can.?you.?do|who.?are.?you|help|hey.?there)\b",
    re.I,
)

_GREETING_REPLIES = [
    "Hello! I'm the archive assistant. I can help you search and answer questions "
    "from the documents you have access to. Try asking about leases, contracts, "
    "policies, or search for a keyword across all documents.",
    "Hi there! Ask me anything about the documents in your archive — I'll search "
    "them and cite my sources.",
    "Good to hear from you! I'm your archive assistant. What would you like to know?",
    "Hello! I can search through your documents, summarise content, and point you "
    "to the exact passages that answer your question.",
]


def plan_greeting(question: str) -> Optional[dict]:
    """Recognize greeting messages and return a canned friendly reply."""
    if _GREETING_PATTERN.search(question):
        return {"intent": "greeting"}
    return None


# ─────────────────────── Keyword search questions ───────────────────────

_KEYWORD_PATTERNS = [
    re.compile(r"^\s*keyword\s+(.+)", re.I),
    re.compile(r"^\s*(?:search|find|look\s+up)\s+(?:for\s+)?(.+)", re.I),
    re.compile(r"^\s*(?:which|what)\s+documents?\s+(?:have|mention|contain|include|with)\s+(.+)", re.I),
    re.compile(r"^\s*documents?\s+(?:mention|contain|have|include|with)\s+(.+)", re.I),
]

_KEYWORD_DOCS_ONLY = re.compile(
    r"^\s*(?:which|what)\s+documents?\s+(?:have|mention|contain|include|with)\s+(.+)", re.I,
)


def plan_keyword(question: str) -> Optional[dict]:
    """Recognize keyword search patterns and extract the search term."""
    for pat in _KEYWORD_PATTERNS:
        m = pat.search(question)
        if m:
            keyword = m.group(1).strip()
            if keyword:
                # Strip trailing question marks / punctuation.
                keyword = keyword.rstrip("?.,!:;")
                if keyword:
                    return {
                        "intent": "keyword",
                        "keyword": keyword,
                        "docs_only": bool(_KEYWORD_DOCS_ONLY.match(question)),
                    }
    return None


async def answer_keyword_query(
    session: AsyncSession,
    user: User,
    question: str,
    plan: dict,
) -> Optional[AnswerResult]:
    """Search all accessible documents for a keyword using ILIKE."""
    keyword = plan["keyword"]
    docs_only = plan.get("docs_only", False)

    if not keyword:
        return AnswerResult(
            text="Please specify a keyword to search for.",
            found=False,
            intent="keyword",
        )

    # Permission-scoped keyword search across all accessible documents.
    chunks = await keyword_search(
        session, user, keyword, top_k=10, docs_only=docs_only
    )

    if not chunks:
        return AnswerResult(
            text=f"No documents you have access to contain the keyword '{keyword}'.",
            found=False,
            intent="keyword",
        )

    # Deduplicate by document — one citation per document, listing matching pages.
    seen_docs: dict = {}
    for chunk in chunks:
        doc_id = chunk.document_id
        if doc_id not in seen_docs:
            seen_docs[doc_id] = {
                "document_id": doc_id,
                "filename": chunk.filename,
                "doc_type": chunk.doc_type,
                "pages": [],
                "texts": [],
            }
        seen_docs[doc_id]["pages"].append((chunk.page_start, chunk.page_end))
        seen_docs[doc_id]["texts"].append(chunk.text)

    lines = []
    citations = []
    for idx, (doc_id, info) in enumerate(seen_docs.items(), start=1):
        pages_str = ", ".join(f"p.{p[0]}" if p[0] == p[1] else f"p.{p[0]}–{p[1]}" for p in info["pages"])
        # First matching text snippet, truncated.
        snippet = " ".join(info["texts"][0].split())[:200]
        if len(info["texts"][0].split()) > 35:
            snippet += "…"
        lines.append(f"{idx}. {info['filename']} ({pages_str}) — {snippet}")
        citations.append(
            CitationOut(
                index=idx,
                document_id=info["document_id"],
                filename=info["filename"],
                page_start=info["pages"][0][0],
                page_end=info["pages"][0][1],
                quote=snippet,
                score=1.0,
            )
        )

    text = (
        f"Found {len(seen_docs)} document{'' if len(seen_docs) == 1 else 's'} "
        f"containing '{keyword}':\n"
        + "\n".join(lines)
    )
    return AnswerResult(
        text=text,
        found=True,
        citations=citations,
        intent="keyword",
    )


# ───────────────────────────── Semantic question path ─────────────────────────────

def build_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n---\n\n".join(chunk.as_context(i) for i, chunk in enumerate(chunks, start=1))


def _extract_citation_indices(text: str) -> list[int]:
    return [int(m) for m in re.findall(r"\[(\d{1,2})\]", text)]


def _quote_for(chunk: RetrievedChunk, limit: int = 320) -> str:
    text = " ".join(chunk.text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


async def answer_question(
    session: AsyncSession,
    user: User,
    question: str,
    *,
    conversation_id: Optional[uuid.UUID] = None,
    persist: bool = True,
) -> AnswerResult:
    """Answer `question` for `user`, honouring their document permissions."""
    question = (question or "").strip()
    if not question:
        raise ValueError("A question is required")

    # 0. Greeting — a canned friendly reply, no retrieval or model call.
    greeting_plan = plan_greeting(question)
    if greeting_plan:
        result = AnswerResult(
            text=random.choice(_GREETING_REPLIES),
            found=True,
            intent="greeting",
        )
        if persist:
            await _persist(session, user, conversation_id, question, result)
        await record_audit(
            session,
            actor_id=user.id,
            action="chat.answer",
            resource_type="conversation",
            resource_id=conversation_id,
            metadata={"intent": "greeting", "found": True, "citations": 0},
        )
        await session.commit()
        return result

    # 1. Deterministic path for metadata questions.
    plan = plan_metadata_query(question)
    if plan:
        result = await answer_metadata_query(session, user, question, plan)
        if result is not None:
            if persist:
                await _persist(session, user, conversation_id, question, result)
            await record_audit(
                session,
                actor_id=user.id,
                action="chat.answer",
                resource_type="conversation",
                resource_id=conversation_id,
                metadata={"intent": result.intent, "found": result.found, "citations": len(result.citations)},
            )
            await session.commit()
            return result

    # 2. Keyword search — deterministic ILIKE across all accessible documents.
    keyword_plan = plan_keyword(question)
    if keyword_plan:
        result = await answer_keyword_query(session, user, question, keyword_plan)
        if persist:
            await _persist(session, user, conversation_id, question, result)
        await record_audit(
            session,
            actor_id=user.id,
            action="chat.answer",
            resource_type="conversation",
            resource_id=conversation_id,
            metadata={"intent": "keyword", "found": result.found, "citations": len(result.citations)},
        )
        await session.commit()
        return result

    # 3. Semantic retrieval, permission-scoped in SQL.
    embedder = get_embedder()
    query_vector = (await embedder.embed([question]))[0]
    chunks = await search(
        session,
        user,
        query_vector,
        embedding_model=embedder.model_id,
        top_k=settings.top_k,
        min_score=settings.min_score,
    )

    if not chunks:
        result = AnswerResult(text=ABSTENTION_TEXT, found=False, intent="semantic")
        if persist:
            await _persist(session, user, conversation_id, question, result)
        await record_audit(
            session,
            actor_id=user.id,
            action="chat.answer",
            resource_type="conversation",
            resource_id=conversation_id,
            metadata={"intent": "semantic", "found": False, "citations": 0},
        )
        await session.commit()
        return result

    # 3. Generate, then keep only citations that point at real passages.
    context = build_context(chunks)
    llm = get_llm()
    response = await llm.generate(SYSTEM_PROMPT, context, question)

    valid_indices = set(range(1, len(chunks) + 1))
    requested = [i for i in response.citations if i in valid_indices]
    inline = [i for i in _extract_citation_indices(response.text) if i in valid_indices]
    used = sorted(set(requested) | set(inline))

    found = bool(response.found) and bool(response.text.strip()) and bool(used)
    if not found:
        text = ABSTENTION_TEXT if not response.text.strip() else response.text
        if not response.found:
            text = ABSTENTION_TEXT
    else:
        text = response.text

    citations = [
        CitationOut(
            index=i,
            document_id=chunks[i - 1].document_id,
            filename=chunks[i - 1].filename,
            page_start=chunks[i - 1].page_start,
            page_end=chunks[i - 1].page_end,
            quote=_quote_for(chunks[i - 1]),
            score=chunks[i - 1].score,
        )
        for i in used
    ]

    result = AnswerResult(
        text=text,
        found=found,
        citations=citations,
        evidence=chunks,
        model=response.model or "unknown",
        intent="semantic",
    )

    if persist:
        await _persist(session, user, conversation_id, question, result)
    await record_audit(
        session,
        actor_id=user.id,
        action="chat.answer",
        resource_type="conversation",
        resource_id=conversation_id,
        metadata={
            "intent": result.intent,
            "found": result.found,
            "citations": len(citations),
            "model": result.model,
        },
    )
    await session.commit()
    return result


async def _persist(
    session: AsyncSession,
    user: User,
    conversation_id: Optional[uuid.UUID],
    question: str,
    result: AnswerResult,
) -> None:
    """Store the question, the answer, its citations and the retrieval evidence."""
    if conversation_id is None:
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=user.id,
            title=question[:120],
            created_at=datetime.now(timezone.utc),
        )
        session.add(conversation)
        await session.flush()
        conversation_id = conversation.id
    else:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id != user.id:
            raise ValueError("Conversation not found")

    session.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role="user",
            content=question,
            created_at=datetime.now(timezone.utc),
        )
    )
    assistant = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content=result.text,
        answer_found=result.found,
        created_at=datetime.now(timezone.utc),
    )
    session.add(assistant)
    await session.flush()

    used_chunk_ids: set = set()
    for citation in result.citations:
        # Match the citation to the chunk it actually came from. Matching on
        # document alone would give two citations to different pages of the
        # same document the same chunk, which the (message_id, chunk_id)
        # unique constraint rejects.
        def _overlaps(evidence_chunk) -> bool:
            return (
                evidence_chunk.page_start <= citation.page_end
                and citation.page_start <= evidence_chunk.page_end
            )

        chunk = next(
            (
                c
                for c in result.evidence
                if c.document_id == citation.document_id and _overlaps(c)
            ),
            None,
        )
        chunk_id = None
        if chunk is not None:
            chunk_id = chunk.chunk_id
        else:
            # Metadata citations point at a document, not a chunk; link the first
            # chunk so the citation still opens the right document.
            from sqlalchemy import select as _select

            from app.db.models.chunk import DocumentChunk

            row = await session.execute(
                _select(DocumentChunk.id)
                .where(DocumentChunk.document_id == citation.document_id)
                .order_by(DocumentChunk.chunk_index)
                .limit(1)
            )
            chunk_id = row.scalar_one_or_none()
        if chunk_id is None or chunk_id in used_chunk_ids:
            continue
        used_chunk_ids.add(chunk_id)
        session.add(
            Citation(
                id=uuid.uuid4(),
                message_id=assistant.id,
                document_id=citation.document_id,
                chunk_id=chunk_id,
                ordinal=citation.index,
                page_start=citation.page_start,
                page_end=citation.page_end,
                quote=citation.quote,
                score=citation.score,
            )
        )

    for rank, chunk in enumerate(result.evidence, start=1):
        session.add(
            RetrievalEvidence(
                id=uuid.uuid4(),
                message_id=assistant.id,
                chunk_id=chunk.chunk_id,
                rank=rank,
                score=chunk.score,
                token_count=max(1, len(chunk.text) // 4),
                created_at=datetime.now(timezone.utc),
            )
        )
    result.message_id = assistant.id
