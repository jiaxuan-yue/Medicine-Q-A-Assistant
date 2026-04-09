"""Document ingestion Celery tasks.

Full pipeline: parse → chunk → embed → index (ES + FAISS) → build graph → update status.
"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import get_sync_session
from app.integrations.embedding_client import EmbeddingClient
from app.integrations.es_client import ESClient, TCM_CHUNKS_INDEX
from app.integrations.neo4j_client import Neo4jClient
from app.integrations.vector_store import VectorStore
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.services.chunking_service import chunking_service
from app.tasks import celery_app

logger = get_logger(__name__)


# ── Helpers ──────────────────────────────────────────────────

def _extract_text(file_path: str) -> str:
    """Read a document file and return plain text."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document file not found: {file_path}")

    suffix = path.suffix.lower()
    file_bytes = path.read_bytes()

    if suffix in {".txt", ".md", ".markdown"}:
        for encoding in ("utf-8", "gb18030", "gbk"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue

    # Fallback: best-effort UTF-8
    decoded = file_bytes.decode("utf-8", errors="ignore").strip()
    if decoded:
        return decoded

    raise ValueError(f"Cannot extract text from file: {file_path}")


def _run_async(coro):
    """Run an async coroutine in a sync Celery task context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── Main ingestion task ──────────────────────────────────────

@celery_app.task(
    bind=True,
    name="ingest_document",
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(ConnectionError, OSError),
)
def ingest_document(self, doc_id: str, file_path: str):
    """Full document ingestion pipeline.

    Steps:
        1. Read and parse the document file
        2. Split text into chunks
        3. Store chunks in DB
        4. Generate embeddings for each chunk
        5. Index chunks in Elasticsearch
        6. Add vectors to FAISS index
        7. Extract entities and build knowledge graph
        8. Update document status to PUBLISHED
    """
    logger.info("[ingest] START doc_id=%s file=%s", doc_id, file_path)

    try:
        # ── 1. Update status to PROCESSING ──────────────────
        _update_document_status(doc_id, DocumentStatus.PROCESSING)
        logger.info("[ingest] step 1/8: status → PROCESSING")

        # ── 2. Extract text ─────────────────────────────────
        text = _extract_text(file_path)
        logger.info("[ingest] step 2/8: extracted text (%d chars)", len(text))

        # ── 3. Split into chunks ────────────────────────────
        chunk_dicts = chunking_service.chunk_text(text)
        if not chunk_dicts:
            logger.warning("[ingest] no chunks produced, marking FAILED")
            _update_document_status(doc_id, DocumentStatus.FAILED)
            return {"status": "failed", "reason": "no chunks produced"}
        logger.info("[ingest] step 3/8: produced %d chunks", len(chunk_dicts))

        # ── 4. Persist chunks to DB ─────────────────────────
        chunk_records = _save_chunks_to_db(doc_id, chunk_dicts)
        logger.info("[ingest] step 4/8: saved %d chunks to DB", len(chunk_records))

        # ── 5. Generate embeddings ──────────────────────────
        chunk_texts = [c["chunk_text"] for c in chunk_dicts]
        embedding_client = EmbeddingClient()
        embeddings = _run_async(embedding_client.embed_texts(chunk_texts))
        logger.info("[ingest] step 5/8: generated %d embeddings", len(embeddings))

        # ── 6. Index in Elasticsearch ───────────────────────
        doc_title = _get_document_title(doc_id)
        es_docs = []
        for i, chunk_rec in enumerate(chunk_records):
            es_docs.append({
                "chunk_id": chunk_rec["chunk_id"],
                "doc_id": doc_id,
                "doc_title": doc_title,
                "chunk_text": chunk_dicts[i]["chunk_text"],
                "metadata": chunk_dicts[i].get("metadata_json", {}),
            })
        es_count = _run_async(_index_in_es(es_docs))
        logger.info("[ingest] step 6/8: indexed %d chunks in ES", es_count)

        # ── 7. Add vectors to FAISS ─────────────────────────
        faiss_meta = []
        for i, chunk_rec in enumerate(chunk_records):
            faiss_meta.append({
                "chunk_id": chunk_rec["chunk_id"],
                "doc_id": doc_id,
                "doc_title": doc_title,
                "chunk_text": chunk_dicts[i]["chunk_text"],
                "metadata": chunk_dicts[i].get("metadata_json", {}),
            })
        _run_async(_add_to_vector_store(embeddings, faiss_meta))
        logger.info("[ingest] step 7/8: added %d vectors to FAISS", len(embeddings))

        # ── 8. Build knowledge graph ────────────────────────
        graph_chunks = []
        for i, chunk_rec in enumerate(chunk_records):
            graph_chunks.append({
                "chunk_id": chunk_rec["chunk_id"],
                "doc_id": doc_id,
                "doc_title": doc_title,
                "chunk_text": chunk_dicts[i]["chunk_text"],
            })
        graph_result = _run_async(_build_graph(graph_chunks))
        logger.info(
            "[ingest] step 8/8: graph built — %d entities, %d relations",
            graph_result.get("entities_created", 0),
            graph_result.get("relations_created", 0),
        )

        # ── 9. Mark as PUBLISHED ────────────────────────────
        _update_document_status(doc_id, DocumentStatus.PUBLISHED)
        logger.info("[ingest] DONE doc_id=%s — PUBLISHED", doc_id)

        return {
            "status": "success",
            "doc_id": doc_id,
            "chunks": len(chunk_dicts),
            "embeddings": len(embeddings),
            "es_indexed": es_count,
            "graph": graph_result,
        }

    except self.MaxRetriesExceededError:
        logger.error("[ingest] FAILED doc_id=%s — max retries exceeded", doc_id)
        _update_document_status(doc_id, DocumentStatus.FAILED)
        return {"status": "failed", "reason": "max retries exceeded"}

    except Exception as exc:
        logger.error(
            "[ingest] FAILED doc_id=%s — %s\n%s",
            doc_id, exc, traceback.format_exc(),
        )
        _update_document_status(doc_id, DocumentStatus.FAILED)
        # Retry on transient errors
        if isinstance(exc, (ConnectionError, OSError)):
            raise self.retry(exc=exc)
        return {"status": "failed", "reason": str(exc)}


# ── DB helpers (synchronous) ─────────────────────────────────

def _update_document_status(doc_id: str, status: DocumentStatus) -> None:
    """Update document status using a sync DB session."""
    with get_sync_session() as session:
        doc = session.execute(
            select(Document).where(Document.doc_id == doc_id)
        ).scalar_one_or_none()
        if doc:
            doc.status = status
            if status == DocumentStatus.PUBLISHED:
                doc.published_at = datetime.utcnow()
            session.flush()


def _save_chunks_to_db(doc_id: str, chunk_dicts: list[dict]) -> list[dict]:
    """Persist chunks to DB and return list of {chunk_id, chunk_index}."""
    records = []
    with get_sync_session() as session:
        for item in chunk_dicts:
            chunk = Chunk(
                doc_id=doc_id,
                chunk_index=item["chunk_index"],
                chunk_text=item["chunk_text"],
                token_count=item.get("token_count"),
                metadata_json=item.get("metadata_json"),
            )
            session.add(chunk)
            session.flush()
            records.append({
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
            })
    return records


def _get_document_title(doc_id: str) -> str:
    """Look up document title by doc_id."""
    with get_sync_session() as session:
        doc = session.execute(
            select(Document).where(Document.doc_id == doc_id)
        ).scalar_one_or_none()
        return doc.title if doc else ""


# ── Async integration helpers ────────────────────────────────

async def _index_in_es(documents: list[dict]) -> int:
    """Init a temporary ES client, bulk-index, then close."""
    client = ESClient()
    try:
        await client.init()
        if not client.available:
            logger.warning("[ingest] ES unavailable, skipping indexing")
            return 0
        await client.create_index(TCM_CHUNKS_INDEX)
        count = await client.bulk_index(TCM_CHUNKS_INDEX, documents)
        return count
    finally:
        await client.close()


async def _add_to_vector_store(
    embeddings: list[list[float]], metadata: list[dict]
) -> None:
    """Add vectors to a FAISS index and persist to disk."""
    store = VectorStore()
    store.load()  # load existing index if present
    await store.add_vectors(embeddings, metadata)
    store.save()


async def _build_graph(chunks: list[dict]) -> dict:
    """Init Neo4j, build graph from chunks, then close."""
    from app.services.graph_build_service import (
        build_graph_from_chunks,
        extract_entities,
        extract_relations,
    )
    from app.integrations.neo4j_client import neo4j_client as _neo4j_singleton

    client = Neo4jClient()
    try:
        await client.init()
        if not client.available:
            logger.warning("[ingest] Neo4j unavailable, skipping graph build")
            return {"entities_created": 0, "relations_created": 0}
        # Use the module-level function which internally uses the neo4j_client singleton.
        # We need to temporarily set the singleton for graph_build_service.
        import app.integrations.neo4j_client as neo4j_mod
        original = neo4j_mod.neo4j_client
        neo4j_mod.neo4j_client = client
        try:
            result = await build_graph_from_chunks(chunks)
        finally:
            neo4j_mod.neo4j_client = original
        return result
    finally:
        await client.close()


# ── Batch ingestion task ─────────────────────────────────────

@celery_app.task(name="batch_ingest")
def batch_ingest(file_paths: list[str]):
    """Dispatch individual ingest_document tasks for each file.

    Creates a document record for each file, then dispatches
    an ingest_document task.

    Args:
        file_paths: List of absolute paths to document files.

    Returns:
        dict with dispatched task IDs.
    """
    logger.info("[batch] dispatching %d files", len(file_paths))
    task_ids = []

    for fp in file_paths:
        path = Path(fp)
        if not path.exists():
            logger.warning("[batch] file not found, skipping: %s", fp)
            continue

        # Create a minimal document record
        with get_sync_session() as session:
            doc = Document(
                title=path.stem,
                source="batch_import",
                file_path=str(path),
                authority_score=0.75,
                uploaded_by=1,  # system user
                status=DocumentStatus.PENDING,
            )
            session.add(doc)
            session.flush()
            doc_id = doc.doc_id

        result = ingest_document.delay(doc_id, str(path))
        task_ids.append({"doc_id": doc_id, "task_id": result.id})
        logger.info("[batch] dispatched doc_id=%s task_id=%s", doc_id, result.id)

    return {"dispatched": len(task_ids), "tasks": task_ids}
