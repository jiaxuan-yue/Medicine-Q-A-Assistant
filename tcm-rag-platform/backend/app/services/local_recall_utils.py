"""Pure-stdlib helpers for book/entity-aware lexical recall.

These utilities intentionally avoid project/runtime dependencies so they can be
reused by lightweight offline regression scripts.
"""

from __future__ import annotations

import re
from typing import Iterable

_HEADING_ENTITY_RE = re.compile(r"<篇名>\s*([^\s<>{}《》【】()（）:：]{1,16})")
_QUOTED_TERM_RE = re.compile(r"[\"“”‘’「」『』](.{1,16}?)[\"“”‘’「」『』]")
_GENERIC_HEADINGS = {
    "目录",
    "序",
    "邵序",
    "张序",
    "孙序",
    "凡例",
    "上经",
    "中经",
    "下经",
    "上品",
    "中品",
    "下品",
    "卷一",
    "卷二",
    "卷三",
    "卷四",
}
_STOP_TERMS = {
    "是什么",
    "什么",
    "哪些",
    "有哪些",
    "提到",
    "记载",
    "原文",
    "描述",
    "功效",
    "作用",
    "主治",
    "使用方法",
}


def normalize_spaces(text: str) -> str:
    return " ".join((text or "").split())


def extract_heading_entity(text: str) -> str:
    match = _HEADING_ENTITY_RE.search(text or "")
    if not match:
        return ""
    entity = match.group(1).strip()
    if entity.endswith("内容"):
        entity = entity[: -2].strip()
    if not entity or entity in _GENERIC_HEADINGS:
        return ""
    if len(entity) > 12:
        return ""
    return entity


def extract_quoted_terms(text: str) -> list[str]:
    items: list[str] = []
    for match in _QUOTED_TERM_RE.finditer(text or ""):
        term = match.group(1).strip()
        if term and term not in items:
            items.append(term)
    return items


def _contains_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def filter_entity_candidates(items: Iterable[str]) -> list[str]:
    entities: list[str] = []
    for raw in items:
        term = normalize_spaces(raw).strip("《》【】[]()（）:：,，。.?？!！;； ")
        if not term or term in _STOP_TERMS:
            continue
        if len(term) < 2 or len(term) > 16:
            continue
        if not _contains_chinese(term):
            continue
        if term not in entities:
            entities.append(term)
    return entities


def score_metadata_item(
    item: dict,
    *,
    query_terms: Iterable[str],
    entities: Iterable[str] = (),
    book_name: str | None = None,
) -> float:
    doc_title = str(item.get("doc_title") or "")
    chunk_text = str(item.get("chunk_text") or "")
    heading_entity = extract_heading_entity(chunk_text)
    score = 0.0

    if book_name:
        if doc_title == book_name:
            score += 8.0
        elif book_name in doc_title:
            score += 4.0
        else:
            return 0.0

    for entity in filter_entity_candidates(entities):
        if heading_entity == entity:
            score += 20.0
        elif f"<篇名>{entity}" in chunk_text:
            score += 12.0
        elif entity in chunk_text:
            score += 6.0
        elif entity in doc_title:
            score += 3.0

    for term in filter_entity_candidates(query_terms):
        if heading_entity == term:
            score += 8.0
        elif term in chunk_text:
            score += 2.0
        elif term in doc_title:
            score += 1.0

    if score <= 0:
        return 0.0

    # Prefer compact, focused chunks when lexical evidence is tied.
    score += max(0.0, 1.5 - (len(chunk_text) / 1200.0))
    return round(score, 4)


def rank_metadata_chunks(
    metadata: Iterable[dict],
    *,
    query_terms: Iterable[str],
    entities: Iterable[str] = (),
    book_name: str | None = None,
    top_k: int = 20,
) -> list[dict]:
    ranked: list[dict] = []
    seen: set[str] = set()

    for item in metadata:
        chunk_id = str(item.get("chunk_id") or "")
        if chunk_id and chunk_id in seen:
            continue
        score = score_metadata_item(
            item,
            query_terms=query_terms,
            entities=entities,
            book_name=book_name,
        )
        if score <= 0:
            continue
        candidate = dict(item)
        candidate["score"] = score
        ranked.append(candidate)
        if chunk_id:
            seen.add(chunk_id)

    ranked.sort(
        key=lambda item: (
            float(item.get("score", 0.0)),
            extract_heading_entity(str(item.get("chunk_text") or "")) != "",
            -len(str(item.get("chunk_text") or "")),
        ),
        reverse=True,
    )
    return ranked[:top_k]
