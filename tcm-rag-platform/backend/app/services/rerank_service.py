"""候选重排服务 — DashScope gte-rerank + authority/freshness scoring."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Document type priority for authority weighting
_DOC_TYPE_PRIORITY: dict[str, float] = {
    "guideline": 1.0,
    "指南": 1.0,
    "textbook": 0.8,
    "教材": 0.8,
    "古籍": 0.85,
    "general": 0.5,
}


def _authority_weight(candidate: dict) -> float:
    """Derive authority weight from document metadata."""
    # Try explicit authority_score first
    if "authority_score" in candidate:
        return float(candidate["authority_score"])
    source = candidate.get("source", "general")
    return _DOC_TYPE_PRIORITY.get(source, 0.5)


def _freshness_weight(candidate: dict) -> float:
    """Score freshness based on published_at date (0.0–1.0)."""
    published_at = candidate.get("published_at")
    if not published_at:
        return 0.5  # neutral when unknown

    try:
        if isinstance(published_at, str):
            # handle ISO format
            pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        else:
            pub_dt = published_at

        now = datetime.now(timezone.utc)
        age_days = max(0, (now - pub_dt).days)
        # 0-30 days → 1.0, 365+ days → 0.3, linear in between
        if age_days <= 30:
            return 1.0
        if age_days >= 365:
            return 0.3
        return 1.0 - 0.7 * ((age_days - 30) / 335)
    except Exception:
        return 0.5


async def _dashscope_rerank(query: str, candidates: list[dict], top_k: int) -> list[dict] | None:
    """Try to call DashScope gte-rerank. Returns None on failure."""
    try:
        import dashscope

        dashscope.api_key = settings.DASHSCOPE_API_KEY
        texts = [c.get("text", c.get("snippet", "")) for c in candidates]

        response = dashscope.TextReRank.call(
            model=settings.RERANKER_MODEL,
            query=query,
            documents=texts,
            top_n=min(top_k * 2, len(texts)),  # fetch extra, we'll re-score
            return_documents=False,
        )

        if response.status_code != 200:
            logger.warning("DashScope reranker returned %s: %s", response.status_code, response.message)
            return None

        # Map scores back to candidates
        scored: list[dict] = []
        for item in response.output.results:
            idx = item.index
            if idx < len(candidates):
                scored.append({
                    **candidates[idx],
                    "_rerank_score": float(item.relevance_score),
                })
        return scored

    except ImportError:
        logger.info("dashscope not available for reranking, using fallback")
        return None
    except Exception as exc:
        logger.warning("DashScope reranker call failed: %s", exc)
        return None


class RerankService:
    async def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank candidates using DashScope reranker + composite scoring.

        final_score = rerank_score * 0.7 + authority_weight * 0.2 + freshness_weight * 0.1
        """
        start_time = time.perf_counter()

        if not candidates:
            return []

        # --- try DashScope reranker ---
        reranked_candidates: list[dict] | None = None
        if settings.RERANKER_ENABLED:
            reranked_candidates = await _dashscope_rerank(query, candidates, top_k)

        # --- fallback: use existing score as rerank_score ---
        if reranked_candidates is None:
            reranked_candidates = [
                {**c, "_rerank_score": float(c.get("score", 0.0))}
                for c in candidates
            ]

        # --- composite scoring ---
        results: list[dict] = []
        for item in reranked_candidates:
            rerank_score = item.pop("_rerank_score", 0.0)
            auth = _authority_weight(item)
            fresh = _freshness_weight(item)
            final_score = rerank_score * 0.7 + auth * 0.2 + fresh * 0.1
            results.append({
                **item,
                "score": round(final_score, 4),
                "_rerank_detail": {
                    "rerank_score": round(rerank_score, 4),
                    "authority": round(auth, 4),
                    "freshness": round(fresh, 4),
                },
            })

        results.sort(key=lambda doc: doc["score"], reverse=True)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            "rerank completed: input=%d, output=%d, latency=%dms",
            len(candidates), min(top_k, len(results)), latency_ms,
        )

        return results[:top_k]


rerank_service = RerankService()
