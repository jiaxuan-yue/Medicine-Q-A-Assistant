"""Query rewrite 服务 — LLM 意图识别 + 实体提取 一体，规则回退。"""

from __future__ import annotations

import asyncio
import json
import re

from app.core.config import settings
from app.core.logger import get_logger
from app.schemas.rag import QueryRewriteResult
from app.services.local_recall_utils import extract_quoted_terms, filter_entity_candidates
from app.services.text_normalization_service import to_simplified_medical

logger = get_logger(__name__)

# ── LLM intent + entity extraction (one call) ──────────────

_INTENT_ENTITIES_PROMPT = """\
你是一个中医药查询意图识别与实体提取助手。请对用户查询完成三项任务：

1. intent: 判断查询意图（只能选一个）
   - symptom_diagnosis: 用户描述自身症状/证候，需要中医辨证（如"我头痛""气血两虚怎么调理""最近老是失眠"）
   - formula_or_herb_knowledge: 询问具体方剂或药材的功效、用法、配伍（如"桂枝汤怎么用""当归有什么功效""红枣和枸杞相克吗"）
   - knowledge_lookup: 询问古籍中的记载、出处、原文或特定内容（如"神农本草经中石类药物有哪些""吴普本草提到水萍的功效"）
   - general_consultation: 其他中医咨询，如食疗推荐、日常调理建议等

2. entities: 提取查询中的中医实体（症状、证候、方剂、药物等），以列表返回（不包含书名）

3. book_name: 如果查询中指定了某本古籍/医书（如"神农本草经""吴普本草""黄帝内经""本草纲目"），提取书名；否则为空字符串

请以 JSON 格式输出，字段为：{"intent": "...", "entities": ["..."], "book_name": "..."}
不要附加任何解释。

用户查询：{query}
"""

_VALID_INTENTS = {"symptom_diagnosis", "formula_or_herb_knowledge", "knowledge_lookup", "general_consultation"}

# ── LLM rewrite prompt ─────────────────────────────────────

_LLM_REWRITE_PROMPT = """\
你是一个中医药查询 query 改写助手。请对用户查询进行分析，输出一行 JSON：
{{"normalized_query": "规范化后的查询（保留所有原书人名、药名，不要替换）", "rewrite_queries": ["改写后的查询列表2-4条，必须保留原查询中的所有专有名词（药名、书名、证候名等），用空格分隔关键词"], "entities": ["中医实体（不含书名）"], "intent": "symptom_diagnosis|formula_or_herb_knowledge|knowledge_lookup|general_consultation", "book_name": "查询中提到的古籍书名，如无则为空字符串"}}
不要附加任何解释，不要换行，不要使用代码块。

用户查询：{query}
"""

# ── Fallback: book name patterns ───────────────────────────

_KNOWN_BOOKS = (
    "神农本草经", "吴普本草", "黄帝内经", "素问", "灵枢", "本草纲目",
    "伤寒论", "金匮要略", "难经", "脉经", "针灸甲乙经", "诸病源候论",
    "千金要方", "千金翼方", "外台秘要", "太平惠民和剂局方", "证类本草",
    "本草经集注", "名医别录", "雷公炮炙论", "汤液经法", "中藏经",
    "肘后备急方", "五十二病方", "刘涓子鬼遗方", "新修本草",
)

# Alternation group (NOT character class) — matches whole book names only
_BOOK_PATTERNS = re.compile(
    r"《?("
    + "|".join(re.escape(b) for b in _KNOWN_BOOKS)
    + r")》?"
)

# ── Fallback: broad symptom patterns ───────────────────────

# 证候/虚损类 — 匹配各种"虚"
_DEFICIENCY_PATTERNS = re.compile(
    r"(?:气|血|阴|阳|心|肝|脾|肺|肾|胃|胆|精|津|元)?"
    r"(?:虚|亏|弱|不足|亏虚|两虚|气虚|阴虚|阳虚|血虚)"
)

# 疼痛/不适类
_DISCOMFORT_PATTERNS = re.compile(
    r"(?:头|腹|胃|胸|腰|颈|背|肩|膝|关[节]|肌[肉])?"
    r"(?:疼|痛|胀|闷|酸|麻|痒|灼|刺|坠|紧|乏|累)"
)

# 功能失调类
_DYSFUNCTION_PATTERNS = re.compile(
    r"(?:失|不|无|少|多|难|差|弱)?"
    r"(?:眠|寐|咳|喘|泻|泄|便秘|呕|吐|嗳|反酸|纳呆|畏寒|怕冷|怕热|出汗|盗汗)"
)

_SYNDROME_HINTS = (
    "上火", "湿热", "痰湿", "寒湿", "风热", "风寒", "气滞", "血瘀",
    "郁结", "心火", "肝郁", "脾虚", "肾虚", "津亏",
)

