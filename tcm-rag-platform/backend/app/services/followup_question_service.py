"""LLM-backed follow-up question generator with deterministic fallback."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.services.followup_service import build_consultation_context_summary

logger = get_logger(__name__)

_TARGET_DEFAULT_QUESTIONS = {
    "primary_symptom": "你这次最想处理的主症状是什么？",
    "duration": "这个情况大概持续多久了？",
    "severity": "现在大概有多严重，是否已经影响睡眠、吃饭或工作？",
    "accompanying_symptoms": "还伴随哪些表现，比如口干口苦、反酸、腹泻、便秘或乏力？",
    "contraindications": "有没有怀孕、备孕、哺乳、慢病、过敏，或者正在用药？",
    "body_status.sleep": "最近睡眠怎么样，有没有入睡困难、容易醒或多梦？",
    "body_status.appetite": "最近胃口怎么样，吃得下吗，有没有明显食欲差？",
    "body_status.bowel": "最近二便怎么样，大便和小便基本正常吗？",
    "body_status.temperature": "现在整体更偏怕冷还是怕热？",
}

_TARGET_LABELS = {
    "primary_symptom": "主症状",
    "duration": "病程时长",
    "severity": "严重程度",
    "accompanying_symptoms": "伴随表现",
    "contraindications": "禁忌与用药情况",
    "body_status.sleep": "睡眠情况",
    "body_status.appetite": "胃口情况",
    "body_status.bowel": "二便情况",
    "body_status.temperature": "寒热偏向",
}

_FOLLOWUP_PROMPT = """\
你是一个中医问诊追问助手。你的任务是基于当前缺失的一个信息目标，生成一句自然、简短、不重复的中文追问。

要求：
1. 只能问一个目标，不要把多个问题并在一起。
2. 不要重复已经明确知道的信息。
3. 不要输出“继续补充”“我收到后继续”“第几问”等包装语。
4. 不要复述已收集信息，不要解释原因，不要输出项目符号或 Markdown。
5. 语气自然、口语化，长度控制在 1 句话内。

当前领域：{domain}
当前缺失目标：{target_label}
默认兜底问法：{fallback_question}
已知信息：{known_context}
本轮用户刚说：{latest_query}
之前已经问过：{asked_targets}

请直接输出一句追问。
"""


class FollowUpQuestionService:
    @staticmethod
    def default_question(target: str) -> str:
        return _TARGET_DEFAULT_QUESTIONS.get(target, "请继续补充这一项。")

    async def generate_question(
        self,
        *,
        domain: str,
        target: str,
        collected_slots: dict[str, Any] | None,
        latest_query: str,
        asked_targets: list[str] | None = None,
    ) -> str:
        fallback_question = self.default_question(target)
        known_context = build_consultation_context_summary(collected_slots) or "暂无"
        target_label = _TARGET_LABELS.get(target, target)
        asked = "、".join(item for item in (asked_targets or []) if item) or "暂无"
        prompt = _FOLLOWUP_PROMPT.format(
            domain=domain,
            target_label=target_label,
            fallback_question=fallback_question,
            known_context=known_context,
            latest_query=latest_query.strip() or "暂无",
            asked_targets=asked,
        )
        try:
            from app.integrations.llm_client import llm_client

            raw = await llm_client.chat(
                [{"role": "user", "content": prompt}],
                model=settings.LLM_REWRITE_MODEL,
                temperature=0.3,
                top_p=0.8,
                max_tokens=80,
            )
            question = (raw or "").strip().strip("```").strip()
            if not question:
                return fallback_question
            first_line = question.splitlines()[0].strip().strip("\"' ")
            if not first_line:
                return fallback_question
            if len(first_line) > 60:
                return fallback_question
            return first_line
        except Exception as exc:
            logger.warning("LLM follow-up question generation failed, using fallback: %s", exc)
            return fallback_question


followup_question_service = FollowUpQuestionService()
