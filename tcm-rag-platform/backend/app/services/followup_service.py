"""会话级追问器：基于缺失槽位的轻量追问状态机。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_QUESTION_MARKERS = ("？", "?", "怎么", "为何", "为什么", "如何", "能不能", "可以吗", "是不是", "要不要")
_DIETARY_MARKERS = ("凉茶", "代茶饮", "煲汤", "药膳", "泡茶", "茶饮", "食疗", "推荐")

_DURATION_PATTERNS = [
    re.compile(r"((?:近|约|差不多)?[一二三四五六七八九十两半\d]+(?:个)?(?:小时|天|周|星期|个月|月|年))"),
    re.compile(r"(昨天|今天|前天|最近|这几天|这几周|这几个月|长期|一直|断断续续)"),
]

_SEVERITY_PATTERNS = [
    re.compile(r"(很严重|比较严重|挺严重|非常严重|厉害|明显|影响睡眠|影响吃饭|影响工作|轻微|一般)"),
]

_CONTRAINDICATION_PATTERNS = [
    re.compile(r"(怀孕|妊娠|备孕|哺乳|过敏|高血压|糖尿病|痛风|肾病|肝病|慢性病|正在用药|吃药)"),
]

_SYMPTOM_HINTS = (
    "胃胀",
    "腹胀",
    "失眠",
    "口苦",
    "咳嗽",
    "发热",
    "头痛",
    "腹泻",
    "便秘",
    "咽痛",
    "口干",
    "反酸",
    "嗳气",
    "恶心",
    "乏力",
    "怕冷",
    "怕热",
    "胸闷",
)

_SLOT_LABELS = {
    "primary_symptom": "主症状",
    "duration": "持续时间",
    "severity": "严重程度",
    "accompanying_symptoms": "伴随表现",
    "contraindications": "禁忌和用药情况",
}

_SLOT_QUESTIONS = {
    "primary_symptom": "你这次最想处理的主症状是什么？",
    "duration": "这个情况大概持续多久了？",
    "severity": "现在大概有多严重，是否已经影响睡眠、吃饭或工作？",
    "accompanying_symptoms": "还伴随哪些表现，比如口干口苦、怕冷怕热、反酸、腹泻、便秘、乏力等？",
    "contraindications": "有没有过敏、怀孕/备孕/哺乳、慢病，或者正在用药？",
}

_DOMAIN_SLOTS = {
    "symptom": ["primary_symptom", "duration", "accompanying_symptoms"],
    "dietary": ["primary_symptom", "duration", "contraindications"],
}


@dataclass(slots=True)
class FollowUpDecision:
    need_follow_up: bool
    follow_up_message: str | None
    effective_query: str
    clarification_context: str | None = None
    message_kind: str = "answer"


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _has_case_profile_details(case_profile_summary: str | None, field_name: str) -> bool:
    summary = _normalize_text(case_profile_summary)
    if not summary:
        return False
    if field_name == "contraindications":
        return any(marker in summary for marker in ("既往史：", "过敏史：", "当前用药："))
    return False


def _looks_like_new_question(text: str) -> bool:
    text = _normalize_text(text)
    if not text:
        return False
    return any(marker in text for marker in _QUESTION_MARKERS) or len(text) >= 16


def _extract_duration(text: str) -> str | None:
    for pattern in _DURATION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _extract_severity(text: str) -> str | None:
    for pattern in _SEVERITY_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _extract_contraindications(text: str, case_profile_summary: str | None) -> str | None:
    if _has_case_profile_details(case_profile_summary, "contraindications"):
        return "已在角色档案中提供"
    for pattern in _CONTRAINDICATION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    if any(marker in text for marker in ("没有过敏", "无过敏", "没有慢病", "没吃药", "未用药")):
        return text[:48]
    return None


def _extract_accompanying_symptoms(text: str) -> str | None:
    if "伴" in text or "还" in text or "同时" in text:
        for marker in ("还", "伴", "同时", "并且"):
            if marker in text:
                tail = text.split(marker, 1)[-1].strip(" ，,。；;")
                if tail and tail != text:
                    return tail[:48]
    hints = [item for item in _SYMPTOM_HINTS if item in text]
    if len(hints) >= 2:
        return "、".join(hints[1:4])
    return None


def _extract_primary_symptom(text: str) -> str | None:
    hints = [item for item in _SYMPTOM_HINTS if item in text]
    if hints:
        return "、".join(hints[:2])

    stripped = _normalize_text(text)
    stripped = re.sub(r"^(我现在|我这两天|我最近|最近|想问一下|请问|帮我看下)", "", stripped)
    stripped = re.sub(r"(怎么办|怎么调理|怎么处理|怎么回事|可以吗|能不能).*?$", "", stripped)
    stripped = stripped.strip(" ，,。；;")
    if 2 <= len(stripped) <= 24:
        return stripped
    return None


def _extract_slots(
    text: str,
    *,
    domain: str,
    case_profile_summary: str | None,
) -> dict[str, str]:
    extracted: dict[str, str] = {}
    primary = _extract_primary_symptom(text)
    if primary:
        extracted["primary_symptom"] = primary

    duration = _extract_duration(text)
    if duration:
        extracted["duration"] = duration

    severity = _extract_severity(text)
    if severity:
        extracted["severity"] = severity

    accompanying = _extract_accompanying_symptoms(text)
    if accompanying:
        extracted["accompanying_symptoms"] = accompanying

    if domain == "dietary":
        contraindications = _extract_contraindications(text, case_profile_summary)
        if contraindications:
            extracted["contraindications"] = contraindications

    return extracted


def _resolve_domain(query: str, intent: str | None, answer_style: str | None) -> str | None:
    if answer_style == "dietary" or any(marker in query for marker in _DIETARY_MARKERS):
        return "dietary"
    if intent in {"symptom_diagnosis", "general_consultation"}:
        return "symptom"
    return None


def _build_clarification_context(collected: dict[str, str]) -> str | None:
    parts = [
        f"{_SLOT_LABELS[key]}：{value}"
        for key, value in collected.items()
        if key in _SLOT_LABELS and _normalize_text(value)
    ]
    return "；".join(parts) if parts else None


def _build_follow_up_message(
    *,
    pending_slots: list[str],
    collected: dict[str, str],
    interrupted: bool,
) -> str:
    first_slot = pending_slots[0]
    pending_labels = "、".join(_SLOT_LABELS.get(item, item) for item in pending_slots)
    collected_context = _build_clarification_context(collected)
    lead = "你刚刚的新问题我记住了，不过要判断得更准，还是得先把关键信息补齐。" if interrupted else "为了判断更准，我还差一些关键信息。"
    lines = [lead]
    if collected_context:
        lines.append(f"已收到：{collected_context}")
    lines.append(f"先补这一项：{_SLOT_QUESTIONS[first_slot]}")
    if len(pending_slots) > 1:
        lines.append(f"待补信息：{pending_labels}")
    lines.append("你也可以一次性把剩余信息都发来，我补齐后继续回答。")
    return "\n".join(lines)


class FollowUpService:
    def process_turn(
        self,
        session,
        *,
        query: str,
        intent: str | None,
        answer_style: str | None,
        case_profile_summary: str | None,
    ) -> FollowUpDecision:
        raw_state = session.followup_state or {}
        active = bool(raw_state.get("active"))
        interrupted = False

        if active:
            domain = raw_state.get("domain")
            if _looks_like_new_question(query):
                interrupted = True
                domain = _resolve_domain(query, intent, answer_style) or domain
                collected = _extract_slots(
                    query,
                    domain=domain,
                    case_profile_summary=case_profile_summary,
                )
                required_slots = list(_DOMAIN_SLOTS.get(domain, []))
                raw_state = {
                    "active": True,
                    "domain": domain,
                    "original_query": query,
                    "latest_query": query,
                    "required_slots": required_slots,
                    "collected": collected,
                }
            else:
                collected = dict(raw_state.get("collected", {}))
                extracted = _extract_slots(
                    query,
                    domain=domain,
                    case_profile_summary=case_profile_summary,
                )
                for key, value in extracted.items():
                    if not _normalize_text(collected.get(key)):
                        collected[key] = value
                raw_state["collected"] = collected
                required_slots = list(raw_state.get("required_slots", _DOMAIN_SLOTS.get(domain, [])))
        else:
            domain = _resolve_domain(query, intent, answer_style)
            if not domain:
                return FollowUpDecision(
                    need_follow_up=False,
                    follow_up_message=None,
                    effective_query=query,
                    clarification_context=None,
                )
            collected = _extract_slots(
                query,
                domain=domain,
                case_profile_summary=case_profile_summary,
            )
            required_slots = list(_DOMAIN_SLOTS.get(domain, []))
            raw_state = {
                "active": True,
                "domain": domain,
                "original_query": query,
                "latest_query": query,
                "required_slots": required_slots,
                "collected": collected,
            }

        pending_slots = [
            slot
            for slot in required_slots
            if not _normalize_text(collected.get(slot))
            and not _has_case_profile_details(case_profile_summary, slot)
        ]
        raw_state["pending_slots"] = pending_slots
        session.followup_state = raw_state

        if pending_slots:
            return FollowUpDecision(
                need_follow_up=True,
                follow_up_message=_build_follow_up_message(
                    pending_slots=pending_slots,
                    collected=collected,
                    interrupted=interrupted,
                ),
                effective_query=raw_state.get("latest_query") or raw_state.get("original_query") or query,
                clarification_context=_build_clarification_context(collected),
                message_kind="followup",
            )

        effective_query = raw_state.get("latest_query") or raw_state.get("original_query") or query
        clarification_context = _build_clarification_context(collected)
        session.followup_state = {}
        return FollowUpDecision(
            need_follow_up=False,
            follow_up_message=None,
            effective_query=effective_query,
            clarification_context=clarification_context,
        )


followup_service = FollowUpService()