_LIFESTYLE_HINTS = (
    "凉茶", "代茶饮", "煲汤", "泡茶", "茶饮", "食疗", "药膳",
    "推荐", "喝什么", "煮什么", "怎么喝", "吃什么", "调理",
)


def _is_symptom_query(query: str) -> bool:
    """Broad symptom detection — no hardcoded entity list needed."""
    q = query.lower()
    if _DEFICIENCY_PATTERNS.search(q):
        return True
    if _DISCOMFORT_PATTERNS.search(q):
        return True
    if _DYSFUNCTION_PATTERNS.search(q):
        return True
    if any(h in q for h in _SYNDROME_HINTS):
        return True
    return False


# ── Fallback: broad knowledge markers ──────────────────────

_KNOWLEDGE_MARKERS = (
    "是什么", "出自", "有什么功效", "有什么作用",
    "有哪些功效", "有哪些作用", "的功效", "的作用",
    "有哪些描述", "有什么特点", "提到的", "中提到的",
    "中有哪些", "中提到的", "原文", "记载",
)


def _extract_book_name(query: str) -> str | None:
    """Extract book name from query using known list + regex fallback."""
    for book in _KNOWN_BOOKS:
        if book in query:
            return book
    m = _BOOK_PATTERNS.search(query)
    if m:
        return m.group(1)  # group(1) is the book name without 《》
    return None


def _is_knowledge_lookup(query: str) -> bool:
    return any(marker in query for marker in _KNOWLEDGE_MARKERS)


# ── LLM call ───────────────────────────────────────────────

def _llm_infer_intent_and_entities(query: str) -> tuple[str | None, list[str] | None, str | None]:
    """Call LLM for intent + entities + book_name in one request. Returns (None, None, None) on failure."""
    try:
        from app.integrations.llm_client import llm_client

        prompt = _INTENT_ENTITIES_PROMPT.format(query=query)
        messages = [{"role": "user", "content": prompt}]

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.ensure_future(llm_client.chat(
                    messages, model=settings.LLM_REWRITE_MODEL,
                    temperature=0.1, max_tokens=200,
                ))
                raw = loop.run_until_complete(future)
            else:
                raw = asyncio.run(llm_client.chat(
                    messages, model=settings.LLM_REWRITE_MODEL,
                    temperature=0.1, max_tokens=200,
                ))
        except RuntimeError:
            raw = asyncio.run(llm_client.chat(
                messages, model=settings.LLM_REWRITE_MODEL,
                temperature=0.1, max_tokens=200,
            ))

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        match_start = raw.find("{")
        match_end = raw.rfind("}") + 1
        if match_start == -1 or match_end == 0:
            return None, None, None

        data = json.loads(raw[match_start:match_end])
        intent = data.get("intent", "")
        entities = data.get("entities", [])
        book_name = data.get("book_name", "") or None
        if not isinstance(entities, list):
            entities = []
        if book_name:
            book_name = book_name.strip("《》「」'\" ")
            if not book_name:
                book_name = None

        if intent in _VALID_INTENTS:
            return intent, entities, book_name
        return None, None, None

    except Exception as exc:
        logger.debug("LLM intent+entity inference failed: %s", exc)
        return None, None, None


# ── Fallback: pattern-based intent ─────────────────────────

def _fallback_infer_intent(query: str) -> str:
    """Pattern-based intent detection — no hardcoded entity dictionary."""
    # 1. 含古籍/出处 → 知识查询
    if _is_knowledge_lookup(query):
        return "knowledge_lookup"

    # 2. 含症状/证候/虚/痛/泻等 → 问诊
    if _is_symptom_query(query):
        return "symptom_diagnosis"

    # 3. 含食疗/调理/推荐 → 咨询
    if any(marker in query for marker in _LIFESTYLE_HINTS):
        return "general_consultation"

    return "general_consultation"


def _fallback_extract_entities(query: str) -> list[str]:
    """Extract entities using regex + keyword patterns — no hardcoded list."""
    entities: list[str] = []

    entities.extend(extract_quoted_terms(query))

    # 方剂名：XX汤、XX散、XX丸、XX饮
    for m in re.finditer(r"([^\s，,。]{2,8}(?:汤|散|丸|饮|膏|丹|剂))", query):
        entities.append(m.group(1))

    # 证候名：XX虚、XX证、XX湿、XX火
    for m in re.finditer(r"((?:气|血|阴|阳|心|肝|脾|肺|肾|胃|寒|湿|热|风|痰|瘀)?(?:虚|证|湿|火|郁|滞))", query):
        entities.append(m.group(1))

    # 症状：XX痛、XX泻、XX咳 等
    for m in re.finditer(r"((?:头|腹|胃|胸|腰|颈|肩|膝|关[节])?(?:疼|痛|胀|咳|喘|泻|呕|吐|麻|酸|痒))", query):
        entities.append(m.group(1))

    return filter_entity_candidates(entities)


# ── Public API ─────────────────────────────────────────────

