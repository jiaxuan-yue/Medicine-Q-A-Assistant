"""Celery Beat schedule — periodic maintenance tasks."""

from __future__ import annotations

from celery.schedules import crontab

from app.tasks import celery_app

# ── Periodic tasks ───────────────────────────────────────────

celery_app.conf.beat_schedule = {
    "rebuild-faiss-index-nightly": {
        "task": "rebuild_faiss_index",
        "schedule": crontab(hour=2, minute=0),  # every day at 02:00 Asia/Shanghai
        "options": {"queue": "maintenance"},
    },
    "update-graph-from-new-chunks": {
        "task": "update_graph_incremental",
        "schedule": crontab(hour=3, minute=0),  # every day at 03:00
        "options": {"queue": "maintenance"},
    },
}

celery_app.conf.task_routes = {
    "rebuild_faiss_index": {"queue": "maintenance"},
    "update_graph_incremental": {"queue": "maintenance"},
    "ingest_document": {"queue": "default"},
    "batch_ingest": {"queue": "default"},
}


# ── Maintenance task implementations ────────────────────────

@celery_app.task(name="rebuild_faiss_index")
def rebuild_faiss_index():
    """Rebuild the FAISS index from all published chunks in the DB.

    Runs nightly to ensure the index stays consistent with the database.
    """
    import asyncio
    from app.core.logger import get_logger
    from app.db.session import get_sync_session
    from app.integrations.embedding_client import EmbeddingClient
    from app.integrations.vector_store import VectorStore
    from app.models.chunk import Chunk
    from app.models.document import Document, DocumentStatus

    logger = get_logger(__name__)
    logger.info("[maintenance] rebuild_faiss_index START")

    try:
        # Collect all published chunks
        from sqlalchemy import select
        with get_sync_session() as session:
            stmt = (
                select(Chunk, Document)
                .join(Document, Document.doc_id == Chunk.doc_id)
                .where(Document.status == DocumentStatus.PUBLISHED)
                .order_by(Document.authority_score.desc(), Chunk.chunk_index.asc())
            )
            rows = session.execute(stmt).all()

        if not rows:
            logger.info("[maintenance] no published chunks, skipping rebuild")
            return {"status": "skipped", "reason": "no chunks"}

        chunk_texts = [row[0].chunk_text for row in rows]
        metadata = []
        for chunk_obj, doc_obj in rows:
            metadata.append({
                "chunk_id": chunk_obj.chunk_id,
                "doc_id": chunk_obj.doc_id,
                "doc_title": doc_obj.title,
                "chunk_text": chunk_obj.chunk_text,
                "metadata": chunk_obj.metadata_json or {},
            })

        # Generate embeddings
        client = EmbeddingClient()

        def _run(coro):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)

        embeddings = _run(client.embed_texts(chunk_texts))

        # Build fresh index
        store = VectorStore()
        _run(store.build_index(embeddings, metadata))
        store.save()

        logger.info(
            "[maintenance] rebuild_faiss_index DONE — %d vectors", len(embeddings)
        )
        return {"status": "success", "vectors": len(embeddings)}

    except Exception as exc:
        logger.error("[maintenance] rebuild_faiss_index FAILED: %s", exc)
        return {"status": "failed", "reason": str(exc)}


@celery_app.task(name="update_graph_incremental")
def update_graph_incremental():
    """Process recently added chunks that haven't been graph-indexed yet.

    Checks for chunks created in the last 24 hours and builds graph entries.
    """
    import asyncio
    from datetime import timedelta
    from app.core.logger import get_logger
    from app.db.session import get_sync_session
    from app.models.chunk import Chunk
    from app.models.document import Document, DocumentStatus

    logger = get_logger(__name__)
    logger.info("[maintenance] update_graph_incremental START")

    try:
        from sqlalchemy import select
        cutoff = datetime.utcnow() - timedelta(hours=25)

        with get_sync_session() as session:
            stmt = (
                select(Chunk, Document)
                .join(Document, Document.doc_id == Chunk.doc_id)
                .where(
                    Document.status == DocumentStatus.PUBLISHED,
                    Chunk.created_at >= cutoff,
                )
                .order_by(Chunk.created_at.asc())
            )
            rows = session.execute(stmt).all()

        if not rows:
            logger.info("[maintenance] no new chunks, skipping graph update")
            return {"status": "skipped", "reason": "no new chunks"}

        graph_chunks = []
        for chunk_obj, doc_obj in rows:
            graph_chunks.append({
                "chunk_id": chunk_obj.chunk_id,
                "doc_id": chunk_obj.doc_id,
                "doc_title": doc_obj.title,
                "chunk_text": chunk_obj.chunk_text,
            })

        from app.services.graph_build_service import build_graph_from_chunks
        from app.integrations.neo4j_client import Neo4jClient

        def _run(coro):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)

        async def _do_graph():
            client = Neo4jClient()
            await client.init()
            if not client.available:
                logger.warning("[maintenance] Neo4j unavailable")
                return {"entities_created": 0, "relations_created": 0}
            import app.integrations.neo4j_client as neo4j_mod
            original = neo4j_mod.neo4j_client
            neo4j_mod.neo4j_client = client
            try:
                return await build_graph_from_chunks(graph_chunks)
            finally:
                neo4j_mod.neo4j_client = original
                await client.close()

        result = _run(_do_graph())
        logger.info(
            "[maintenance] update_graph DONE — %d entities, %d relations",
            result.get("entities_created", 0),
            result.get("relations_created", 0),
        )
        return {"status": "success", **result}

    except Exception as exc:
        logger.error("[maintenance] update_graph FAILED: %s", exc)
        return {"status": "failed", "reason": str(exc)}


# Import datetime at module level for update_graph_incremental
from datetime import datetime  # noqa: E402
