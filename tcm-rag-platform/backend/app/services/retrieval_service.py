"""混合检索服务 — 稀疏 (ES BM25) + 稠密 (FAISS) + 图谱 (Neo4j) + RRF 融合。

对外保留 retrieve_documents / build_citations 兼容原有调用。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from app.core.config import settings
from app.core.logger import get_logger
from app.integrations.embedding_client import embedding_client
from app.integrations.es_client import ESClient, TCM_CHUNKS_INDEX, es_client
from app.integrations.neo4j_client import Neo4jClient, neo4j_client
from app.integrations.vector_store import VectorStore, vector_store
from app.schemas.chat import Citation
from app.schemas.rag import QueryRewriteResult, RetrievalHit
from app.services.store import store
from app.services.text_normalization_service import expand_script_variants

logger = get_logger(__name__)


class RetrievalService:
    """Triple-channel retrieval with RRF fusion and graceful fallback."""

    def __init__(
        self,
        es: ESClient | None = None,
        vs: VectorStore | None = None,
        neo4j: Neo4jClient | None = None,
    ) -> None:
        self._es = es or es_client
        self._vs = vs or vector_store
        self._neo4j = neo4j or neo4j_client

    # ── public API ──────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        rewrite_result: QueryRewriteResult,
        top_k: int | None = None,
    ) -> dict:
        """Run triple retrieval and return a RetrievalBundle dict.

        Returns:
            {sparse_docs, dense_docs, graph_docs, fused_docs}
        """
        fusion_k = top_k or settings.FUSION_TOP_K
        queries = rewrite_result.rewrite_queries or [rewrite_result.normalized_query]
        entities = rewrite_result.entities or []

        # Run retrieval channels in parallel
        tasks: dict[str, asyncio.Task] = {}
        async with asyncio.TaskGroup() as tg:
            tasks["sparse"] = tg.create_task(
                self._sparse_retrieve(queries, settings.SPARSE_TOP_K)
            )
            tasks["dense"] = tg.create_task(
                self._dense_retrieve(rewrite_result.normalized_query, settings.DENSE_TOP_K)
            )
            if settings.GRAPH_RECALL_ENABLED and entities:
                tasks["graph"] = tg.create_task(
                    self._graph_retrieve(entities, settings.GRAPH_TOP_K)
                )

        sparse_docs = tasks["sparse"].result()
        dense_docs = tasks["dense"].result()
        graph_docs = tasks.get("graph", _EmptyResult()).result() if "graph" in tasks else []

        fused_docs = await self._fuse_results(sparse_docs, dense_docs, graph_docs, fusion_k)

        # If all channels empty, fall back to in-memory keyword search
        if not fused_docs:
            logger.info("所有检索通道为空，降级到内存关键词检索")
            fused_docs = _fallback_keyword_search(rewrite_result, fusion_k)

        logger.info(
            "retrieval: sparse=%d, dense=%d, graph=%d, fused=%d",
            len(sparse_docs),
            len(dense_docs),
            len(graph_docs),
            len(fused_docs),
        )

        return {
            "sparse_docs": sparse_docs,
            "dense_docs": dense_docs,
            "graph_docs": graph_docs,
            "fused_docs": fused_docs,
        }

    # ── sparse (ES BM25) ───────────────────────────────────

    async def _sparse_retrieve(self, queries: list[str], top_k: int) -> list[dict]:
        """Elasticsearch BM25 search across rewritten queries."""
        if not self._es.available:
            return []
        try:
            all_hits: list[dict] = []
            for q in queries:
                for variant in expand_script_variants(q):
                    hits = await self._es.search_bm25(TCM_CHUNKS_INDEX, variant, top_k=top_k)
                    for h in hits:
                        h["source_type"] = "sparse"
                    all_hits.extend(hits)
            # deduplicate by chunk_id, keep highest score
            return _deduplicate(all_hits, top_k)
        except Exception as exc:
            logger.warning("稀疏检索失败，降级跳过: %s", exc)
            return []

    # ── dense (FAISS) ───────────────────────────────────────

    async def _dense_retrieve(self, query: str, top_k: int) -> list[dict]:
        """FAISS vector search using embedding."""
        if not self._vs.available:
            return []
        try:
            all_hits: list[dict] = []
            for variant in expand_script_variants(query):
                query_embedding = await embedding_client.embed_query(variant)
                hits = await self._vs.search(query_embedding, top_k=top_k)
                for h in hits:
                    h["source_type"] = "dense"
                all_hits.extend(hits)
            return _deduplicate(all_hits, top_k)
        except Exception as exc:
            logger.warning("稠密检索失败，降级跳过: %s", exc)
            return []

    # ── graph (Neo4j) ───────────────────────────────────────

    async def _graph_retrieve(self, entities: list[str], top_k: int) -> list[dict]:
        """Neo4j entity expansion → convert to doc-like results."""
        if not self._neo4j.available:
            return []
        try:
            all_related: list[dict] = []
            for entity_name in entities:
                related = await self._neo4j.expand_entity(
                    entity_name, max_hops=settings.GRAPH_MAX_HOPS
                )
                all_related.extend(related)
            # Build pseudo retrieval hits from graph entities
            results: list[dict] = []
            seen: set[str] = set()
            for idx, rel in enumerate(all_related):
                name = rel.get("name", "")
                if not name or name in seen:
                    continue
                seen.add(name)
                results.append(
                    {
                        "chunk_id": f"graph-{name}",
                        "doc_id": "",
                        "chunk_text": f"[图谱实体] {name} ({', '.join(rel.get('labels', []))})",
                        "doc_title": "",
                        "score": 1.0 / (idx + 1),
                        "source_type": "graph",
                        "metadata": {"labels": rel.get("labels", []), "rel_type": rel.get("rel_type", "")},
                    }
                )
                if len(results) >= top_k:
                    break
            return results
        except Exception as exc:
            logger.warning("图谱检索失败，降级跳过: %s", exc)
            return []

    # ── RRF fusion ──────────────────────────────────────────

    async def _fuse_results(
        self,
        sparse: list[dict],
        dense: list[dict],
        graph: list[dict],
        top_k: int,
    ) -> list[dict]:
        """Reciprocal Rank Fusion: score = sum(1 / (RRF_K + rank_i))."""
        rrf_k = settings.RRF_K
        scores: dict[str, float] = defaultdict(float)
        doc_map: dict[str, dict] = {}

        for channel_docs in (sparse, dense, graph):
            for rank, doc in enumerate(channel_docs):
                cid = doc.get("chunk_id", "")
                if not cid:
                    continue
                scores[cid] += 1.0 / (rrf_k + rank + 1)
                if cid not in doc_map:
                    doc_map[cid] = doc

        # Sort by fused score
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        results: list[dict] = []
        for cid, fused_score in ranked:
            doc = doc_map[cid].copy()
            doc["score"] = round(fused_score, 6)
            doc.setdefault("source_type", "fused")
            results.append(doc)
        return results


class _EmptyResult:
    """Placeholder for absent TaskGroup tasks."""

    @staticmethod
    def result() -> list[dict]:
        return []


# ── module-level helpers (backward compatible) ──────────────

_service = RetrievalService()
retrieval_service = _service


def _deduplicate(hits: list[dict], top_k: int) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for h in sorted(hits, key=lambda x: x.get("score", 0), reverse=True):
        cid = h.get("chunk_id", "")
        if cid in seen:
            continue
        seen.add(cid)
        deduped.append(h)
        if len(deduped) >= top_k:
            break
    return deduped


def _fallback_keyword_search(
    query_bundle: QueryRewriteResult, top_k: int
) -> list[dict]:
    """Fallback to in-memory store keyword matching (original logic)."""
    from app.services.store import DocumentRecord

    def _score(doc: DocumentRecord) -> tuple[float, list[str]]:
        score = doc.authority_score
        reasons: list[str] = []
        nq = query_bundle.normalized_query
        for entity in query_bundle.entities:
            if entity in doc.keywords:
                score += 3.5
                reasons.append(f"命中实体 {entity}")
            elif entity in doc.title or (doc.excerpt and entity in doc.excerpt):
                score += 2.2
                reasons.append(f"命中正文 {entity}")
        for kw in doc.keywords:
            if kw in nq:
                score += 1.4
                reasons.append(f"命中关键词 {kw}")
        if doc.status == "published":
            score += 0.4
        return score, reasons

    candidates: list[dict] = []
    for doc in store.documents.values():
        score, reasons = _score(doc)
        if reasons:
            candidates.append(
                {
                    "chunk_id": f"{doc.doc_id}-chunk-1",
                    "doc_id": doc.doc_id,
                    "chunk_text": doc.excerpt or "",
                    "doc_title": doc.title,
                    "score": round(score, 4),
                    "source_type": "fallback",
                    "metadata": {},
                }
            )
    if not candidates:
        fallback_docs = sorted(
            store.documents.values(),
            key=lambda d: (d.status == "published", d.authority_score),
            reverse=True,
        )[:top_k]
        return [
            {
                "chunk_id": f"{d.doc_id}-chunk-1",
                "doc_id": d.doc_id,
                "chunk_text": d.excerpt or "",
                "doc_title": d.title,
                "score": round(d.authority_score, 4),
                "source_type": "fallback",
                "metadata": {},
            }
            for d in fallback_docs
        ]
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_k]


# ── backward-compatible top-level functions ─────────────────

def retrieve_documents(query_bundle: QueryRewriteResult, top_k: int = 5) -> list[RetrievalHit]:
    """Synchronous-compatible wrapper kept for existing callers (rag_service).

    Runs the full triple retrieval inside an event loop if one is available,
    otherwise falls back to keyword search.
    """
    # In sync context, use fallback directly (event loop may not be running)
    docs = _fallback_keyword_search(query_bundle, top_k)
    return [
        RetrievalHit(
            chunk_id=d["chunk_id"],
            doc_id=d.get("doc_id", ""),
            doc_title=d.get("doc_title", ""),
            source=d.get("source_type", "fallback"),
            retrieval_source=d.get("source_type", "fallback"),
            score=d.get("score", 0.0),
            reason=d.get("source_type", "fallback"),
            text=d.get("chunk_text", ""),
        )
        for d in docs
    ]


def build_citations(hits: list[RetrievalHit], top_k: int = 3) -> list[Citation]:
    return [
        Citation(
            chunk_id=hit.chunk_id,
            doc_title=hit.doc_title,
            text=hit.text,
        )
        for hit in hits[:top_k]
    ]