def _infer_query(query: str) -> tuple[str, list[str], str | None]:
    """Intent + entity extraction: LLM first, pattern fallback."""
    intent, entities, book_name = _llm_infer_intent_and_entities(query)
    if intent:
        return intent, entities, book_name

    logger.debug("LLM intent+entity failed, falling back to patterns for: %s", query[:80])
    intent = _fallback_infer_intent(query)
    entities = _fallback_extract_entities(query)
    book_name = _extract_book_name(query)
    return intent, entities, book_name


def _normalize_query(query: str) -> str:
    normalized = " ".join(query.strip().split())
    return to_simplified_medical(normalized)


def _rule_based_rewrite(query: str, history_summary: str | None = None) -> QueryRewriteResult:
    """Rule-based rewrite with LLM intent/entity extraction."""
    normalized = _normalize_query(query)
    intent, entities, book_name = _infer_query(query)
    quoted_terms = extract_quoted_terms(query)
    if quoted_terms:
        entities = filter_entity_candidates([*entities, *quoted_terms])

    rewrite_queries = [normalized]
    if entities:
        joined = " ".join(entities)
        if book_name:
            rewrite_queries.append(f"{book_name} {joined} 功效 记载")
            rewrite_queries.append(f"{book_name} {joined} 原文 描述")
            rewrite_queries.append(f"{book_name} {joined} 内容 主治")
            rewrite_queries.append(f"{book_name} <篇名>{entities[0]} 内容")
        else:
            rewrite_queries.append(f"{joined} 中医辨证 古籍依据")
            rewrite_queries.append(f"{joined} 经典出处 相关证候")
            rewrite_queries.append(f"{joined} 主治 功效 用法")
    elif book_name and _is_knowledge_lookup(query):
        rewrite_queries.append(f"{book_name} 原文 记载")
        rewrite_queries.append(f"{book_name} 内容 描述")
    if history_summary:
        rewrite_queries.append(f"{normalized} 结合上下文 {history_summary[:24]}")

    unique_queries: list[str] = []
    for item in rewrite_queries:
        if item and item not in unique_queries:
            unique_queries.append(item)

    return QueryRewriteResult(
        raw_query=query,
        normalized_query=normalized,
        rewrite_queries=unique_queries,
        entities=entities,
        intent=intent,
        book_name=book_name,
    )


async def _llm_based_rewrite(query: str, history_summary: str | None = None) -> QueryRewriteResult | None:
    """Try LLM-based rewrite using qwen-plus. Returns None on failure."""
    try:
        from app.integrations.llm_client import llm_client

        prompt = _LLM_REWRITE_PROMPT.format(query=query)
        if history_summary:
            prompt += f"\n对话上下文摘要：{history_summary[:60]}"

        messages = [{"role": "user", "content": prompt}]
        raw = await llm_client.chat(messages, model=settings.LLM_REWRITE_MODEL,
                                    temperature=0.3, max_tokens=500)

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)
        normalized = data.get("normalized_query", query)
        rewrite_queries = data.get("rewrite_queries", [normalized])
        entities = data.get("entities", [])
        intent = data.get("intent", "general_consultation")
        book_name = data.get("book_name", "") or None
        if book_name:
            book_name = book_name.strip("《》「」'\" ")
            if not book_name:
                book_name = None

        if normalized not in rewrite_queries:
            rewrite_queries.insert(0, normalized)

        logger.info("LLM rewrite succeeded: entities=%s, intent=%s, book_name=%s", entities, intent, book_name)

        return QueryRewriteResult(
            raw_query=query,
            normalized_query=normalized,
            rewrite_queries=rewrite_queries,
            entities=entities,
            intent=intent,
            book_name=book_name,
        )

    except Exception as exc:
        logger.warning("LLM-based rewrite failed, falling back to rules: %s", exc)
        return None


async def rewrite_query_async(
    query: str,
    history_summary: str | None = None,
    *,
    use_llm: bool = True,
) -> QueryRewriteResult:
    """Async rewrite with optional LLM stage.

    Args:
        use_llm: when False, force rule-based rewrite only.
    """
    if settings.QUERY_REWRITE_ENABLED and use_llm:
        result = await _llm_based_rewrite(query, history_summary)
        if result is not None:
            return result

    return _rule_based_rewrite(query, history_summary)


def rewrite_query(query: str, history_summary: str | None = None) -> QueryRewriteResult:
    """Synchronous rule-based rewrite (backward-compatible)."""
    return _rule_based_rewrite(query, history_summary)


# ── Singleton service (used by API layer) ────────────────────

class QueryRewriteService:
    """Async query-rewrite service for the API layer."""

    async def rewrite(self, db, query: str, history_summary: str | None = None) -> dict:
        result = await rewrite_query_async(query, history_summary=history_summary)
        return result.model_dump()


query_rewrite_service = QueryRewriteService()
