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

_SMALLTALK_EXACT_MARKERS = {
    "你好",
    "你好呀",
    "你好啊",
    "哈喽",
    "hello",
    "hi",
    "在吗",
    "在嘛",
    "早上好",
    "中午好",
    "下午好",
    "晚上好",
    "谢谢",
    "谢谢你",
    "多谢",
    "辛苦了",
    "好的",
    "好滴",
    "收到",
    "嗯",
    "嗯嗯",
}

_MEDICAL_HINT_MARKERS = (
    "疼",
    "痛",
    "胀",
    "痒",
    "热",
    "寒",
    "咳",
    "眠",
    "药",
    "方",
    "症",
    "舌",
    "脉",
    "食疗",
    "凉茶",
    "煲汤",
)

_KNOWLEDGE_SEARCH_MARKERS = (
    "古籍",
    "出处",
    "原文",
    "医书",
    "哪本书",
    "文献",
    "经典",
    "本草纲目",
    "黄帝内经",
    "伤寒论",
    "金匮要略",
    "方剂",
    "方子",
    "药方",
    "药材",
    "中药",
    "当归",
    "桂枝汤",
)

_SIMPLE_CONSULT_MARKERS = (
    "我现在",
    "我最近",
    "最近",
    "有点",
    "总是",
    "老是",
    "感觉",
    "是不是",
    "正常吗",
    "怎么办",
    "要紧吗",
    "严重吗",
    "能吃吗",
    "要忌口吗",
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

    @staticmethod
    def is_smalltalk(query: str) -> bool:
        normalized = (query or "").strip().lower().strip("，,。.!！？?~～ ")
        if not normalized:
            return False
        if normalized in _SMALLTALK_EXACT_MARKERS:
            return True
        if len(normalized) <= 8 and any(item in normalized for item in ("你好", "哈喽", "hello", "hi", "谢谢", "在吗")):
            if not any(marker in normalized for marker in _MEDICAL_HINT_MARKERS):
                return True
        return False

    @staticmethod
    def requires_search(query: str) -> bool:
        normalized = (query or "").strip()
        if not normalized:
            return False
        return any(marker in normalized for marker in _KNOWLEDGE_SEARCH_MARKERS)

    @staticmethod
    def is_simple_consult(query: str) -> bool:
        normalized = (query or "").strip()
        if not normalized:
            return False
        if LightAgentService.is_smalltalk(normalized):
            return False
        if any(marker in normalized for marker in _DIETARY_RECOMMENDATION_MARKERS):
            return False
        if any(marker in normalized for marker in _DIRECT_KNOWLEDGE_MARKERS):
            return False
        if LightAgentService.requires_search(normalized):
            return False
        has_consult_marker = any(marker in normalized for marker in _SIMPLE_CONSULT_MARKERS)
        has_medical_hint = any(marker in normalized for marker in _MEDICAL_HINT_MARKERS)
        return has_medical_hint or has_consult_marker

    def plan(self, query: str, history_summary: str | None = None) -> ToolPlan:
        query = (query or "").strip()
        q_len = len(query)
        if self.is_smalltalk(query):
            return ToolPlan(
                strategy="smalltalk",
                use_llm_rewrite=False,
                use_rerank=False,
                retrieval_top_k=0,
                answer_top_k=0,
                rerank_top_k=0,
                answer_style="chat",
                reason="寒暄或简短对话，直接短答，跳过检索与引用。",
            )

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

        if self.is_simple_consult(query):
            return ToolPlan(
                strategy="no_search_consult",
                use_llm_rewrite=False,
                use_rerank=False,
                retrieval_top_k=0,
                answer_top_k=0,
                rerank_top_k=0,
                answer_style="consult",
                reason="简单问诊或生活化咨询，不需要搜索医术依据，先走简短问诊/答复。",
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
