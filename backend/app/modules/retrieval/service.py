"""Permission-scoped semantic retrieval.

The permission boundary lives *inside* the SQL: a `permitted` CTE resolves the
document IDs the user may read, and that CTE is joined into the pgvector cosine
query. Unauthorized chunks are never returned to the application layer, so they
cannot reach the prompt, the citations, or the UI.

A second check in `filter_by_permission` re-validates every candidate before it
is used (defence in depth against a mis-written filter).
"""

import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User

# The permission CTE. `grantee_user_id` / `grantee_role` are bound parameters.
PERMITTED_CTE = """
permitted AS (
    SELECT d.id AS document_id
    FROM documents d
    WHERE d.uploaded_by = :user_id
    UNION
    SELECT dp.document_id
    FROM document_permissions dp
    WHERE dp.permission IN ('view', 'download', 'manage')
      AND (
        (dp.grantee_type = 'user' AND dp.grantee_user_id = :user_id)
        OR (dp.grantee_type = 'role' AND dp.grantee_role = :role)
      )
)
"""


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    doc_type: Optional[str]
    text: str
    page_start: int
    page_end: int
    score: float
    heading_path: Optional[List[str]] = None
    expiry_date: Optional[str] = None

    def as_context(self, index: int) -> str:
        return f"[{index}] {self.filename} (pages {self.page_start}-{self.page_end})\n{self.text}"


def _is_admin(user: User) -> bool:
    return user.role == "admin"


async def search(
    session: AsyncSession,
    user: User,
    query_embedding: List[float],
    *,
    embedding_model: str,
    top_k: int = 6,
    min_score: float = 0.30,
    doc_type: Optional[str] = None,
) -> List[RetrievedChunk]:
    """Vector search restricted to documents the user may read.

    Admins skip the ACL join; for everyone else the `permitted` CTE is part of
    the query, so the database itself filters before ranking.
    """
    params = {
        "qvec": str(query_embedding),
        "user_id": str(user.id),
        "role": user.role,
        "model": embedding_model,
        "top_k": top_k,
    }
    type_clause = ""
    if doc_type:
        type_clause = "AND d.doc_type = :doc_type"
        params["doc_type"] = doc_type

    if _is_admin(user):
        # Admins see every document, so the ACL join is omitted entirely.
        sql = text(
            f"""
            WITH {PERMITTED_CTE}
            SELECT c.id AS chunk_id,
                   c.document_id,
                   d.filename,
                   d.doc_type,
                   c.text,
                   c.page_start,
                   c.page_end,
                   c.heading_path,
                   d.expiry_date,
                   1 - (c.embedding <=> CAST(:qvec AS vector)) AS score
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding_model = :model
              {type_clause}
            ORDER BY c.embedding <=> CAST(:qvec AS vector)
            LIMIT :top_k
            """
        )
        # The CTE still refers to :user_id/:role, so bind them.
        result = await session.execute(sql, params)
    else:
        sql = text(
            f"""
            WITH {PERMITTED_CTE}
            SELECT c.id AS chunk_id,
                   c.document_id,
                   d.filename,
                   d.doc_type,
                   c.text,
                   c.page_start,
                   c.page_end,
                   c.heading_path,
                   d.expiry_date,
                   1 - (c.embedding <=> CAST(:qvec AS vector)) AS score
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            JOIN permitted p ON p.document_id = c.document_id
            WHERE c.embedding_model = :model
              {type_clause}
            ORDER BY c.embedding <=> CAST(:qvec AS vector)
            LIMIT :top_k
            """
        )
        result = await session.execute(sql, params)

    rows = result.fetchall()
    chunks = [
        RetrievedChunk(
            chunk_id=r[0],
            document_id=r[1],
            filename=r[2],
            doc_type=r[3],
            text=r[4],
            page_start=r[5],
            page_end=r[6],
            score=float(r[9]),
            heading_path=list(r[7]) if r[7] else None,
            expiry_date=r[8].isoformat() if r[8] else None,
        )
        for r in rows
    ]
    filtered = await filter_by_permission(session, user, chunks)
    return [c for c in filtered if c.score >= min_score]


