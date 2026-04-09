"""文档与管理台视图服务。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.document_repo import document_repo
from app.db.repositories.session_repo import session_repo
from app.db.repositories.user_repo import user_repo
from app.models.document import DocumentStatus
from app.models.feedback import Feedback, FeedbackType


def serialize_document(document) -> dict:
    uploader_name = document.uploader.username if getattr(document, "uploader", None) else "-"
    return {
        "doc_id": document.doc_id,
        "title": document.title,
        "source": document.source,
        "version": document.version,
        "status": document.status.value if hasattr(document.status, "value") else str(document.status),
        "authority_score": float(document.authority_score),
        "uploaded_by": uploader_name,
        "published_at": document.published_at,
        "created_at": document.created_at,
    }


class DocumentService:
    async def build_dashboard_stats(self, db: AsyncSession) -> dict:
        positive_count = int(
            await db.scalar(
                select(func.count(Feedback.id)).where(Feedback.feedback_type == FeedbackType.THUMBS_UP)
            )
            or 0
        )
        negative_count = int(
            await db.scalar(
                select(func.count(Feedback.id)).where(Feedback.feedback_type == FeedbackType.THUMBS_DOWN)
            )
            or 0
        )
        feedback_total = positive_count + negative_count
        positive_rate = positive_count / feedback_total if feedback_total else 0.0
        return {
            "total_users": await user_repo.count_users(db),
            "total_documents": await document_repo.count_documents(db),
            "total_sessions": await session_repo.count_sessions(db),
            "total_messages": await session_repo.count_messages(db),
            "documents_pending_review": await document_repo.count_by_status(db, DocumentStatus.PENDING),
            "feedback_positive_rate": round(positive_rate, 4),
        }


document_service = DocumentService()
