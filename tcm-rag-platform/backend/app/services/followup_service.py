"""会话级追问器：基于缺失槽位的轻量追问状态机。"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


_QUESTION_MARKERS = ("？", "?", "怎么", "为何", "为什么", "如何", "能不能", "可以吗", "是不是", "要不要")
_DIETARY_MARKERS = ("凉茶", "代茶饮", "煲汤", "药膳", "泡茶", "茶饮", "食疗", "推荐")
_COOLING_TEA_MARKERS = ("凉茶", "清热", "降火", "祛湿茶", "清火", "下火", "败火")
_NEW_TOPIC_PREFIXES = ("我想问", "我其实想问", "另外", "换个问题", "再问一个", "还有个问题", "顺便问下")
_TREATMENT_CONTINUATION_MARKERS = (
    "中药",
    "汤药",
    "颗粒",
    "方子",
    "凉茶",
    "代茶饮",
    "食疗",
    "药膳",
    "泡茶",
    "茶饮",
    "喝一些",
    "喝点",
    "喝什么",
    "改喝",
    "换成",
    "而不是",
)
_UNINFORMATIVE_REPLY_PATTERNS = (
    re.compile(r"^(不太清楚|不清楚|不知道|不确定|记不清|说不好|不好说|还是说不好|还是不清楚)$"),
    re.compile(r"^(暂时|目前)?(补不了|说不出|答不上来)(更多|了)?$"),
)
_LOW_CONFIDENCE_DURATION_MARKERS = {"最近", "这几天", "这几周", "这几个月", "今天", "昨天", "前天"}

_DURATION_PATTERNS = [
    re.compile(r"((?:近|约|差不多)?[一二三四五六七八九十两半\d]+(?:个)?(?:小时|天|周|星期|个月|月|年))"),
    re.compile(r"(昨天|今天|前天|最近|这几天|这几周|这几个月|长期|一直|断断续续)"),
]

_SEVERITY_PATTERNS = [
    re.compile(r"(很严重|比较严重|挺严重|非常严重|厉害|明显|影响睡眠|影响吃饭|影响工作|轻微)"),
]

_CONTRAINDICATION_PATTERNS = [
    re.compile(r"(怀孕|妊娠|备孕|哺乳|过敏|高血压|糖尿病|痛风|肾病|肝病|慢性病|正在用药|吃药)"),
]

_SYMPTOM_HINTS = (
    "感冒",
    "脖子酸",
    "脖子疼",
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
_APPETITE_STATUS_MARKERS = (
    "胃口差",
    "胃口有点差",
    "胃口有一点差",
    "胃口不好",
    "胃口不是很好",
    "食欲差",
    "食欲有点差",
    "食欲有一点差",
    "食欲不好",
    "食欲不是很好",
    "没胃口",
    "吃得少",
    "食欲一般",
    "胃口一般",
    "胃口还行",
    "能吃",
)
_BOWEL_STATUS_MARKERS = (
    "腹泻",
    "便秘",
    "大便稀",
    "大便偏稀",
    "大便干",
    "大便偏干",
    "便溏",
    "二便正常",
    "大小便正常",
    "大便正常",
    "小便正常",
    "小便黄",
    "尿黄",
)
_HEAT_COLD_STATUS_MARKERS = ("怕冷", "怕热", "口干", "口苦", "手脚凉", "容易上火", "发热", "畏寒")

_BODY_STATUS_DIMENSIONS = ("sleep", "appetite", "bowel", "temperature")
_MAX_FOLLOWUP_ROUNDS = 3
_EPISODE_SLOTS = ("primary_symptom", "duration", "severity", "accompanying_symptoms")
_GENERAL_CONTEXT_SLOTS = ("body_statuses", "contraindications")
_BODY_STATUS_TARGETS = tuple(f"body_status.{dimension}" for dimension in _BODY_STATUS_DIMENSIONS)

_SEVERITY_NEGATIVE_PATTERNS = [
    re.compile(r"(不影响(?:睡眠|吃饭|工作|日常生活)(?:[、和及与](?:睡眠|吃饭|工作|日常生活))*)"),
    re.compile(r"(不严重|不算严重|问题不大|比较轻|轻微)"),
]

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
    collected_slots: dict[str, str] | None = None
    question_target: str | None = None
    round_count: int = 0
    domain: str | None = None


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _is_uninformative_reply(text: str) -> bool:
    normalized = _normalize_text(text).strip(" ，,。；;！!？?")
    if not normalized:
        return True
    return any(pattern.fullmatch(normalized) for pattern in _UNINFORMATIVE_REPLY_PATTERNS)


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


def _copy_slot_map(value: dict[str, Any] | None) -> dict[str, str]:
    copied: dict[str, str] = {}
    for key in _SLOT_LABELS:
        normalized = _normalize_text((value or {}).get(key))
        if normalized:
            copied[key] = normalized
    return copied


def _target_to_slot(target: str) -> str:
    if target.startswith("body_status."):
        return "body_statuses"
    return target


def _body_dimension_for_target(target: str) -> str | None:
    if not target.startswith("body_status."):
        return None
    _, _, dimension = target.partition(".")
    return dimension or None


def _required_targets_for_domain(domain: str | None) -> list[str]:
    targets: list[str] = []
    for slot in _DOMAIN_SLOTS.get(domain, []):
        if slot == "body_statuses":
            targets.extend(_BODY_STATUS_TARGETS)
        else:
            targets.append(slot)
    return targets


def _split_items(value: str) -> list[str]:
    items: list[str] = []
    for item in re.split(r"[、，,；;]\s*", value):
        normalized = _normalize_text(item)
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _slot_values_overlap(left: str | None, right: str | None) -> bool:
    left_text = _normalize_text(left)
    right_text = _normalize_text(right)
    if not left_text or not right_text:
        return False
    left_items = _split_items(left_text)
    right_items = _split_items(right_text)
    return any(item in other or other in item for item in left_items for other in right_items)


def _has_case_profile_body_dimension(case_profile_summary: str | None, dimension: str) -> bool:
    summary = _normalize_text(case_profile_summary)
    if not summary:
        return False
    markers_by_dimension = {
        "sleep": ("睡眠", "失眠", "多梦", "易醒", "入睡困难"),
        "appetite": ("胃口", "食欲", "没胃口", "吃得少"),
        "bowel": ("二便", "大便", "小便", "腹泻", "便秘"),
        "temperature": ("怕冷", "怕热", "畏寒", "口干", "口苦", "发热"),
    }
    return any(marker in summary for marker in markers_by_dimension.get(dimension, ()))


def _looks_like_new_question(text: str) -> bool:
    text = _normalize_text(text)
    if not text:
        return False
    return any(marker in text for marker in _QUESTION_MARKERS) or any(
        text.startswith(prefix) for prefix in _NEW_TOPIC_PREFIXES
    )


def _looks_like_treatment_request(text: str) -> bool:
    return any(marker in text for marker in _TREATMENT_CONTINUATION_MARKERS)


def _extract_duration(text: str) -> str | None:
    for pattern in _DURATION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _extract_severity(text: str) -> str | None:
    for pattern in _SEVERITY_NEGATIVE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
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
    def collect_hits(markers: tuple[str, ...]) -> list[str]:
        hits: list[str] = []
        for marker in sorted(markers, key=len, reverse=True):
            if marker not in text:
                continue
            if any(marker in existing or existing in marker for existing in hits):
                continue
            hits.append(marker)
        return hits[:2]

    result: dict[str, str] = {}

    sleep_hits = collect_hits(_SLEEP_STATUS_MARKERS)
    if sleep_hits:
        result["sleep"] = "、".join(sleep_hits)

    appetite_hits = collect_hits(_APPETITE_STATUS_MARKERS)
    if appetite_hits:
        result["appetite"] = "、".join(appetite_hits)

    bowel_hits = collect_hits(_BOWEL_STATUS_MARKERS)
    if bowel_hits:
        result["bowel"] = "、".join(bowel_hits)

    heat_cold_hits = collect_hits(_HEAT_COLD_STATUS_MARKERS)
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
        appetite_value = _normalize_status_value(status_map["appetite"], "胃口")
        appetite_value = _normalize_status_value(appetite_value, "食欲")
        parts.append(f"胃口{appetite_value}")
    if status_map.get("bowel"):
        bowel_value = _normalize_status_value(status_map['bowel'], '大便')
        bowel_value = _normalize_status_value(bowel_value, '二便')
        bowel_value = _normalize_status_value(bowel_value, '大小便')
        bowel_value = _normalize_status_value(bowel_value, '小便')
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
    if _is_uninformative_reply(text):
        return None
    if "伴" in text or "还有" in text or "同时" in text:
        for marker in ("还有", "还伴", "伴有", "同时", "并且"):
            if marker in text:
                tail = text.split(marker, 1)[-1].strip(" ，,。；;")
                if tail and tail != text:
                    return tail[:48]
    hints = [item for item in _SYMPTOM_HINTS if item in text]
    if len(hints) >= 2:
        return "、".join(hints[1:4])
    return None


def _extract_primary_symptom(text: str, *, allow_fallback: bool = True) -> str | None:
    hints = [item for item in _SYMPTOM_HINTS if item in text]
    if hints:
        return "、".join(hints[:2])

    if not allow_fallback:
        return None

    stripped = _normalize_text(text)
    stripped = re.sub(r"^(我现在|我这两天|我最近|最近|想问一下|请问|帮我看下)", "", stripped)
    stripped = re.sub(r"(怎么办|怎么调理|怎么处理|怎么回事|可以吗|能不能).*?$", "", stripped)
    stripped = stripped.strip(" ，,。；;")
    if _is_uninformative_reply(stripped):
        return None
    if any(marker in stripped for marker in _TREATMENT_CONTINUATION_MARKERS):
        return None
    if 2 <= len(stripped) <= 24:
        return stripped
    return None


def _extract_slots(
    text: str,
    *,
    domain: str,
    case_profile_summary: str | None,
    allow_primary_fallback: bool = True,
    focused_slot: str | None = None,
) -> dict[str, str]:
    extracted: dict[str, str] = {}
    if allow_primary_fallback or focused_slot == "primary_symptom":
        primary = _extract_primary_symptom(
            text,
            allow_fallback=allow_primary_fallback or focused_slot == "primary_symptom",
        )
        if primary:
            extracted["primary_symptom"] = primary

    duration = _extract_duration(text)
    if duration and not (
        duration in _LOW_CONFIDENCE_DURATION_MARKERS
        and _looks_like_treatment_request(text)
        and not any(marker in text for marker in _SYMPTOM_HINTS)
    ):
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


def _merge_slot_value(slot: str, existing: str | None, incoming: str | None) -> str | None:
    existing_text = _normalize_text(existing)
    incoming_text = _normalize_text(incoming)
    if not existing_text:
        return incoming_text or None
    if not incoming_text:
        return existing_text

    if slot == "body_statuses":
        merged_status_map = {
            **_extract_body_status_details(existing_text),
            **_extract_body_status_details(incoming_text),
        }
        rendered = _render_body_status_map(merged_status_map)
        return rendered or existing_text

    if slot == "accompanying_symptoms":
        merged_items: list[str] = []
        for raw in (existing_text, incoming_text):
            for item in re.split(r"[、，,；;]\s*", raw):
                normalized_item = _normalize_text(item)
                if normalized_item and normalized_item not in merged_items:
                    merged_items.append(normalized_item)
        return "、".join(merged_items) if merged_items else existing_text

    # For scalar slots, prefer the latest explicit answer.
    return incoming_text


def merge_consultation_context(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, str]:
    merged = _copy_slot_map(existing)
    for key, value in _copy_slot_map(incoming).items():
        merged_value = _merge_slot_value(key, merged.get(key), value)
        if merged_value:
            merged[key] = merged_value
    return merged


def build_consultation_context_summary(slots: dict[str, Any] | None) -> str | None:
    copied = _copy_slot_map(slots)
    parts = [f"{_SLOT_LABELS.get(key, key)}：{value}" for key, value in copied.items()]
    return "；".join(parts) if parts else None


def _resolve_domain(query: str, intent: str | None, answer_style: str | None) -> str | None:
    if any(marker in query for marker in _COOLING_TEA_MARKERS):
        return "cooling_tea"
    if answer_style == "dietary" or any(marker in query for marker in _DIETARY_MARKERS):
        return "dietary"
    if intent in {"symptom_diagnosis", "general_consultation"}:
        return "symptom"
    return None


def _should_reuse_episode_context(
    query: str,
    *,
    extracted: dict[str, str],
    known_context: dict[str, str],
) -> bool:
    known_primary = known_context.get("primary_symptom")
    if not _normalize_text(known_primary):
        return False

    incoming_primary = extracted.get("primary_symptom")
    if incoming_primary and _slot_values_overlap(incoming_primary, known_primary):
        return True

    if not incoming_primary and any(marker in query for marker in _TREATMENT_CONTINUATION_MARKERS):
        return True

    if not incoming_primary and any(_normalize_text(extracted.get(slot)) for slot in _EPISODE_SLOTS[1:]):
        return True

    return False


def _seed_known_context(
    *,
    domain: str,
    query: str,
    extracted: dict[str, str],
    known_context: dict[str, Any] | None,
) -> dict[str, str]:
    required_slots = set(_DOMAIN_SLOTS.get(domain, []))
    known = _copy_slot_map(known_context)
    if not known:
        return {}

    seeded: dict[str, str] = {}
    for slot in _GENERAL_CONTEXT_SLOTS:
        if slot in required_slots and _normalize_text(known.get(slot)):
            seeded[slot] = known[slot]

    if _should_reuse_episode_context(query, extracted=extracted, known_context=known):
        for slot in _EPISODE_SLOTS:
            if slot in required_slots and _normalize_text(known.get(slot)):
                seeded[slot] = known[slot]

    return seeded


def _build_clarification_context(collected: dict[str, str], *, domain: str) -> str | None:
    labels = _DOMAIN_SLOT_LABELS.get(domain, _SLOT_LABELS)
    parts = [
        f"{labels.get(key, _SLOT_LABELS.get(key, key))}：{value}"
        for key, value in collected.items()
        if _normalize_text(value)
    ]
    return "；".join(parts) if parts else None


def _is_target_satisfied(
    target: str,
    collected: dict[str, str],
    case_profile_summary: str | None,
) -> bool:
    dimension = _body_dimension_for_target(target)
    if dimension:
        if _has_case_profile_body_dimension(case_profile_summary, dimension):
            return True
        detail_map = _extract_body_status_details(collected.get("body_statuses", ""))
        return bool(_normalize_text(detail_map.get(dimension)))

    slot = _target_to_slot(target)
    if _has_case_profile_details(case_profile_summary, slot):
        return True

    value = collected.get(slot)
    return bool(_normalize_text(value))


def _default_question_for_target(domain: str, target: str) -> str:
    if target == "body_status.sleep":
        return "最近睡眠怎么样，有没有入睡困难、容易醒或多梦？"
    if target == "body_status.appetite":
        return "最近胃口怎么样，吃得下吗，有没有明显食欲差？"
    if target == "body_status.bowel":
        return "最近二便怎么样，大便和小便基本正常吗？"
    if target == "body_status.temperature":
        return "现在整体更偏怕冷还是怕热？"
    questions = _DOMAIN_SLOT_QUESTIONS.get(domain, {})
    return questions.get(_target_to_slot(target), "请继续补充相关信息。")


def _build_follow_up_message(
    *,
    domain: str,
    target: str,
    current_round: int,
    max_rounds: int,
) -> str:
    question = _default_question_for_target(domain, target)
    lines = [
        f"第 {current_round} 问 / 共 {max_rounds} 问",
        question,
        "直接回复这一项就可以，我收到后继续。",
    ]
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
        known_context: dict[str, Any] | None = None,
    ) -> FollowUpDecision:
        raw_state = deepcopy(session.followup_state or {})
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
                required_targets = _required_targets_for_domain(domain)
                collected = merge_consultation_context(
                    _seed_known_context(
                        domain=domain or "symptom",
                        query=query,
                        extracted=collected,
                        known_context=known_context,
                    ),
                    collected,
                )
                raw_state = {
                    "active": True,
                    "domain": domain,
                    "original_query": query,
                    "latest_query": query,
                    "required_targets": required_targets,
                    "collected": collected,
                    "round_count": 0,
                    "asked_targets": [],
                }
            else:
                collected = dict(raw_state.get("collected", {}))
                last_asked_target = raw_state.get("last_asked_target")
                extracted = _extract_slots(
                    query,
                    domain=domain,
                    case_profile_summary=case_profile_summary,
                    allow_primary_fallback=False,
                    focused_slot=_target_to_slot(last_asked_target) if isinstance(last_asked_target, str) else None,
                )
                new_slots: list[str] = []
                for key, value in extracted.items():
                    merged_value = _merge_slot_value(key, collected.get(key), value)
                    if merged_value and _normalize_text(merged_value) != _normalize_text(collected.get(key)):
                        collected[key] = merged_value
                        new_slots.append(key)
                raw_state["collected"] = collected
                raw_state["last_reply_new_slots"] = new_slots
                required_targets = list(raw_state.get("required_targets", _required_targets_for_domain(domain)))
        else:
            domain = _resolve_domain(query, intent, answer_style)
            if not domain:
                return FollowUpDecision(
                    need_follow_up=False,
                    follow_up_message=None,
                    effective_query=query,
                    clarification_context=None,
                    collected_slots={},
                )
            collected = _extract_slots(
                query,
                domain=domain,
                case_profile_summary=case_profile_summary,
            )
            required_targets = _required_targets_for_domain(domain)
            collected = merge_consultation_context(
                _seed_known_context(
                    domain=domain,
                    query=query,
                    extracted=collected,
                    known_context=known_context,
                ),
                collected,
            )
            raw_state = {
                "active": True,
                "domain": domain,
                "original_query": query,
                "latest_query": query,
                "required_targets": required_targets,
                "collected": collected,
                "round_count": 0,
                "asked_targets": [],
            }

        pending_targets = [
            target
            for target in required_targets
            if not _is_target_satisfied(target, collected, case_profile_summary)
        ]
        raw_state["pending_targets"] = pending_targets

        if pending_targets:
            asked_targets = [
                target
                for target in (raw_state.get("asked_targets") or raw_state.get("asked_slots") or [])
                if isinstance(target, str) and target
            ]
            next_target = next((target for target in pending_targets if target not in asked_targets), None)
            if not next_target:
                session.followup_state = {}
                return FollowUpDecision(
                    need_follow_up=False,
                    follow_up_message=None,
                    effective_query=raw_state.get("latest_query") or raw_state.get("original_query") or query,
                    clarification_context=_build_clarification_context(
                        collected,
                        domain=raw_state.get("domain") or "symptom",
                    ),
                    message_kind="answer",
                    collected_slots=_copy_slot_map(collected),
                    domain=raw_state.get("domain"),
                )

            round_count = int(raw_state.get("round_count", 0) or 0)
            if round_count >= _MAX_FOLLOWUP_ROUNDS:
                session.followup_state = {}
                return FollowUpDecision(
                    need_follow_up=False,
                    follow_up_message=None,
                    effective_query=raw_state.get("latest_query") or raw_state.get("original_query") or query,
                    clarification_context=_build_clarification_context(
                        collected,
                        domain=raw_state.get("domain") or "symptom",
                    ),
                    message_kind="answer",
                    collected_slots=_copy_slot_map(collected),
                    domain=raw_state.get("domain"),
                )

            current_round = round_count + 1
            raw_state["round_count"] = current_round
            raw_state["asked_targets"] = [*asked_targets, next_target]
            raw_state["last_asked_target"] = next_target
            session.followup_state = raw_state
            return FollowUpDecision(
                need_follow_up=True,
                follow_up_message=_build_follow_up_message(
                    domain=raw_state.get("domain") or "symptom",
                    target=next_target,
                    current_round=current_round,
                    max_rounds=_MAX_FOLLOWUP_ROUNDS,
                ),
                effective_query=raw_state.get("latest_query") or raw_state.get("original_query") or query,
                clarification_context=_build_clarification_context(
                    collected,
                    domain=raw_state.get("domain") or "symptom",
                ),
                message_kind="followup",
                collected_slots=_copy_slot_map(collected),
                question_target=next_target,
                round_count=current_round,
                domain=raw_state.get("domain"),
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
            collected_slots=_copy_slot_map(collected),
            domain=raw_state.get("domain"),
        )


followup_service = FollowUpService()
