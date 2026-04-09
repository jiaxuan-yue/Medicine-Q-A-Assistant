"""知识图谱构建服务 — 从文本 chunk 提取实体和关系，写入 Neo4j。"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import get_logger
from app.integrations.llm_client import llm_client
from app.integrations.neo4j_client import neo4j_client, ENTITY_LABELS

logger = get_logger(__name__)

# ── regex patterns for TCM entity extraction (fallback) ────

# Common TCM terms regex — covers herbs, symptoms, syndromes, formulas
_HERB_PATTERN = re.compile(
    r"(?:当归|黄芪|人参|甘草|白术|茯苓|川芎|白芍|熟地|生地|麦冬|五味子|"
    r"柴胡|黄芩|半夏|大枣|生姜|桂枝|芍药|附子|干姜|细辛|吴茱萸|"
    r"黄连|黄柏|栀子|龙胆草|夏枯草|菊花|桑叶|薄荷|连翘|金银花|"
    r"知母|石膏|天花粉|竹叶|芦根|丹皮|赤芍|桃仁|红花|牛膝|"
    r"枳壳|厚朴|陈皮|香附|木香|砂仁|苍术|藿香|佩兰|薏苡仁)"
)
_SYMPTOM_PATTERN = re.compile(
    r"(?:失眠|头痛|头晕|咳嗽|发热|恶寒|恶风|汗出|盗汗|自汗|"
    r"口苦|口渴|口干|咽痛|咽干|胸闷|心悸|气短|乏力|纳差|"
    r"腹胀|腹痛|便溏|便秘|尿频|尿急|腰痛|膝软|耳鸣|目眩|"
    r"烦躁|易怒|多梦|健忘|食少|呕吐|泄泻|水肿|黄疸|出血)"
)
_SYNDROME_PATTERN = re.compile(
    r"(?:肝火扰心|肝郁化火|肝胆郁热|心肾不交|脾气虚弱|脾虚湿困|"
    r"肾阳虚|肾阴虚|气血两虚|气虚|血虚|阴虚|阳虚|痰湿|湿热|"
    r"血瘀|气滞|风热犯肺|风寒束表|肝阳上亢|心脾两虚|脾虚|"
    r"营卫不和|少阳郁热|阴阳失和|燥邪伤肺)"
)
_FORMULA_PATTERN = re.compile(
    r"(?:桂枝汤|麻黄汤|小柴胡汤|大柴胡汤|四君子汤|六君子汤|"
    r"补中益气汤|归脾汤|逍遥散|龙胆泻肝汤|天王补心丹|"
    r"酸枣仁汤|温胆汤|半夏泻心汤|理中汤|四逆汤|"
    r"银翘散|桑菊饮|麻杏石甘汤|白虎汤|六味地黄丸)"
)

# Maps regex → entity type
_REGEX_MAP: list[tuple[re.Pattern, str]] = [
    (_HERB_PATTERN, "Herb"),
    (_SYMPTOM_PATTERN, "Symptom"),
    (_SYNDROME_PATTERN, "Syndrome"),
    (_FORMULA_PATTERN, "Formula"),
]

# Relation inference rules: (from_type, to_type) → rel_type
_RELATION_RULES: dict[tuple[str, str], str] = {
    ("Symptom", "Syndrome"): "ASSOCIATED_WITH",
    ("Syndrome", "Formula"): "RECOMMENDS",
    ("Formula", "Herb"): "CONTAINS",
    ("Herb", "Efficacy"): "HAS_EFFICACY",
    ("Herb", "Contraindication"): "HAS_CONTRAINDICATION",
    ("Symptom", "Formula"): "SUPPORTS",
    ("Syndrome", "Herb"): "RECOMMENDS",
    ("Symptom", "Herb"): "SUPPORTS",
}

# ── LLM-based extraction prompt ────────────────────────────

_NER_SYSTEM_PROMPT = """\
你是一个中医药实体抽取助手。从给定文本中提取以下类型的实体：
Symptom（症状）、Syndrome（证候）、Formula（方剂）、Herb（中药）、Efficacy（功效）、Contraindication（禁忌）。

