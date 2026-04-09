"""文档仓储。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentStatus


class DocumentRepository:
    async def create_document(
        self,
        db: AsyncSession,
        *,
        title: str,
        source: str | None,
        file_path: str,
        authority_score: float,
        uploaded_by: int,
        status: DocumentStatus,
        published_at: datetime | None = None,
    ) -> Document:
        document = Document(
            title=title,
            source=source,
            file_path=file_path,
            authority_score=authority_score,
            uploaded_by=uploaded_by,
            status=status,
            published_at=published_at,
        )
        db.add(document)
        await db.flush()
        await db.refresh(document, attribute_names=["uploader"])
        return document

    async def list_documents(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        status: str | None = None,
    ) -> tuple[list[Document], int]:
        stmt = select(Document).options(selectinload(Document.uploader)).order_by(Document.created_at.desc())
        count_stmt = select(func.count(Document.id))
        if status:
            doc_status = DocumentStatus(status)
            stmt = stmt.where(Document.status == doc_status)
            count_stmt = count_stmt.where(Document.status == doc_status)
        stmt = stmt.offset((page - 1) * size).limit(size)
        documents = list((await db.scalars(stmt)).all())
        total = int(await db.scalar(count_stmt) or 0)
        return documents, total

    async def get_by_doc_id(self, db: AsyncSession, doc_id: str) -> Document | None:
        stmt = (
            select(Document)
            .options(selectinload(Document.uploader), selectinload(Document.chunks))
            .where(Document.doc_id == doc_id)
        )
        return await db.scalar(stmt)

    async def count_documents(self, db: AsyncSession) -> int:
        return int(await db.scalar(select(func.count(Document.id))) or 0)

    async def count_by_status(self, db: AsyncSession, status: DocumentStatus) -> int:
        stmt = select(func.count(Document.id)).where(Document.status == status)
        return int(await db.scalar(stmt) or 0)

    async def update_status(
        self,
        db: AsyncSession,
        *,
        document: Document,
        status: DocumentStatus,
    ) -> Document:
        document.status = status
        if status == DocumentStatus.PUBLISHED:
            document.published_at = datetime.utcnow()
        await db.flush()
        await db.refresh(document, attribute_names=["uploader"])
        return document


document_repo = DocumentRepository()
