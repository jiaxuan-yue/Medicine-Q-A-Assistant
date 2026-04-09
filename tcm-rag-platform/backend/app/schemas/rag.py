"""RAG 相关 schema。"""

from pydantic import BaseModel

from app.schemas.chat import Citation


class QueryRewriteResult(BaseModel):
    raw_query: str
    normalized_query: str
    rewrite_queries: list[str]
    entities: list[str]
    intent: str


class RetrievalHit(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    source: str
    retrieval_source: str
    score: float
    reason: str
    text: str


class RagQueryRequest(BaseModel):
    query: str
    session_summary: str | None = None
    top_k: int = 5


class RetrievalPreviewResponse(BaseModel):
    query_bundle: QueryRewriteResult
    hits: list[RetrievalHit]


class AnswerPreviewResponse(BaseModel):
    query_bundle: QueryRewriteResult
    answer: str
    citations: list[Citation]
    hits: list[RetrievalHit]
    latency_ms: int
