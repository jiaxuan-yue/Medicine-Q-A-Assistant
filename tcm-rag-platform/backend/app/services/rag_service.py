"""RAG 编排服务。"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from app.schemas.chat import Citation
from app.schemas.rag import QueryRewriteResult, RetrievalHit
from app.services.answer_service import compose_answer
from app.services.query_rewrite_service import rewrite_query
from app.services.retrieval_service import build_citations, retrieve_documents


@dataclass
class AnswerPackage:
    query_bundle: QueryRewriteResult
    hits: list[RetrievalHit]
    citations: list[Citation]
    answer: str
    latency_ms: int


def generate_answer_package(
    query: str,
    history_summary: str | None = None,
    top_k: int = 5,
) -> AnswerPackage:
    started_at = perf_counter()
    query_bundle = rewrite_query(query, history_summary=history_summary)
    hits = retrieve_documents(query_bundle, top_k=top_k)
    citations = build_citations(hits)
    answer = compose_answer(query, query_bundle, hits)
    latency_ms = int((perf_counter() - started_at) * 1000)
    return AnswerPackage(
        query_bundle=query_bundle,
        hits=hits,
        citations=citations,
        answer=answer,
        latency_ms=latency_ms,
    )
