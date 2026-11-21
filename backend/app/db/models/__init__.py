"""Import every model so Base.metadata (and Alembic autogenerate) sees all tables."""

from app.db.models.audit import AuditLog
from app.db.models.chunk import DocumentChunk
from app.db.models.citation import Citation
from app.db.models.conversation import Conversation
from app.db.models.document import Document
from app.db.models.document_summary import DocumentSummary
from app.db.models.evidence import RetrievalEvidence
from app.db.models.ingestion_job import IngestionJob
from app.db.models.message import Message
from app.db.models.permission import DocumentPermission
from app.db.models.user import User

__all__ = [
    "AuditLog", "Citation", "Conversation", "Document", "DocumentChunk",
    "DocumentPermission", "DocumentSummary", "IngestionJob", "Message",
    "RetrievalEvidence", "User",
]