输出 JSON 数组，每个元素格式为 {"name": "实体名", "type": "类型"}。
只输出 JSON，不要其他文字。如果没有实体，输出空数组 []。"""


async def extract_entities(text: str) -> list[dict]:
    """Extract TCM entities from text. Uses LLM if available, regex as fallback."""
    # Try LLM extraction first
    try:
        if llm_client and hasattr(llm_client, "generate"):
            messages = [
                {"role": "system", "content": _NER_SYSTEM_PROMPT},
                {"role": "user", "content": text[:2000]},
            ]
            raw = await llm_client.generate(messages, temperature=0.1, max_tokens=1000)
            entities = _parse_entity_json(raw)
            if entities:
                logger.info("LLM 提取实体 %d 个", len(entities))
                return entities
    except Exception as exc:
        logger.warning("LLM 实体抽取失败，回退正则: %s", exc)

    # Fallback: regex-based extraction
    return _extract_entities_regex(text)


def _extract_entities_regex(text: str) -> list[dict]:
    """Regex-based entity extraction."""
    entities: list[dict] = []
    seen: set[str] = set()
    for pattern, entity_type in _REGEX_MAP:
        for match in pattern.finditer(text):
            name = match.group(0)
            if name not in seen:
                seen.add(name)
                entities.append({"name": name, "type": entity_type})
    return entities


def _parse_entity_json(raw: str) -> list[dict]:
    """Parse LLM output as JSON entity list."""
    import json
    # Try to extract JSON array from the response
    raw = raw.strip()
    # Find JSON array boundaries
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(raw[start : end + 1])
        if not isinstance(data, list):
            return []
        valid: list[dict] = []
        for item in data:
            if isinstance(item, dict) and "name" in item and "type" in item:
                valid.append({"name": item["name"], "type": item["type"]})
        return valid
    except json.JSONDecodeError:
        return []


async def extract_relations(
    entities: list[dict], text: str
) -> list[dict]:
    """Infer relations between extracted entities based on co-occurrence and rules."""
    relations: list[dict] = []
    entity_list = [(e["name"], e["type"]) for e in entities]

    for i, (name_a, type_a) in enumerate(entity_list):
        for j, (name_b, type_b) in enumerate(entity_list):
            if i >= j:
                continue
            # Check forward direction
            rel = _RELATION_RULES.get((type_a, type_b))
            if rel:
                relations.append(
                    {"from": name_a, "to": name_b, "type": rel}
                )
            # Check reverse direction
            rel_rev = _RELATION_RULES.get((type_b, type_a))
            if rel_rev:
                relations.append(
                    {"from": name_b, "to": name_a, "type": rel_rev}
                )
    return relations


async def build_graph_from_chunks(chunks: list[dict]) -> dict[str, Any]:
    """Process chunks → extract entities → infer relations → write to Neo4j.

    Args:
        chunks: list of {"chunk_id", "chunk_text", "doc_id", "doc_title", ...}

    Returns:
        {"entities_created": int, "relations_created": int}
    """
    total_entities = 0
    total_relations = 0

    for chunk in chunks:
        text = chunk.get("chunk_text", "")
        if not text:
            continue

        entities = await extract_entities(text)
        if not entities:
            continue

        # Create entity nodes
        for ent in entities:
            await neo4j_client.create_entity(
                name=ent["name"],
                entity_type=ent["type"],
                properties={
                    "source_chunk": chunk.get("chunk_id", ""),
                    "source_doc": chunk.get("doc_id", ""),
                },
            )
            total_entities += 1

        # Infer and create relations
        relations = await extract_relations(entities, text)
        for rel in relations:
            await neo4j_client.create_relationship(
                from_name=rel["from"],
                to_name=rel["to"],
                rel_type=rel["type"],
                properties={"source_chunk": chunk.get("chunk_id", "")},
            )
            total_relations += 1

    result = {"entities_created": total_entities, "relations_created": total_relations}
    logger.info(
        "图谱构建完成: %d 个实体, %d 条关系 (from %d chunks)",
        total_entities, total_relations, len(chunks),
    )
    return result
