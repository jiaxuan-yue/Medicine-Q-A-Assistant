"""分块仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus


class ChunkRepository:
    async def bulk_create_chunks(
        self,
        db: AsyncSession,
        *,
        doc_id: str,
        chunks: list[dict],
    ) -> list[Chunk]:
        instances: list[Chunk] = []
        for item in chunks:
            chunk = Chunk(
                doc_id=doc_id,
                chunk_index=item["chunk_index"],
                chunk_text=item["chunk_text"],
                token_count=item.get("token_count"),
                metadata_json=item.get("metadata_json"),
            )
            db.add(chunk)
            instances.append(chunk)
        await db.flush()
        return instances

    async def list_retrieval_candidates(self, db: AsyncSession) -> list[tuple[Chunk, Document]]:
        stmt = (
            select(Chunk, Document)
            .join(Document, Document.doc_id == Chunk.doc_id)
            .where(Document.status == DocumentStatus.PUBLISHED)
            .order_by(Document.authority_score.desc(), Chunk.chunk_index.asc())
        )
        result = await db.execute(stmt)
        return list(result.all())


chunk_repo = ChunkRepository()
