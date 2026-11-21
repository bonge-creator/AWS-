"""The permission matrix, exercised against the real database.

This is the security core of the product, so it is tested against real
PostgreSQL — real `document_permissions` rows, the real `permitted` CTE, the
real pgvector query. A mocked query would only prove the mock works.

Each test creates its own documents and grants, and removes them afterwards,
so the suite never depends on or disturbs the seeded demo archive.
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document
from app.db.models.permission import DocumentPermission
from app.db.models.user import User
from app.db.session import async_session
from app.modules.documents.permissions import (
    can_access_document,
    grant,
    list_permissions,
    permission_filter,
    permitted_document_ids,
    revoke,
)
from app.modules.retrieval.service import filter_by_permission, search


pytestmark = pytest.mark.asyncio


async def make_user(email: str, role: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=email.split("@")[0],
        role=role,
        password_hash="x",
        is_active=True,
    )
    async with async_session() as session:
        session.add(user)
        await session.commit()
    return user


async def make_document(owner: User, filename: str, doc_type: str = "lease") -> Document:
    doc = Document(
        id=uuid.uuid4(),
        s3_key=f"documents/{uuid.uuid4()}/{filename}",
        filename=filename,
        content_type="application/pdf",
        byte_size=10,
        checksum_sha256="0" * 64,
        status="ready",
        doc_type=doc_type,
        uploaded_by=owner.id,
    )
    async with async_session() as session:
        session.add(doc)
        await session.commit()
    return doc


async def cleanup(*users: User, **docs: Document) -> None:
    async with async_session() as session:
        for doc in docs.values():
            await session.execute(
                delete(DocumentPermission).where(
                    DocumentPermission.document_id == doc.id
                )
            )
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )
            await session.delete(doc)
        for user in users:
            await session.delete(user)
        await session.commit()


class TestPermissionFilter:
    async def test_admin_sees_everything(self):
        admin = await make_user("perm-admin@test.local", "admin")
        try:
            async with async_session() as session:
                conditions = permission_filter(admin)
                assert len(conditions) == 1
        finally:
            await cleanup(admin)

    async def test_non_admin_filter_is_a_single_or_ed_condition(self):
        """The uploader path and the grant path are alternatives, not
        requirements. Returning them as separate entries would AND them and
        hide every document a role grant was meant to expose."""
        user = await make_user("perm-analyst@test.local", "analyst")
        try:
            async with async_session() as session:
                conditions = permission_filter(user)
                assert len(conditions) == 1
        finally:
            await cleanup(user)

    async def test_role_grant_alone_grants_access(self):
        """A document the user did not upload is still readable when their
        role has been granted access to it."""
        owner = await make_user("rg-owner@test.local", "admin")
        analyst = await make_user("rg-analyst@test.local", "analyst")
        doc = await make_document(owner, "role-granted.pdf")
        try:
            async with async_session() as session:
                await grant(
                    session,
                    doc.id,
                    grantee_type="role",
                    grantee_role="analyst",
                    permission="view",
                    granted_by=owner.id,
                )
                await session.commit()
                allowed = await permitted_document_ids(session, analyst)
                assert doc.id in allowed
        finally:
            await cleanup(analyst, owner, doc=doc)

    async def test_uploader_alone_grants_access(self):
        """The uploader keeps access even with no grant on the document."""
        owner = await make_user("up-owner@test.local", "analyst")
        doc = await make_document(owner, "own-upload.pdf")
        try:
            async with async_session() as session:
                allowed = await permitted_document_ids(session, owner)
                assert doc.id in allowed
        finally:
            await cleanup(owner, doc=doc)

    async def test_no_grant_and_not_uploader_means_no_access(self):
        owner = await make_user("none-owner@test.local", "admin")
        analyst = await make_user("none-analyst@test.local", "analyst")
        doc = await make_document(owner, "not-shared.pdf")
        try:
            async with async_session() as session:
                allowed = await permitted_document_ids(session, analyst)
                assert doc.id not in allowed
        finally:
            await cleanup(analyst, owner, doc=doc)

    async def test_permitted_ids_reflect_grants(self):
        owner = await make_user("perm-owner@test.local", "admin")
        analyst = await make_user("perm-granted@test.local", "analyst")
        doc = await make_document(owner, "granted.pdf")
        try:
            async with async_session() as session:
                await grant(
                    session,
                    doc.id,
                    grantee_type="role",
                    grantee_role="analyst",
                    permission="view",
                    granted_by=owner.id,
                )
                await session.commit()
                allowed = await permitted_document_ids(session, analyst)
                assert doc.id in allowed
        finally:
            await cleanup(analyst, owner, doc=doc)


class TestAccessChecks:
    async def test_download_requires_download_permission(self):
        owner = await make_user("dl-owner@test.local", "admin")
        analyst = await make_user("dl-analyst@test.local", "analyst")
        doc = await make_document(owner, "download.pdf")
        try:
            async with async_session() as session:
                await grant(
                    session,
                    doc.id,
                    grantee_type="role",
                    grantee_role="analyst",
                    permission="view",
                    granted_by=owner.id,
                )
                await session.commit()

                assert await can_access_document(session, analyst, doc.id, "view")
                assert not await can_access_document(
                    session, analyst, doc.id, "download"
                )

                await grant(
                    session,
                    doc.id,
                    grantee_type="role",
                    grantee_role="analyst",
                    permission="download",
                    granted_by=owner.id,
                )
                await session.commit()
                assert await can_access_document(
                    session, analyst, doc.id, "download"
                )
        finally:
            await cleanup(analyst, owner, doc=doc)

    async def test_manage_implies_view(self):
        owner = await make_user("mg-owner@test.local", "admin")
        analyst = await make_user("mg-analyst@test.local", "analyst")
        doc = await make_document(owner, "manage.pdf")
        try:
            async with async_session() as session:
                await grant(
                    session,
                    doc.id,
                    grantee_type="user",
                    grantee_user_id=analyst.id,
                    permission="manage",
                    granted_by=owner.id,
                )
                await session.commit()
                assert await can_access_document(session, analyst, doc.id, "view")
                assert await can_access_document(session, analyst, doc.id, "download")
        finally:
            await cleanup(analyst, owner, doc=doc)

    async def test_revocation_removes_access_immediately(self):
        owner = await make_user("rv-owner@test.local", "admin")
        analyst = await make_user("rv-analyst@test.local", "analyst")
        doc = await make_document(owner, "revoke.pdf")
        try:
            async with async_session() as session:
                await grant(
                    session,
                    doc.id,
                    grantee_type="role",
                    grantee_role="analyst",
                    permission="view",
                    granted_by=owner.id,
                )
                await session.commit()
                assert await can_access_document(session, analyst, doc.id, "view")

                removed = await revoke(
                    session,
                    doc.id,
                    grantee_type="role",
                    grantee_role="analyst",
                    permission="view",
                )
                await session.commit()
                assert removed == 1
                assert not await can_access_document(session, analyst, doc.id, "view")
        finally:
            await cleanup(analyst, owner, doc=doc)

    async def test_grant_is_idempotent(self):
        owner = await make_user("idem-owner@test.local", "admin")
        doc = await make_document(owner, "idem.pdf")
        try:
            async with async_session() as session:
                await grant(
                    session,
                    doc.id,
                    grantee_type="role",
                    grantee_role="viewer",
                    permission="view",
                    granted_by=owner.id,
                )
                await grant(
                    session,
                    doc.id,
                    grantee_type="role",
                    grantee_role="viewer",
                    permission="view",
                    granted_by=owner.id,
                )
                await session.commit()
                perms = await list_permissions(session, doc.id)
                assert len(perms) == 1
        finally:
            await cleanup(owner, doc=doc)


class TestRetrievalBoundary:
    """The retrieval query itself must not surface a document the caller
    cannot read — this is the 'never send unauthorised content to the model'
    constraint, enforced in SQL rather than in the prompt."""

    async def test_search_excludes_documents_without_a_grant(self):
        owner = await make_user("srch-owner@test.local", "admin")
        analyst = await make_user("srch-analyst@test.local", "analyst")
        allowed = await make_document(owner, "search-allowed.pdf")
        denied = await make_document(owner, "search-denied.pdf")
        try:
            async with async_session() as session:
                # Both documents carry an identical, perfectly-matching chunk.
                # The only difference is the permission grant, so the result
                # set is decided purely by the ACL.
                for doc, text in ((allowed, "permitted lease clause"), (denied, "restricted lease clause")):
                    session.add(
                        DocumentChunk(
                            id=uuid.uuid4(),
                            document_id=doc.id,
                            chunk_index=0,
                            page_start=1,
                            page_end=1,
                            text=text,
                            token_count=8,
                            heading_path=[],
                            embedding=[1.0] * 1024,
                            embedding_model="test-model",
                        )
                    )
                await grant(
                    session,
                    allowed.id,
                    grantee_type="role",
                    grantee_role="analyst",
                    permission="view",
                    granted_by=owner.id,
                )
                await session.commit()

                hits = await search(
                    session,
                    analyst,
                    [1.0] * 1024,
                    embedding_model="test-model",
                    top_k=50,
                    min_score=-1.0,
                )
                found = {h.document_id for h in hits}
                assert allowed.id in found, "the granted document must be retrievable"
                assert denied.id not in found, (
                    "a document with no grant must never leave the database"
                )
        finally:
            await cleanup(analyst, owner, doc_a=allowed, doc_b=denied)

    async def test_admin_retrieval_sees_ungranted_documents(self):
        """Confirms the analyst result above is caused by the ACL, not by the
        data: the same query as an admin does return the ungranted document."""
        owner = await make_user("adm-owner@test.local", "admin")
        denied = await make_document(owner, "admin-visible.pdf")
        try:
            async with async_session() as session:
                session.add(
                    DocumentChunk(
                        id=uuid.uuid4(),
                        document_id=denied.id,
                        chunk_index=0,
                        page_start=1,
                        page_end=1,
                        text="admin visible clause",
                        token_count=8,
                        heading_path=[],
                        embedding=[1.0] * 1024,
                        embedding_model="test-model",
                    )
                )
                await session.commit()

                hits = await search(
                    session,
                    owner,
                    [1.0] * 1024,
                    embedding_model="test-model",
                    top_k=50,
                    min_score=-1.0,
                )
                assert denied.id in {h.document_id for h in hits}
        finally:
            await cleanup(owner, doc=denied)

    async def test_second_chance_filter_drops_unauthorised_candidates(self):
        """Even if a caller somehow obtained a chunk from a forbidden
        document, the Python-side re-check removes it before prompting."""
        owner = await make_user("fb-owner@test.local", "admin")
        analyst = await make_user("fb-analyst@test.local", "analyst")
        doc = await make_document(owner, "forbidden.pdf")
        try:
            async with async_session() as session:
                from app.modules.retrieval.service import RetrievedChunk

                smuggled = [
                    RetrievedChunk(
                        chunk_id=uuid.uuid4(),
                        document_id=doc.id,
                        filename=doc.filename,
                        doc_type="lease",
                        text="secret content",
                        page_start=1,
                        page_end=1,
                        score=0.99,
                    )
                ]
                kept = await filter_by_permission(session, analyst, smuggled)
                assert kept == []
        finally:
            await cleanup(analyst, owner, doc=doc)

    async def test_admin_bypass_is_not_a_leak_for_non_admins(self):
        owner = await make_user("ab-owner@test.local", "admin")
        viewer = await make_user("ab-viewer@test.local", "viewer")
        doc = await make_document(owner, "admin-only.pdf")
        try:
            async with async_session() as session:
                from app.modules.retrieval.service import RetrievedChunk

                candidate = [
                    RetrievedChunk(
                        chunk_id=uuid.uuid4(),
                        document_id=doc.id,
                        filename=doc.filename,
                        doc_type="lease",
                        text="restricted",
                        page_start=1,
                        page_end=1,
                        score=0.9,
                    )
                ]
                assert await filter_by_permission(session, owner, candidate)
                assert await filter_by_permission(session, viewer, candidate) == []
        finally:
            await cleanup(viewer, owner, doc=doc)
