"""轻量 agent 编排：启发式规划 + 工具按需执行。

目标：
1. 不新增额外的大模型 planner 调用；
2. 用启发式规则决定是否需要 LLM rewrite / rerank；
3. 缩小最终送入生成模型的证据集，降低端到端延迟。
"""

from __future__ import annotations

from dataclasses import dataclass


_COLLOQUIAL_MARKERS = (
    "我现在",
    "怎么办",
    "能不能",
    "可以吗",
    "怎么调理",
    "最近",
    "老是",
    "总是",
    "适合",
    "是不是",
)

_DIRECT_KNOWLEDGE_MARKERS = (
    "是什么",
    "有什么功效",
    "功效",
    "作用",
    "出自",
    "有哪些",
    "什么意思",
)

_COMPLEX_MARKERS = ("以及", "同时", "还有", "并且", "但是", "不过", "一边", "一会")

_DIETARY_RECOMMENDATION_MARKERS = (
    "凉茶",
    "代茶饮",
    "煲汤",
    "泡茶",
    "茶饮",
    "食疗",
    "汤方",
    "药膳",
    "推荐",
    "喝什么",
    "煮什么",
    "怎么喝",
)


@dataclass(slots=True)
class ToolPlan:
    strategy: str
    use_llm_rewrite: bool
    use_rerank: bool
    retrieval_top_k: int
    answer_top_k: int
    rerank_top_k: int
    answer_style: str
    reason: str


class LightAgentService:
    """Heuristic planner for a tool-based lightweight agent chain."""

    def plan(self, query: str, history_summary: str | None = None) -> ToolPlan:
        query = (query or "").strip()
        q_len = len(query)
        has_colloquial = any(marker in query for marker in _COLLOQUIAL_MARKERS)
        is_direct_knowledge = any(marker in query for marker in _DIRECT_KNOWLEDGE_MARKERS)
        is_complex = any(marker in query for marker in _COMPLEX_MARKERS) or q_len >= 24
        needs_dietary_recommendation = any(
            marker in query for marker in _DIETARY_RECOMMENDATION_MARKERS
        )
        has_history = bool((history_summary or "").strip())

        if needs_dietary_recommendation:
            return ToolPlan(
                strategy="guided_reasoning" if (has_colloquial or has_history or is_complex) else "fast_hybrid",
                use_llm_rewrite=has_colloquial or has_history or is_complex,
                use_rerank=True,
                retrieval_top_k=10,
                answer_top_k=4,
                rerank_top_k=4,
                answer_style="dietary",
                reason="用户明确在要代茶饮/煲汤/食疗推荐，保留推荐型模板，但压缩为必要信息。",
            )

        if is_direct_knowledge and q_len <= 18 and not has_colloquial:
            return ToolPlan(
                strategy="direct_lookup",
                use_llm_rewrite=False,
                use_rerank=False,
                retrieval_top_k=8,
                answer_top_k=2,
                rerank_top_k=3,
                answer_style="concise",
                reason="直接知识问答，优先短答，不强行展开成完整方案。",
            )

        if has_colloquial or has_history or is_complex:
            return ToolPlan(
                strategy="guided_reasoning",
                use_llm_rewrite=True,
                use_rerank=True,
                retrieval_top_k=10,
                answer_top_k=4,
                rerank_top_k=5,
                answer_style="adaptive",
                reason="问题需要一定判断，但默认仍优先简洁输出，仅在必要时展开。",
            )

        return ToolPlan(
            strategy="fast_hybrid",
            use_llm_rewrite=False,
            use_rerank=True,
            retrieval_top_k=8,
            answer_top_k=3,
            rerank_top_k=4,
            answer_style="concise",
            reason="中等复杂度问题，保留混合检索 + 小规模 rerank，输出以短答为主。",
        )

    def should_rerank(self, candidates: list[dict], plan: ToolPlan) -> bool:
        if not plan.use_rerank or len(candidates) <= 1:
            return False

        if len(candidates) <= plan.rerank_top_k:
            top_scores = [float(item.get("score", 0.0)) for item in candidates[:2]]
            if len(top_scores) < 2:
                return False
            return abs(top_scores[0] - top_scores[1]) < 0.12

        return True

    def trim_for_answer(self, candidates: list[dict], plan: ToolPlan) -> list[dict]:
        return candidates[: max(1, plan.answer_top_k)]


light_agent_service = LightAgentService()
