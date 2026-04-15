"""煲汤/茶饮生成上下文聚合服务。"""

from __future__ import annotations

import re

from app.services.live_context_service import get_current_solar_term

_EXPLICIT_CONSTITUTIONS = (
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

_CONSTITUTION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("阳虚", ("怕冷", "畏寒", "手脚凉", "喜热饮", "清晨腹泻", "大便溏", "易受凉")),
    ("阴虚", ("口干", "咽燥", "手足心热", "盗汗", "烦热", "失眠", "舌红少津")),
    ("痰湿", ("痰多", "困重", "胸闷", "肥胖", "苔腻", "腹胀", "身体沉重")),
    ("湿热", ("口苦", "口黏", "小便黄", "长痘", "苔黄腻", "烦躁", "湿热")),
    ("气虚", ("乏力", "易累", "少气", "懒言", "气短", "易感冒", "食少")),
    ("血瘀", ("刺痛", "舌暗", "面色晦暗", "经血有块", "固定疼痛")),
    ("气郁", ("情绪低落", "郁闷", "焦虑", "胁胀", "易叹气", "胸胁不舒")),
]

_LOCATION_PATTERNS = [
    re.compile(r"(?:地点|位置|居住地|所在地|常住地)[:：]?\s*([^\s；，,。]+)"),
    re.compile(r"(北京|上海|广州|深圳|佛山|东莞|珠海|中山|惠州|成都|重庆|杭州|苏州|南京|武汉|长沙|西安|天津)"),
]


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()
def infer_user_constitution(case_profile_summary: str | None, user_query: str = "") -> str:
    combined = f"{_normalize_text(case_profile_summary)} {_normalize_text(user_query)}"
    explicit = re.search(r"(平和|气虚|阳虚|阴虚|痰湿|湿热|血瘀|气郁|特禀)体质", combined)
    if explicit:
        return explicit.group(1)

    for name in _EXPLICIT_CONSTITUTIONS:
        if name in combined:
            return name

    for constitution, keywords in _CONSTITUTION_RULES:
        if any(keyword in combined for keyword in keywords):
            return constitution

    return "体质信息不足，按平和偏保守处理"


def extract_location_hint(case_profile_summary: str | None, user_query: str = "") -> str | None:
    combined = f"{_normalize_text(case_profile_summary)} {_normalize_text(user_query)}"
    for pattern in _LOCATION_PATTERNS:
        match = pattern.search(combined)
        if match:
            return match.group(1)
    return None


def normalize_weather_mcp_data(
    weather_mcp_data: dict | None,
    *,
    location_hint: str | None = None,
) -> dict:
    payload = weather_mcp_data.copy() if weather_mcp_data else {}
    location = payload.get("location") or location_hint or "未提供"
    temperature_c = payload.get("temperature_c")
    humidity_pct = payload.get("humidity_pct")
    condition = payload.get("condition") or payload.get("summary") or "未接入实时天气"
    return {
        "location": location,
        "temperature_c": temperature_c,
        "humidity_pct": humidity_pct,
        "condition": condition,
        "source": payload.get("source") or ("weather_mcp" if weather_mcp_data else "weather_mcp_unavailable"),
    }


def _serialize_retrieved_chunk(chunk: dict) -> dict:
    title = chunk.get("doc_title", "未知古籍")
    raw_text = chunk.get("text", chunk.get("snippet", "")) or ""
    metadata = chunk.get("metadata", {}) or {}
    return {
        "book_title": title,
        "raw": raw_text,
        "chunk_id": chunk.get("chunk_id", ""),
        "doc_id": chunk.get("doc_id", ""),
        "metadata": metadata,
    }


class DietaryGenerationContextService:
    def build_context(
        self,
        *,
        user_query: str,
        case_profile_summary: str | None,
        retrieved_chunks: list[dict],
        weather_mcp_data: dict | None = None,
        live_context: dict | None = None,
    ) -> dict:
        location_hint = extract_location_hint(case_profile_summary, user_query)
        live_context = live_context or {}
        weather_payload = weather_mcp_data or {
            "location": (
                f"{live_context.get('province', '')}{live_context.get('city', '')}".strip()
                or live_context.get("label")
                or None
            ),
            "temperature_c": live_context.get("temperature") or None,
            "humidity_pct": live_context.get("humidity") or None,
            "condition": live_context.get("condition") or None,
            "source": live_context.get("source") or None,
        }
        return {
            "weather_mcp_data": normalize_weather_mcp_data(
                weather_payload,
                location_hint=location_hint,
            ),
            "current_solar_term": live_context.get("solar_term") or get_current_solar_term(),
            "environmental_context": live_context.get("environmental_context")
            or f"时间：未知 | 位置：{location_hint or '未提供'} | 天气：未获取",
            "user_constitution": infer_user_constitution(case_profile_summary, user_query),
            "retrieved_ancient_chunks": [
                _serialize_retrieved_chunk(chunk)
                for chunk in retrieved_chunks[:6]
            ],
        }


dietary_generation_context_service = DietaryGenerationContextService()
