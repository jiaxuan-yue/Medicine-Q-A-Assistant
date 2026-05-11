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
你是一个中医问诊追问助手。你的任务是基于当前缺失的多个信息目标，一次性生成多句自然、简短、不重复的中文追问。

要求：
1. 每个目标对应一句追问，不要合并在一起。
2. 不要重复已经明确知道的信息。
3. 不要输出”继续补充””我收到后继续””第几问”等包装语。
4. 不要复述已收集信息，不要解释原因，不要输出项目符号或 Markdown。
5. 语气自然、口语化，每句长度控制在 1 句话内。
6. 严格按编号顺序输出，一行一个，前面不要加编号（我会自行编号）。

当前领域：{domain}
缺失目标列表：{targets_list}
已知信息：{known_context}
本轮用户刚说：{latest_query}
之前已经问过：{asked_targets}

请直接逐行输出对应追问，不要包含任何其他内容。
"""


class FollowUpQuestionService:
    @staticmethod
    def default_question(target: str) -> str:
        return _TARGET_DEFAULT_QUESTIONS.get(target, "请继续补充这一项。")

    def default_questions(self, targets: list[str]) -> list[str]:
        """Generate deterministic fallback questions for all targets."""
        return [self.default_question(t) for t in targets]

    async def generate_questions(
        self,
        *,
        domain: str,
        targets: list[str],
        collected_slots: dict[str, Any] | None,
        latest_query: str,
        asked_targets: list[str] | None = None,
    ) -> list[str]:
        """Generate follow-up questions for all missing targets in one LLM call."""
        fallback_questions = self.default_questions(targets)
        known_context = build_consultation_context_summary(collected_slots) or "暂无"
        targets_list = "、".join(_TARGET_LABELS.get(t, t) for t in targets)
        asked = "、".join(item for item in (asked_targets or []) if item) or "暂无"
        prompt = _FOLLOWUP_PROMPT.format(
            domain=domain,
            targets_list=targets_list,
            fallback_question=fallback_questions[0] if fallback_questions else "",
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
                max_tokens=200,
            )
            content = (raw or "").strip().strip("```").strip()
            if not content:
                return fallback_questions

            lines = [
                line.strip().strip("0123456789.、. \"'")
                for line in content.splitlines()
                if line.strip()
            ]
            lines = [line for line in lines if line]

            if len(lines) < len(targets):
                # LLM didn't generate enough questions, fall back to defaults
                return fallback_questions

            # Clamp to expected number
            result = lines[:len(targets)]
            # Filter out overly long lines
            return [q if len(q) <= 80 else fallback_questions[i] for i, q in enumerate(result)]
        except Exception as exc:
            logger.warning("LLM follow-up questions generation failed, using fallback: %s", exc)
            return fallback_questions

    # Keep old single-question API for backward compat
    async def generate_question(
        self,
        *,
        domain: str,
        target: str,
        collected_slots: dict[str, Any] | None,
        latest_query: str,
        asked_targets: list[str] | None = None,
    ) -> str:
        questions = await self.generate_questions(
            domain=domain,
            targets=[target],
            collected_slots=collected_slots,
            latest_query=latest_query,
            asked_targets=asked_targets,
        )
        return questions[0] if questions else self.default_question(target)


followup_question_service = FollowUpQuestionService()
