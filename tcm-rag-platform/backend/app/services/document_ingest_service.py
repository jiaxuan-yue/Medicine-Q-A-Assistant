"""文档上传与入库服务。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.db.repositories.chunk_repo import chunk_repo
from app.db.repositories.document_repo import document_repo
from app.models.document import DocumentStatus
from app.services.chunking_service import chunking_service

logger = get_logger(__name__)


class DocumentIngestService:
    """Document upload and ingestion service.

    Supports two modes:
    - Async (Celery): saves file + DB record, dispatches background task
    - Sync fallback: inline chunking when Redis/Celery is unavailable
    """

    # ── Primary upload entry point ──────────────────────────

    async def ingest_upload(
        self,
        db: AsyncSession,
        *,
        uploaded_by: int,
        file: UploadFile,
        use_celery: bool = True,
    ):
        """Upload a document file and trigger ingestion.

        When *use_celery* is True (default), the document is saved as PENDING
        and a Celery task is dispatched for background processing.  If Celery/Redis
        is unavailable, falls back to synchronous inline processing.
        """
        raw_dir = Path(settings.RAW_DOCUMENTS_DIR)
        raw_dir.mkdir(parents=True, exist_ok=True)

        file_bytes = await file.read()
        filename = file.filename or f"document-{datetime.utcnow().timestamp()}.txt"
        target_path = raw_dir / filename
        target_path.write_bytes(file_bytes)

        if use_celery and self._celery_available():
            # ── Async path: create PENDING doc → dispatch Celery task
            document = await document_repo.create_document(
                db,
                title=Path(filename).stem,
                source="uploaded_file",
                file_path=str(target_path),
                authority_score=0.75,
                uploaded_by=uploaded_by,
                status=DocumentStatus.PENDING,
            )
            await db.commit()

            from app.tasks.ingest_tasks import ingest_document
            task_result = ingest_document.delay(document.doc_id, str(target_path))
            logger.info(
                "Celery task dispatched: doc_id=%s task_id=%s",
                document.doc_id, task_result.id,
            )
            return document
        else:
            # ── Sync fallback: inline processing
            return await self._ingest_sync(
                db,
                uploaded_by=uploaded_by,
                filename=filename,
                file_bytes=file_bytes,
                target_path=target_path,
            )

    # ── Sync fallback (original behaviour) ──────────────────

    async def _ingest_sync(
        self,
        db: AsyncSession,
        *,
        uploaded_by: int,
        filename: str,
        file_bytes: bytes,
        target_path: Path,
    ):
        """Inline chunking — no Celery required."""
        text = self._extract_text(filename, file_bytes)
        chunks = chunking_service.chunk_text(text)
        status = DocumentStatus.PUBLISHED if chunks else DocumentStatus.PENDING
        document = await document_repo.create_document(
            db,
            title=Path(filename).stem,
            source="uploaded_file",
            file_path=str(target_path),
            authority_score=0.75,
            uploaded_by=uploaded_by,
            status=status,
            published_at=datetime.utcnow() if chunks else None,
        )
        if chunks:
            await chunk_repo.bulk_create_chunks(db, doc_id=document.doc_id, chunks=chunks)
        return document

    # ── Task status query ───────────────────────────────────

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Check the status of an ingest Celery task via the result backend.

        Returns:
            {"task_id": str, "status": str, "result": Any}
        """
        try:
            from app.tasks import celery_app
            result = celery_app.AsyncResult(task_id)
            return {
                "task_id": task_id,
                "status": result.status,
                "result": result.result if result.ready() else None,
            }
        except Exception as exc:
            logger.warning("Failed to query task status: %s", exc)
            return {
                "task_id": task_id,
                "status": "UNKNOWN",
                "result": None,
            }

    # ── Utilities ───────────────────────────────────────────

    @staticmethod
    def _celery_available() -> bool:
        """Check whether Celery broker (Redis) is reachable."""
        try:
            from app.tasks import celery_app
            conn = celery_app.connection()
            conn.ensure_connection(max_retries=1, timeout=2)
            conn.close()
            return True
        except Exception:
            logger.warning("Celery/Redis unavailable — falling back to sync ingest")
            return False

    @staticmethod
    def _extract_text(filename: str, file_bytes: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            for encoding in ("utf-8", "gb18030", "gbk"):
                try:
                    return file_bytes.decode(encoding)
                except UnicodeDecodeError:
                    continue
        try:
            decoded = file_bytes.decode("utf-8", errors="ignore").strip()
        except OSError:
            decoded = ""
        if decoded:
            return decoded
        return (
            "文件已上传，但当前 MVP 版本仅对 TXT/Markdown 自动抽取正文。"
            "其余格式已保存原文件，后续可接入 OCR/Office 解析。"
        )


document_ingest_service = DocumentIngestService()
