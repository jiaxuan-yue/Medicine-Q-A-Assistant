"""长期体质画像与会话短期证候记忆服务。"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any


_CONSTITUTION_TYPES = (
    "平和",
    "气虚",
    "阳虚",
    "阴虚",
    "痰湿",
    "湿热",
    "血瘀",
    "气郁",
    "特禀",
)

_CONSTITUTION_SCORE_FIELDS = {
    "平和": "constitution_pinghe_score",
    "气虚": "constitution_qixu_score",
    "阳虚": "constitution_yangxu_score",
    "阴虚": "constitution_yinxu_score",
    "痰湿": "constitution_tanshi_score",
    "湿热": "constitution_shire_score",
    "血瘀": "constitution_xueyu_score",
    "气郁": "constitution_qiyu_score",
    "特禀": "constitution_tebing_score",
}

_TONGUE_FIELD_NAMES = (
    "tongue_image_url",
    "tongue_color",
    "tongue_coating",
    "tongue_shape",
    "tongue_constitution_hint",
    "tongue_raw_description",
)

_SHORT_TERM_LIMIT = 8
_SHORT_TERM_RECENCY_BASE = 0.985
_ACUTE_RECOVERY_GRACE_DAYS = 10
_DEFAULT_REASSESSMENT_CYCLE_DAYS = 90

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+")
_RESOLUTION_MARKERS = ("好了", "好多了", "恢复了", "痊愈", "缓解了", "已经好了", "不咳了", "退烧了", "没事了")
_UNRESOLVED_MARKERS = ("还没好", "没好", "还有", "仍然", "还是", "反复", "一直", "未恢复")
_TONIFY_MARKERS = ("补身体", "进补", "补一补", "滋补", "补气", "补血", "补脾", "补汤", "养身体", "补品")
_SYMPTOM_MARKERS = (
    "感冒",
    "发热",
    "低热",
    "怕冷",
    "恶寒",
    "咳嗽",
    "咽痛",
    "鼻塞",
    "流涕",
    "口苦",
    "口干",
    "尿黄",
    "长痘",
    "腹胀",
    "胃胀",
    "乏力",
    "失眠",
    "头痛",
    "腹泻",
    "便秘",
)
_ACUTE_EXTERNAL_MARKERS = ("感冒", "发热", "低热", "怕冷", "恶寒", "咽痛", "鼻塞", "流涕", "咳嗽", "头痛")
_ACUTE_HEAT_MARKERS = ("上火", "口苦", "口干", "咽痛", "尿黄", "长痘", "牙龈肿痛")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = re.split(r"[、，,；;\n]\s*", value)
    elif isinstance(value, list):
        items = value
    else:
        return []
    normalized: list[str] = []
    for item in items:
        text = _normalize_text(item)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_score(value: Any) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, int(round(numeric))))


def _normalize_optional_score(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return _normalize_score(value)


def _normalize_positive_int(value: Any, default: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, numeric)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = _normalize_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_list(values: list[str]) -> str | None:
    if not values:
        return None
    return "、".join(values)


def _humanize_recency(observed_at: datetime | None, *, now: datetime) -> str:
    if observed_at is None:
        return "时间未知"
    hours_passed = max(0.0, (now - observed_at).total_seconds() / 3600.0)
    if hours_passed < 6:
        return "6小时内"
    if hours_passed < 24:
        return "24小时内"
    if hours_passed < 24 * 3:
        return "3天内"
    if hours_passed < 24 * 7:
        return "7天内"
    return "较早记录"


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    normalized = _normalize_text(text).lower()
    for part in _TOKEN_RE.findall(normalized):
        token = part.strip()
        if not token:
            continue
        tokens.add(token)
        if all("\u4e00" <= char <= "\u9fff" for char in token):
            for n in (2, 3):
                if len(token) < n:
                    continue
                for index in range(len(token) - n + 1):
                    tokens.add(token[index : index + n])
    return tokens


def _lexical_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    if overlap == 0 or union == 0:
        return 0.0
    coverage = overlap / min(len(left_tokens), len(right_tokens))
    jaccard = overlap / union
    return max(0.0, min(1.0, (0.65 * coverage) + (0.35 * jaccard)))


def _split_symptoms(value: str) -> list[str]:
    items = _normalize_list(value)
    if items:
        return items
    hits = [marker for marker in _SYMPTOM_MARKERS if marker in value]
    deduped: list[str] = []
    for item in hits:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _has_resolution_signal(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(marker in normalized for marker in _RESOLUTION_MARKERS) and not any(
        marker in normalized for marker in _UNRESOLVED_MARKERS
    )


def _is_tonify_request(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(marker in normalized for marker in _TONIFY_MARKERS)


def _recency_score(observed_at: datetime | None, *, now: datetime) -> float:
    if observed_at is None:
        return 0.0
    hours_passed = max(0.0, (now - observed_at).total_seconds() / 3600.0)
    return max(0.0, min(1.0, _SHORT_TERM_RECENCY_BASE**hours_passed))


def _status_label(status: str) -> str:
    return {
        "active": "当前未过期",
        "resolved": "已恢复",
        "expired": "已过期",
    }.get(status, status)


def _read_value(source: Any, field_name: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(field_name)
    return getattr(source, field_name, None)


class PortraitMemoryService:
    def normalize_long_term_profile_payload(
        self,
        raw_payload: dict[str, Any] | None,
        *,
        allergy_history: str | None = None,
        medical_history: str | None = None,
    ) -> dict[str, Any]:
        payload = dict(raw_payload or {})
        scores = {
            field_name: _normalize_optional_score(payload.get(field_name))
            for field_name in _CONSTITUTION_SCORE_FIELDS.values()
        }

        explicit_primary = _normalize_text(payload.get("constitution_primary"))
        primary_constitution = explicit_primary if explicit_primary in _CONSTITUTION_TYPES else None
        named_scores = {
            constitution: score or 0
            for constitution, field_name in _CONSTITUTION_SCORE_FIELDS.items()
            for score in [scores.get(field_name)]
        }
        if primary_constitution is None and any(score > 0 for score in named_scores.values()):
            primary_constitution = max(named_scores.items(), key=lambda item: item[1])[0]

        secondary_constitutions = [
            item
            for item in _normalize_list(payload.get("constitution_secondary"))
            if item in _CONSTITUTION_TYPES and item != primary_constitution
        ]
        if not secondary_constitutions:
            ranked = sorted(named_scores.items(), key=lambda item: item[1], reverse=True)
            secondary_constitutions = [
                name
                for name, score in ranked
                if score > 0 and name != primary_constitution
            ][:2]

        allergies = _normalize_list(payload.get("allergy_history"))
        if not allergies and allergy_history:
            allergies = _normalize_list(allergy_history)

        chronic_symptoms = _normalize_list(payload.get("chronic_symptoms"))
        if not chronic_symptoms and medical_history:
            chronic_symptoms = _normalize_list(medical_history)

        dietary_restrictions = _normalize_list(
            payload.get("dietary_restrictions")
        )

        last_assessed_at = _parse_datetime(payload.get("constitution_assessed_at"))
        reassessment_cycle_days = _normalize_positive_int(
            payload.get("constitution_reassessment_cycle_days") or _DEFAULT_REASSESSMENT_CYCLE_DAYS,
            _DEFAULT_REASSESSMENT_CYCLE_DAYS,
        )

        normalized = {
            "chronic_symptoms": _serialize_list(chronic_symptoms),
            "dietary_restrictions": _serialize_list(dietary_restrictions),
            "constitution_primary": primary_constitution,
            "constitution_secondary": _serialize_list(secondary_constitutions),
            "constitution_assessed_at": last_assessed_at,
            "constitution_reassessment_cycle_days": reassessment_cycle_days,
        }
        normalized.update(scores)
        for field_name in _TONGUE_FIELD_NAMES:
            normalized[field_name] = _normalize_text(payload.get(field_name)) or None
        return normalized

    def serialize_long_term_profile_fields(
        self,
        source: Any,
        *,
        allergy_history: str | None = None,
        medical_history: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "constitution_primary": None,
            "constitution_secondary": [],
            "constitution_assessed_at": None,
            "constitution_reassessment_cycle_days": None,
            "chronic_symptoms": [],
            "dietary_restrictions": [],
        }
        for field_name in _CONSTITUTION_SCORE_FIELDS.values():
            payload[field_name] = None
        for field_name in _TONGUE_FIELD_NAMES:
            payload[field_name] = None

        profile = self.build_long_term_profile(
            source,
            allergy_history=allergy_history,
            medical_history=medical_history,
        )
        if not profile:
            return payload

        payload.update(
            {
                "constitution_primary": profile.get("primary_constitution"),
                "constitution_secondary": profile.get("secondary_constitutions") or [],
                "constitution_assessed_at": profile.get("last_assessed_at"),
                "constitution_reassessment_cycle_days": profile.get("reassessment_cycle_days"),
                "chronic_symptoms": profile.get("chronic_symptoms") or [],
                "dietary_restrictions": profile.get("dietary_restrictions") or [],
            }
        )
        for constitution, field_name in _CONSTITUTION_SCORE_FIELDS.items():
            payload[field_name] = profile.get("scores", {}).get(constitution)
        for field_name in _TONGUE_FIELD_NAMES:
            payload[field_name] = profile.get(field_name)
        return payload

    def build_long_term_profile(
        self,
        source: Any,
        *,
        allergy_history: str | None = None,
        medical_history: str | None = None,
    ) -> dict[str, Any]:
        scores = {
            constitution: _normalize_score(_read_value(source, field_name))
            for constitution, field_name in _CONSTITUTION_SCORE_FIELDS.items()
        }
        primary_constitution = _normalize_text(_read_value(source, "constitution_primary"))
        if primary_constitution not in _CONSTITUTION_TYPES:
            primary_constitution = None
        if primary_constitution is None and any(score > 0 for score in scores.values()):
            primary_constitution = max(scores.items(), key=lambda item: item[1])[0]

        secondary_constitutions = [
            item
            for item in _normalize_list(_read_value(source, "constitution_secondary"))
            if item in _CONSTITUTION_TYPES and item != primary_constitution
        ]
        if not secondary_constitutions:
            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            secondary_constitutions = [
                name
                for name, score in ranked
                if score > 0 and name != primary_constitution
            ][:2]

        allergies = _normalize_list(allergy_history or _read_value(source, "allergy_history"))
        chronic_symptoms = _normalize_list(_read_value(source, "chronic_symptoms"))
        if not chronic_symptoms and medical_history:
            chronic_symptoms = _normalize_list(medical_history)
        if not chronic_symptoms:
            chronic_symptoms = _normalize_list(_read_value(source, "medical_history"))

        dietary_restrictions = _normalize_list(_read_value(source, "dietary_restrictions"))
        assessed_at = _parse_datetime(_read_value(source, "constitution_assessed_at"))
        reassessment_cycle_days = _normalize_positive_int(
            _read_value(source, "constitution_reassessment_cycle_days") or _DEFAULT_REASSESSMENT_CYCLE_DAYS,
            _DEFAULT_REASSESSMENT_CYCLE_DAYS,
        )

        tongue_fields = {
            field_name: _normalize_text(_read_value(source, field_name)) or None
            for field_name in _TONGUE_FIELD_NAMES
        }
        tongue_constitution_hint = tongue_fields.get("tongue_constitution_hint")
        if primary_constitution is None and tongue_constitution_hint:
            for constitution in _CONSTITUTION_TYPES:
                if constitution in tongue_constitution_hint:
                    primary_constitution = constitution
                    break

        has_meaningful_content = (
            any(score > 0 for score in scores.values())
            or bool(allergies)
            or bool(chronic_symptoms)
            or bool(dietary_restrictions)
            or bool(assessed_at)
            or any(bool(value) for value in tongue_fields.values())
        )
        if not has_meaningful_content:
            return {}
        top_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]
        refresh_hint = "建议首次完成体质测评"
        if assessed_at is not None:
            age_days = max(0, (_utcnow() - assessed_at).days)
            if age_days >= reassessment_cycle_days:
                refresh_hint = "建议重新测评或根据近期反馈微调"
            elif age_days >= 30:
                refresh_hint = "一个月内可结合反馈微调"
            else:
                refresh_hint = "近期体质画像较新"

        return {
            "scores": scores,
            "primary_constitution": primary_constitution,
            "secondary_constitutions": secondary_constitutions,
            "allergy_history": allergies,
            "chronic_symptoms": chronic_symptoms,
            "dietary_restrictions": dietary_restrictions,
            "last_assessed_at": _serialize_datetime(assessed_at),
            "reassessment_cycle_days": reassessment_cycle_days,
            "top_scores": top_scores,
            "refresh_hint": refresh_hint,
            **tongue_fields,
        }

    def infer_constitution_label(
        self,
        long_term_profile: dict[str, Any] | None,
    ) -> str | None:
        if not long_term_profile:
            return None
        primary = _normalize_text(long_term_profile.get("primary_constitution"))
        if primary in _CONSTITUTION_TYPES:
            return primary
        top_scores = long_term_profile.get("top_scores") or []
        if top_scores:
            name, score = top_scores[0]
            if score > 0:
                return name
        return None

    def normalize_syndrome_memory(self, raw_memory: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        now = _utcnow()
        normalized: list[dict[str, Any]] = []
        for item in raw_memory or []:
            if not isinstance(item, dict):
                continue
            recorded_at = _parse_datetime(item.get("recorded_at")) or now
            last_seen_at = _parse_datetime(item.get("last_seen_at")) or recorded_at
            expires_at = _parse_datetime(item.get("expires_at"))
            status = _normalize_text(item.get("status")) or "active"
            if status == "active" and expires_at and expires_at < now:
                status = "expired"
            normalized.append(
                {
                    "summary": _normalize_text(item.get("summary")),
                    "symptoms": _normalize_list(item.get("symptoms")),
                    "duration": _normalize_text(item.get("duration")) or None,
                    "severity": _normalize_text(item.get("severity")) or None,
                    "body_statuses": _normalize_text(item.get("body_statuses")) or None,
                    "contraindications": _normalize_text(item.get("contraindications")) or None,
                    "syndrome_kind": _normalize_text(item.get("syndrome_kind")) or "general",
                    "risk_tags": _normalize_list(item.get("risk_tags")),
                    "status": status,
                    "source_message_id": _normalize_text(item.get("source_message_id")) or None,
                    "recorded_at": _serialize_datetime(recorded_at),
                    "last_seen_at": _serialize_datetime(last_seen_at),
                    "expires_at": _serialize_datetime(expires_at),
                    "resolved_at": _serialize_datetime(_parse_datetime(item.get("resolved_at"))),
                }
            )
        normalized.sort(
            key=lambda item: _parse_datetime(item.get("last_seen_at")) or now,
            reverse=True,
        )
        return normalized[:_SHORT_TERM_LIMIT]

    def update_session_syndrome_memory(
        self,
        *,
        syndrome_memory: list[dict[str, Any]] | None,
        latest_query: str,
        answer_style: str,
        consultation_context: dict[str, Any] | None = None,
        source_message_id: str | None = None,
    ) -> list[dict[str, Any]]:
        now = _utcnow()
        memories = self.normalize_syndrome_memory(syndrome_memory)
        memories = [self._refresh_memory_status(item, now=now) for item in memories]

        if answer_style == "chat":
            return memories[:_SHORT_TERM_LIMIT]

        if _has_resolution_signal(latest_query):
            for item in memories:
                if item["status"] != "active":
                    continue
                if self._memory_matches_resolution(item, latest_query):
                    item["status"] = "resolved"
                    item["resolved_at"] = _serialize_datetime(now)
                    item["last_seen_at"] = _serialize_datetime(now)

        candidate = self._build_syndrome_candidate(
            latest_query=latest_query,
            consultation_context=consultation_context,
            source_message_id=source_message_id,
            now=now,
        )
        if candidate:
            merged = False
            for item in memories:
                if item["status"] != "active":
                    continue
                if self._memory_overlaps(item, candidate):
                    item["summary"] = candidate["summary"] or item["summary"]
                    item["symptoms"] = self._merge_lists(item.get("symptoms"), candidate.get("symptoms"))
                    item["duration"] = candidate["duration"] or item["duration"]
                    item["severity"] = candidate["severity"] or item["severity"]
                    item["body_statuses"] = candidate["body_statuses"] or item["body_statuses"]
                    item["contraindications"] = candidate["contraindications"] or item["contraindications"]
                    item["risk_tags"] = self._merge_lists(item.get("risk_tags"), candidate.get("risk_tags"))
                    item["syndrome_kind"] = candidate["syndrome_kind"] or item["syndrome_kind"]
                    item["source_message_id"] = source_message_id or item["source_message_id"]
                    item["last_seen_at"] = candidate["last_seen_at"]
                    item["expires_at"] = candidate["expires_at"]
                    merged = True
                    break
            if not merged:
                memories.insert(0, candidate)

        memories = [self._refresh_memory_status(item, now=now) for item in memories]
        memories.sort(
            key=lambda item: _parse_datetime(item.get("last_seen_at")) or now,
            reverse=True,
        )
        return memories[:_SHORT_TERM_LIMIT]

    def retrieve_relevant_short_term_memories(
        self,
        *,
        query: str,
        syndrome_memory: list[dict[str, Any]] | None,
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        now = _utcnow()
        memories = self.normalize_syndrome_memory(syndrome_memory)
        is_tonify_request = _is_tonify_request(query)
        ranked: list[dict[str, Any]] = []

        for item in memories:
            item = self._refresh_memory_status(item, now=now)
            if item["status"] == "expired" and not self._should_surface_expired_memory(item, query=query, now=now):
                continue
            similarity = _lexical_similarity(
                query,
                " ".join(
                    filter(
                        None,
                        [
                            item.get("summary"),
                            "、".join(item.get("symptoms", [])),
                            item.get("body_statuses"),
                        ],
                    )
                ),
            )
            recency = _recency_score(_parse_datetime(item.get("last_seen_at")), now=now)
            score = (0.4 * similarity) + (0.6 * recency)
            if item["status"] == "active":
                score += 0.05
            if is_tonify_request and "avoid_tonifying_until_resolved" in item.get("risk_tags", []):
                score += 0.25
            ranked.append(
                {
                    **item,
                    "score": round(min(1.0, score), 4),
                    "freshness_hint": _humanize_recency(_parse_datetime(item.get("last_seen_at")), now=now),
                    "status_label": _status_label(item["status"]),
                }
            )

        ranked.sort(key=lambda item: (item["score"], item["status"] == "active"), reverse=True)
        return ranked[:limit]

    def build_short_term_guardrail(
        self,
        *,
        query: str,
        syndrome_memory: list[dict[str, Any]] | None,
    ) -> str | None:
        if not _is_tonify_request(query):
            return None
        risky_memory = self._find_recent_unresolved_acute_memory(syndrome_memory)
        if not risky_memory:
            return None
        symptoms = "、".join(risky_memory.get("symptoms", [])[:3]) or risky_memory.get("summary") or "近期不适"
        freshness = _humanize_recency(_parse_datetime(risky_memory.get("last_seen_at")), now=_utcnow())
        return (
            f"短期证候记忆提示：{freshness} 记录过“{symptoms}”，当前未确认是否已痊愈；"
            "若仍处于外感或实热阶段，不宜直接推荐偏补方案。"
        )

    def build_recovery_followup(
        self,
        *,
        query: str,
        syndrome_memory: list[dict[str, Any]] | None,
    ) -> dict[str, str] | None:
        if not _is_tonify_request(query) or _has_resolution_signal(query):
            return None
        risky_memory = self._find_recent_unresolved_acute_memory(syndrome_memory)
        if not risky_memory:
            return None
        symptoms = "、".join(risky_memory.get("symptoms", [])[:2]) or risky_memory.get("summary") or "上次不适"
        return {
            "question": (
                f"你上次提到的{symptoms}现在已经完全恢复了吗？"
                "如果还有发热、咽痛、怕冷或咳嗽，暂时先别直接进补。"
            ),
            "note": f"近期有未确认恢复的急性证候：{symptoms}",
        }

    def _build_syndrome_candidate(
        self,
        *,
        latest_query: str,
        consultation_context: dict[str, Any] | None,
        source_message_id: str | None,
        now: datetime,
    ) -> dict[str, Any] | None:
        slots = consultation_context or {}
        primary_symptom = _normalize_text(slots.get("primary_symptom"))
        accompanying = _normalize_text(slots.get("accompanying_symptoms"))
        duration = _normalize_text(slots.get("duration")) or None
        severity = _normalize_text(slots.get("severity")) or None
        body_statuses = _normalize_text(slots.get("body_statuses")) or None
        contraindications = _normalize_text(slots.get("contraindications")) or None

        if _has_resolution_signal(latest_query) and not any(
            [primary_symptom, accompanying, duration, severity, body_statuses]
        ):
            return None

        symptoms = self._merge_lists(
            _split_symptoms(primary_symptom),
            _split_symptoms(accompanying or latest_query),
        )
        if not symptoms and not any([primary_symptom, accompanying, duration, severity, body_statuses]):
            return None

        combined = " ".join(filter(None, [latest_query, primary_symptom, accompanying, body_statuses]))
        syndrome_kind = "general"
        if any(marker in combined for marker in _ACUTE_EXTERNAL_MARKERS):
            syndrome_kind = "acute_external"
        elif any(marker in combined for marker in _ACUTE_HEAT_MARKERS):
            syndrome_kind = "acute_heat"

        risk_tags: list[str] = []
        if syndrome_kind in {"acute_external", "acute_heat"}:
            risk_tags.append("avoid_tonifying_until_resolved")

        summary_parts: list[str] = []
        if primary_symptom:
            summary_parts.append(f"主症状：{primary_symptom}")
        elif symptoms:
            summary_parts.append(f"主症状：{'、'.join(symptoms[:3])}")
        if duration:
            summary_parts.append(f"持续：{duration}")
        if severity:
            summary_parts.append(f"程度：{severity}")
        if accompanying:
            summary_parts.append(f"伴随：{accompanying}")
        if body_statuses:
            summary_parts.append(f"状态：{body_statuses}")
        summary = "；".join(summary_parts) or _normalize_text(latest_query)[:64]

        expiry_days = 7 if syndrome_kind in {"acute_external", "acute_heat"} else 5
        return {
            "summary": summary,
            "symptoms": symptoms[:6],
            "duration": duration,
            "severity": severity,
            "body_statuses": body_statuses,
            "contraindications": contraindications,
            "syndrome_kind": syndrome_kind,
            "risk_tags": risk_tags,
            "status": "active",
            "source_message_id": source_message_id,
            "recorded_at": _serialize_datetime(now),
            "last_seen_at": _serialize_datetime(now),
            "expires_at": _serialize_datetime(now + timedelta(days=expiry_days)),
            "resolved_at": None,
        }

    def _memory_matches_resolution(self, memory: dict[str, Any], query: str) -> bool:
        symptom_text = " ".join(memory.get("symptoms", [])) or memory.get("summary", "")
        similarity = _lexical_similarity(query, symptom_text)
        if similarity >= 0.15:
            return True
        normalized_query = _normalize_text(query)
        for symptom in memory.get("symptoms", []):
            normalized_symptom = _normalize_text(symptom)
            if not normalized_symptom:
                continue
            if normalized_symptom in normalized_query:
                return True
            symptom_stem = normalized_symptom[:1]
            if symptom_stem and any(marker in normalized_query for marker in (f"不{symptom_stem}", f"没{symptom_stem}")):
                return True
        return False

    def _memory_overlaps(self, memory: dict[str, Any], candidate: dict[str, Any]) -> bool:
        existing_symptoms = set(memory.get("symptoms") or [])
        incoming_symptoms = set(candidate.get("symptoms") or [])
        if existing_symptoms & incoming_symptoms:
            return True
        similarity = _lexical_similarity(memory.get("summary", ""), candidate.get("summary", ""))
        return similarity >= 0.4 and memory.get("syndrome_kind") == candidate.get("syndrome_kind")

    def _refresh_memory_status(self, memory: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        refreshed = dict(memory)
        expires_at = _parse_datetime(refreshed.get("expires_at"))
        if refreshed.get("status") == "active" and expires_at and expires_at < now:
            refreshed["status"] = "expired"
        return refreshed

    def _should_surface_expired_memory(
        self,
        memory: dict[str, Any],
        *,
        query: str,
        now: datetime,
    ) -> bool:
        if "avoid_tonifying_until_resolved" not in memory.get("risk_tags", []):
            return False
        if not _is_tonify_request(query):
            return False
        last_seen_at = _parse_datetime(memory.get("last_seen_at"))
        if last_seen_at is None:
            return False
        return now - last_seen_at <= timedelta(days=_ACUTE_RECOVERY_GRACE_DAYS)

    def _find_recent_unresolved_acute_memory(
        self,
        syndrome_memory: list[dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
        now = _utcnow()
        memories = self.normalize_syndrome_memory(syndrome_memory)
        for item in memories:
            item = self._refresh_memory_status(item, now=now)
            if "avoid_tonifying_until_resolved" not in item.get("risk_tags", []):
                continue
            if item.get("status") == "resolved":
                continue
            last_seen_at = _parse_datetime(item.get("last_seen_at"))
            if last_seen_at is None:
                continue
            if now - last_seen_at <= timedelta(days=_ACUTE_RECOVERY_GRACE_DAYS):
                return item
        return None

    @staticmethod
    def _merge_lists(left: list[str] | None, right: list[str] | None) -> list[str]:
        merged: list[str] = []
        for item in list(left or []) + list(right or []):
            normalized = _normalize_text(item)
            if normalized and normalized not in merged:
                merged.append(normalized)
        return merged


portrait_memory_service = PortraitMemoryService()
