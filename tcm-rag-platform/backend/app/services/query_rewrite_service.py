"""轻量版 query rewrite 服务 — rule-based + optional LLM rewrite."""

from __future__ import annotations

import json

from app.core.config import settings
from app.core.logger import get_logger
from app.schemas.rag import QueryRewriteResult
from app.services.text_normalization_service import to_simplified_medical

logger = get_logger(__name__)

ENTITY_ALIASES: dict[str, list[str]] = {
    "失眠": ["失眠", "睡不好", "入睡困难", "多梦", "睡眠差"],
    "口苦": ["口苦", "嘴苦"],
    "肝火": ["肝火", "烦躁", "易怒", "目赤"],
    "咳嗽": ["咳嗽", "咳", "咽痒"],
    "发热": ["发热", "发烧", "身热"],
    "感冒": ["感冒", "恶风", "鼻塞", "头痛"],
    "脾胃虚弱": ["脾胃虚弱", "食少", "乏力", "腹胀", "没胃口"],
    "月经不调": ["月经不调", "经期不准", "经行不畅", "痛经"],
    "当归": ["当归"],
    "桂枝汤": ["桂枝汤"],
}

_LLM_REWRITE_PROMPT = """\
你是一个中医药检索查询改写助手。用户输入了一段中医相关的查询，请帮助完成以下任务：
1. normalized_query: 对原始查询做语义规范化（去除口语化表达，统一术语）。
2. rewrite_queries: 生成 2-3 个改写变体，用于提升检索召回率。每个变体侧重不同角度（如证候、方剂、症状）。
3. entities: 提取查询中的中医实体（症状、方剂、药物、证候等）。
4. intent: 判断查询意图，从以下选项中选一个：symptom_diagnosis, formula_or_herb_knowledge, knowledge_lookup, general_consultation。

请以 JSON 格式输出，字段为：normalized_query, rewrite_queries (array), entities (array), intent (string)。
仅输出 JSON，不要附加任何解释。

用户查询：{query}
"""


def _normalize_query(query: str) -> str:
    normalized = " ".join(query.strip().split())
    normalized = to_simplified_medical(normalized)
    for canonical, aliases in ENTITY_ALIASES.items():
        for alias in aliases:
            normalized = normalized.replace(alias, canonical)
    return normalized


def _extract_entities(query: str) -> list[str]:
    entities: list[str] = []
    for canonical, aliases in ENTITY_ALIASES.items():
        if any(alias in query for alias in aliases):
            entities.append(canonical)
    return entities


def _infer_intent(query: str, entities: list[str]) -> str:
    if any(entity in {"当归", "桂枝汤"} for entity in entities):
        return "formula_or_herb_knowledge"
    if any(entity in {"失眠", "口苦", "肝火", "咳嗽", "发热", "感冒", "脾胃虚弱", "月经不调"} for entity in entities):
        return "symptom_diagnosis"
    if "是什么" in query or "出自" in query:
        return "knowledge_lookup"
    return "general_consultation"


def _rule_based_rewrite(query: str, history_summary: str | None = None) -> QueryRewriteResult:
    """Original rule-based rewriting logic."""
    normalized = _normalize_query(query)
    entities = _extract_entities(normalized)
    intent = _infer_intent(normalized, entities)

    rewrite_queries = [normalized]
    if entities:
        joined = " ".join(entities)
        rewrite_queries.append(f"{joined} 中医辨证 古籍依据")
        rewrite_queries.append(f"{joined} 经典出处 相关证候")
    if history_summary:
        rewrite_queries.append(f"{normalized} 结合上下文 {history_summary[:24]}")

    unique_queries: list[str] = []
    for item in rewrite_queries:
        if item and item not in unique_queries:
            unique_queries.append(item)

    return QueryRewriteResult(
        raw_query=query,
        normalized_query=normalized,
        rewrite_queries=unique_queries,
        entities=entities,
        intent=intent,
    )


async def _llm_based_rewrite(query: str, history_summary: str | None = None) -> QueryRewriteResult | None:
    """Try LLM-based rewrite using qwen-plus. Returns None on failure."""
    try:
        from app.integrations.llm_client import llm_client

        prompt = _LLM_REWRITE_PROMPT.format(query=query)
        if history_summary:
            prompt += f"\n对话上下文摘要：{history_summary[:60]}"

        messages = [{"role": "user", "content": prompt}]
        raw = await llm_client.chat(messages, model=settings.LLM_REWRITE_MODEL,
                                    temperature=0.3, max_tokens=500)

        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)
        normalized = data.get("normalized_query", query)
        rewrite_queries = data.get("rewrite_queries", [normalized])
        entities = data.get("entities", [])
        intent = data.get("intent", "general_consultation")

        # Ensure normalized is in rewrite list
        if normalized not in rewrite_queries:
            rewrite_queries.insert(0, normalized)

        logger.info("LLM rewrite succeeded: entities=%s, intent=%s", entities, intent)

        return QueryRewriteResult(
            raw_query=query,
            normalized_query=normalized,
            rewrite_queries=rewrite_queries,
            entities=entities,
            intent=intent,
        )

    except Exception as exc:
        logger.warning("LLM-based rewrite failed, falling back to rules: %s", exc)
        return None


async def rewrite_query_async(
    query: str,
    history_summary: str | None = None,
    *,
    use_llm: bool = True,
) -> QueryRewriteResult:
    """Async rewrite with optional LLM stage.

    Args:
        use_llm: when False, force rule-based rewrite only.
    """
    if settings.QUERY_REWRITE_ENABLED and use_llm:
        result = await _llm_based_rewrite(query, history_summary)
        if result is not None:
            return result

    return _rule_based_rewrite(query, history_summary)


def rewrite_query(query: str, history_summary: str | None = None) -> QueryRewriteResult:
    """Synchronous rule-based rewrite (backward-compatible)."""
    return _rule_based_rewrite(query, history_summary)


# ── Singleton service (used by API layer) ────────────────────

class QueryRewriteService:
    """Async query-rewrite service for the API layer."""

    async def rewrite(self, db, query: str, history_summary: str | None = None) -> dict:
        result = await rewrite_query_async(query, history_summary=history_summary)
        return result.model_dump()


query_rewrite_service = QueryRewriteService()
