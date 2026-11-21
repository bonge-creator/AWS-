"""Seed the archive: users, corpus, ingestion and the permission matrix.

The permission matrix is what makes demo TEST 4 work — the analyst can read
the leases and the contracts, the viewer can only read the two policies, and
the NDA is restricted to admins. So the same question returns different
answers depending on who asks.

Usage:
    python -m scripts.seed          # reset and reseed
    python -m scripts.seed --keep   # skip user creation, keep existing users
"""

import asyncio
import hashlib
import sys
import uuid
from pathlib import Path

from sqlalchemy import delete, select

from app.db.models.document import Document
from app.db.models.permission import DocumentPermission
from app.db.models.user import User
from app.db.session import async_session, engine
from app.modules.auth.service import create_user
from app.modules.documents.permissions import grant
from app.modules.ingestion.pipeline import ingest_document
from app.ports.factory import get_storage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.seed_corpus import build_corpus  # noqa: E402

ADMIN_EMAIL = "admin@archivedemo.example.com"
ANALYST_EMAIL = "analyst@archivedemo.example.com"
VIEWER_EMAIL = "viewer@archivedemo.example.com"

DEMO_PASSWORD = "Archive!2026"

# Filename -> the roles that may read it. Anything not listed is admin-only.
ROLE_VISIBILITY = {
    "harbour-street-lease.pdf": ("analyst", "viewer"),
    "meridian-park-lease.pdf": ("analyst", "viewer"),
    "northgate-warehouse-lease.pdf": ("analyst",),
    "kestrel-facilities-contract.pdf": ("analyst",),
    "ridgeline-supply-agreement.pdf": ("analyst",),
    "data-retention-policy.pdf": ("viewer",),
    "information-security-policy.pdf": ("viewer",),
    "infrastructure-survey-2026.pdf": ("analyst", "viewer"),
    "transit-authority-mou.pdf": ("analyst",),
    "kestrel-q4-invoice.pdf": ("analyst",),
    # aurora-mutual-nda.pdf intentionally absent — admin only.
}


async def ensure_user(session, email: str, display_name: str, role: str) -> User:
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        existing.role = role
        existing.is_active = True
        existing.display_name = display_name
        await session.flush()
        return existing
    return await create_user(
        session,
        email=email,
        display_name=display_name,
        password=DEMO_PASSWORD,
        role=role,
        actor_id=None,
    )


async def seed() -> None:
    paths = build_corpus()
    print(f"generated {len(paths)} documents")

    async with async_session() as session:
        admin = await ensure_user(session, ADMIN_EMAIL, "Avery Chen", "admin")
        analyst = await ensure_user(session, ANALYST_EMAIL, "Noor Haddad", "analyst")
        viewer = await ensure_user(session, VIEWER_EMAIL, "Sam Okafor", "viewer")
        await session.commit()
        print(f"users: {admin.email}, {analyst.email}, {viewer.email}")

    storage = get_storage()

    async with async_session() as session:
        # Clear previous corpus documents and their permissions.
        existing = (await session.execute(select(Document))).scalars().all()
        for doc in existing:
            await session.execute(
                delete(DocumentPermission).where(DocumentPermission.document_id == doc.id)
            )
            await session.delete(doc)
        await session.commit()

        for path in paths:
            body = path.read_bytes()
            document_id = uuid.uuid4()
            key = f"documents/{document_id}/{path.name}"
            await storage.put_object(key, body, "application/pdf", {"filename": path.name})
            document = Document(
                id=document_id,
                s3_key=key,
                filename=path.name,
                content_type="application/pdf",
                byte_size=len(body),
                checksum_sha256=hashlib.sha256(body).hexdigest(),
                status="uploaded",
                uploaded_by=admin.id,
            )
            session.add(document)
            await session.flush()

            await ingest_document(session, document.id)

            # "download" implies "view", and it also lets the reader fetch the
            # original file from the document view — which is what a reviewer
            # actually needs to do with a document they are allowed to read.
            # Admins bypass the ACL entirely, so they need no grant at all.
            for role in ROLE_VISIBILITY.get(path.name, ()):
                await grant(
                    session,
                    document.id,
                    grantee_type="role",
                    permission="download",
                    grantee_role=role,
                    granted_by=admin.id,
                )
            await session.commit()
            print(f"  {path.name:38s} -> {document.doc_type:8s} expiry={document.expiry_date}")

        # Remove demo accounts left behind by an earlier email scheme. The
        # login form validates addresses strictly, so an address the
        # validator rejects is an account nobody can sign into — dead weight
        # in the admin panel. This runs after the documents are cleared,
        # because those rows reference their uploader.
        stale = (
            await session.execute(
                select(User).where(
                    User.email.notin_([ADMIN_EMAIL, ANALYST_EMAIL, VIEWER_EMAIL]),
                    User.email.like("%@archive.test"),
                )
            )
        ).scalars().all()
        for user in stale:
            await session.delete(user)
        if stale:
            await session.commit()
            print(f"removed {len(stale)} stale demo account(s)")

    await engine.dispose()
    print("\nseed complete.")
    print(f"login password for all demo users: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