async def filter_by_permission(
    session: AsyncSession, user: User, chunks: List[RetrievedChunk]
) -> List[RetrievedChunk]:
    """Second-chance ACL check on retrieved candidates.

    The SQL already restricted the result set; this guards against a future
    query change (a missing JOIN, a different code path) silently leaking.
    """
    if _is_admin(user) or not chunks:
        return chunks

    allowed = await _allowed_document_ids(session, user, {c.document_id for c in chunks})
    return [c for c in chunks if c.document_id in allowed]


async def _allowed_document_ids(
    session: AsyncSession, user: User, candidate_ids: set
) -> set:
    if not candidate_ids:
        return set()
    sql = text(
        """
        WITH permitted AS (
            SELECT d.id AS document_id
            FROM documents d
            WHERE d.uploaded_by = :user_id
            UNION
            SELECT dp.document_id
            FROM document_permissions dp
            WHERE dp.permission IN ('view', 'download', 'manage')
              AND (
                (dp.grantee_type = 'user' AND dp.grantee_user_id = :user_id)
                OR (dp.grantee_type = 'role' AND dp.grantee_role = :role)
              )
        )
        SELECT document_id FROM permitted WHERE document_id = ANY(:ids)
        """
    )
    result = await session.execute(
        sql,
        {"user_id": str(user.id), "role": user.role, "ids": [str(i) for i in candidate_ids]},
    )
    return {r[0] for r in result.fetchall()}


async def keyword_search(
    session: AsyncSession,
    user: User,
    keyword: str,
    *,
    top_k: int = 10,
    docs_only: bool = False,
) -> List[RetrievedChunk]:
    """Permission-scoped keyword search using ILIKE on chunk text.

    Returns chunks where the text contains the keyword, restricted to
    documents the user may read. Ordered by filename and page for consistency.
    """
    params = {
        "kw": f"%{keyword}%",
        "user_id": str(user.id),
        "role": user.role,
        "top_k": top_k,
    }

    if _is_admin(user):
        sql = text(
            f"""
            WITH {PERMITTED_CTE}
            SELECT c.id AS chunk_id,
                   c.document_id,
                   d.filename,
                   d.doc_type,
                   c.text,
                   c.page_start,
                   c.page_end,
                   c.heading_path,
                   d.expiry_date,
                   1.0 AS score
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.text ILIKE :kw
            ORDER BY d.filename, c.page_start, c.chunk_index
            LIMIT :top_k
            """
        )
        result = await session.execute(sql, params)
    else:
        sql = text(
            f"""
            WITH {PERMITTED_CTE}
            SELECT c.id AS chunk_id,
                   c.document_id,
                   d.filename,
                   d.doc_type,
                   c.text,
                   c.page_start,
                   c.page_end,
                   c.heading_path,
                   d.expiry_date,
                   1.0 AS score
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            JOIN permitted p ON p.document_id = c.document_id
            WHERE c.text ILIKE :kw
            ORDER BY d.filename, c.page_start, c.chunk_index
            LIMIT :top_k
            """
        )
        result = await session.execute(sql, params)

    rows = result.fetchall()
    chunks = [
        RetrievedChunk(
            chunk_id=r[0],
            document_id=r[1],
            filename=r[2],
            doc_type=r[3],
            text=r[4],
            page_start=r[5],
            page_end=r[6],
            score=float(r[9]),
            heading_path=list(r[7]) if r[7] else None,
            expiry_date=r[8].isoformat() if r[8] else None,
        )
        for r in rows
    ]
    filtered = await filter_by_permission(session, user, chunks)
    return [c for c in filtered if c.score >= 0.0]  # score is always 1.0 for keyword matches
