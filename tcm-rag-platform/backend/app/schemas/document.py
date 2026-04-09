"""文档相关 schema。"""

from pydantic import BaseModel


class DocumentOut(BaseModel):
    doc_id: str
    title: str
    source: str
    version: int
    status: str
    authority_score: float
    uploaded_by: str
    published_at: str | None
    created_at: str
    excerpt: str | None = None


class DocumentReviewRequest(BaseModel):
    action: str
    comment: str | None = None
