"""会话级追问器：基于缺失槽位的轻量追问状态机。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_QUESTION_MARKERS = ("？", "?", "怎么", "为何", "为什么", "如何", "能不能", "可以吗", "是不是", "要不要")
_DIETARY_MARKERS = ("凉茶", "代茶饮", "煲汤", "药膳", "泡茶", "茶饮", "食疗", "推荐")
_COOLING_TEA_MARKERS = ("凉茶", "清热", "降火", "祛湿茶", "清火", "下火", "败火")
_NEW_TOPIC_PREFIXES = ("我想问", "我其实想问", "另外", "换个问题", "再问一个", "还有个问题", "顺便问下")

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

_SLEEP_STATUS_MARKERS = ("睡不好", "失眠", "多梦", "易醒", "入睡困难", "睡得还行", "睡眠一般", "睡眠差")
_APPETITE_STATUS_MARKERS = ("胃口差", "食欲差", "没胃口", "吃得少", "食欲一般", "胃口一般", "胃口还行", "能吃")
_BOWEL_STATUS_MARKERS = ("腹泻", "便秘", "大便稀", "大便偏稀", "大便干", "大便偏干", "便溏", "二便正常", "小便黄", "尿黄")
_HEAT_COLD_STATUS_MARKERS = ("怕冷", "怕热", "口干", "口苦", "手脚凉", "容易上火", "发热", "畏寒")

_BODY_STATUS_DIMENSIONS = ("sleep", "appetite", "bowel", "temperature")

_SLOT_LABELS = {
    "primary_symptom": "主症状",
    "duration": "持续时间",
    "severity": "严重程度",
    "accompanying_symptoms": "伴随表现",
    "body_statuses": "其他状态",
    "contraindications": "禁忌和用药情况",
}

_DOMAIN_SLOTS = {
    "symptom": ["primary_symptom", "duration", "severity", "body_statuses", "accompanying_symptoms"],
    "dietary": ["primary_symptom", "duration", "body_statuses", "accompanying_symptoms", "contraindications"],
    "cooling_tea": ["primary_symptom", "body_statuses", "accompanying_symptoms", "duration", "contraindications"],
}

_DOMAIN_INTROS = {
    "symptom": "为了把症状判断得更准，我还差几项问诊信息。",
    "dietary": "为了把食疗建议收得更稳，我还差几项调理信息。",
    "cooling_tea": "为了避免凉茶推荐过凉、过猛，我还差几项关键信息。",
}

_DOMAIN_SLOT_LABELS = {
    "symptom": {
        "primary_symptom": "主症状",
        "duration": "持续时间",
        "severity": "严重程度",
        "body_statuses": "其他状态",
        "accompanying_symptoms": "伴随表现",
    },
    "dietary": {
        "primary_symptom": "想调理的问题",
        "duration": "持续时间",
        "body_statuses": "整体状态",
        "accompanying_symptoms": "体感和伴随表现",
        "contraindications": "禁忌和用药情况",
    },
    "cooling_tea": {
        "primary_symptom": "想解决的问题",
        "body_statuses": "整体状态",
        "accompanying_symptoms": "偏热/偏湿表现",
        "duration": "持续时间",
        "contraindications": "凉茶禁忌情况",
    },
}

_DOMAIN_SLOT_QUESTIONS = {
    "symptom": {
        "primary_symptom": "你这次最想处理的主症状是什么？",
        "duration": "这个情况大概持续多久了？",
        "severity": "现在大概有多严重，是否已经影响睡眠、吃饭或工作？",
        "body_statuses": "再补一下病人的其他状态：最近睡眠、胃口、二便，以及怕冷还是怕热，大概怎么样？",
        "accompanying_symptoms": "还伴随哪些表现，比如口干口苦、怕冷怕热、反酸、腹泻、便秘、乏力等？",
    },
    "dietary": {
        "primary_symptom": "这次你最想通过食疗改善什么问题，是养胃、助眠、祛湿，还是缓解某个不适？",
        "duration": "这个状态持续多久了，是偶发还是最近一直这样？",
        "body_statuses": "再补一下整体状态：最近睡眠、胃口、二便，以及怕冷怕热的情况怎么样？",
        "accompanying_symptoms": "除了这个问题，还伴随哪些体感，比如口干、口苦、腹胀、怕冷、乏力、睡不好等？",
        "contraindications": "有没有过敏、怀孕/备孕/哺乳、慢病，或者正在用药？这些会影响食疗推荐。",
    },
    "cooling_tea": {
        "primary_symptom": "你这次想用凉茶主要处理什么，是上火、咽痛、口苦、长痘，还是湿热困重？",
        "body_statuses": "再补一下整体状态：最近睡眠、胃口、二便，以及怕冷还是怕热，大概是什么情况？",
        "accompanying_symptoms": "再补一下偏热或偏湿的表现，比如口苦口干、咽痛、尿黄、长痘、困重、舌苔厚腻等？",
        "duration": "这些表现大概持续多久了，是这两天突然加重，还是已经反复一段时间？",
        "contraindications": "有没有怕冷、腹泻、经期、怀孕/备孕/哺乳、慢病或正在用药？凉茶这一步要先避开禁忌。",
    },
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
    if field_name == "body_statuses":
        markers = ("睡眠", "胃口", "食欲", "大便", "便秘", "腹泻", "怕冷", "怕热", "口干", "口苦")
        return any(marker in summary for marker in markers)
    return False


def _looks_like_new_question(text: str) -> bool:
    text = _normalize_text(text)
    if not text:
        return False
    return any(marker in text for marker in _QUESTION_MARKERS) or any(
        text.startswith(prefix) for prefix in _NEW_TOPIC_PREFIXES
    )


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


def _extract_body_statuses(text: str) -> str | None:
    status_map = _extract_body_status_details(text)
    if not status_map:
        return None
    return _render_body_status_map(status_map)


def _extract_body_status_details(text: str) -> dict[str, str]:
    result: dict[str, str] = {}

    sleep_hits = [marker for marker in _SLEEP_STATUS_MARKERS if marker in text][:2]
    if sleep_hits:
        result["sleep"] = "、".join(sleep_hits)

    appetite_hits = [marker for marker in _APPETITE_STATUS_MARKERS if marker in text][:2]
    if appetite_hits:
        result["appetite"] = "、".join(appetite_hits)

    bowel_hits = [marker for marker in _BOWEL_STATUS_MARKERS if marker in text][:2]
    if bowel_hits:
        result["bowel"] = "、".join(bowel_hits)

    heat_cold_hits = [marker for marker in _HEAT_COLD_STATUS_MARKERS if marker in text][:2]
    if heat_cold_hits:
        result["temperature"] = "、".join(heat_cold_hits)

    return result


def _normalize_status_value(value: str, prefix: str) -> str:
    value = _normalize_text(value)
    if value.startswith(prefix):
        return value[len(prefix):]
    return value


def _render_body_status_map(status_map: dict[str, str]) -> str:
    parts: list[str] = []
    if status_map.get("sleep"):
        parts.append(f"睡眠{_normalize_status_value(status_map['sleep'], '睡眠')}")
    if status_map.get("appetite"):
        parts.append(f"胃口{_normalize_status_value(status_map['appetite'], '胃口')}")
    if status_map.get("bowel"):
        bowel_value = _normalize_status_value(status_map['bowel'], '大便')
        bowel_value = _normalize_status_value(bowel_value, '二便')
        parts.append(f"二便{bowel_value}")
    if status_map.get("temperature"):
        parts.append(f"寒热{status_map['temperature']}")
    return "；".join(parts)


def _body_status_is_sufficient(value: str | None) -> bool:
    text = _normalize_text(value)
    if not text:
        return False
    detail_map = _extract_body_status_details(text)
    return len(detail_map) >= 3


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

    body_statuses = _extract_body_statuses(text)
    if body_statuses:
        extracted["body_statuses"] = body_statuses

    if domain in {"dietary", "cooling_tea"}:
        contraindications = _extract_contraindications(text, case_profile_summary)
        if contraindications:
            extracted["contraindications"] = contraindications

    return extracted


def _resolve_domain(query: str, intent: str | None, answer_style: str | None) -> str | None:
    if any(marker in query for marker in _COOLING_TEA_MARKERS):
        return "cooling_tea"
    if answer_style == "dietary" or any(marker in query for marker in _DIETARY_MARKERS):
        return "dietary"
    if intent in {"symptom_diagnosis", "general_consultation"}:
        return "symptom"
    return None


def _build_clarification_context(collected: dict[str, str], *, domain: str) -> str | None:
    labels = _DOMAIN_SLOT_LABELS.get(domain, _SLOT_LABELS)
    parts = [
        f"{labels.get(key, _SLOT_LABELS.get(key, key))}：{value}"
        for key, value in collected.items()
        if _normalize_text(value)
    ]
    return "；".join(parts) if parts else None


def _is_slot_satisfied(
    slot: str,
    collected: dict[str, str],
    case_profile_summary: str | None,
) -> bool:
    if _has_case_profile_details(case_profile_summary, slot):
        return True

    value = collected.get(slot)
    if slot == "body_statuses":
        return _body_status_is_sufficient(value)

    return bool(_normalize_text(value))


def _build_follow_up_message(
    *,
    domain: str,
    pending_slots: list[str],
    collected: dict[str, str],
    interrupted: bool,
) -> str:
    first_slot = pending_slots[0]
    labels = _DOMAIN_SLOT_LABELS.get(domain, _SLOT_LABELS)
    questions = _DOMAIN_SLOT_QUESTIONS.get(domain, {})
    pending_labels = "、".join(labels.get(item, _SLOT_LABELS.get(item, item)) for item in pending_slots)
    collected_context = _build_clarification_context(collected, domain=domain)
    base_intro = _DOMAIN_INTROS.get(domain, "为了判断更准，我还差一些关键信息。")
    lead = (
        "你刚刚的新问题我记住了，不过我们先把这轮关键信息补齐。"
        if interrupted
        else base_intro
    )
    lines = [lead]
    if collected_context:
        lines.append(f"已收到：{collected_context}")
    lines.append(f"先补这一项：{questions.get(first_slot, '请继续补充相关信息。')}")
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
            if not _is_slot_satisfied(slot, collected, case_profile_summary)
        ]
        raw_state["pending_slots"] = pending_slots
        session.followup_state = raw_state

        if pending_slots:
            return FollowUpDecision(
                need_follow_up=True,
                follow_up_message=_build_follow_up_message(
                    domain=raw_state.get("domain") or "symptom",
                    pending_slots=pending_slots,
                    collected=collected,
                    interrupted=interrupted,
                ),
                effective_query=raw_state.get("latest_query") or raw_state.get("original_query") or query,
                clarification_context=_build_clarification_context(
                    collected,
                    domain=raw_state.get("domain") or "symptom",
                ),
                message_kind="followup",
            )

        effective_query = raw_state.get("latest_query") or raw_state.get("original_query") or query
        clarification_context = _build_clarification_context(
            collected,
            domain=raw_state.get("domain") or "symptom",
        )
        session.followup_state = {}
        return FollowUpDecision(
            need_follow_up=False,
            follow_up_message=None,
            effective_query=effective_query,
            clarification_context=clarification_context,
        )


followup_service = FollowUpService()
