"""答案生成与流式切块服务 — LLM-powered streaming."""

from __future__ import annotations

import time
from typing import AsyncGenerator

from app.core.logger import get_logger
from app.integrations.llm_client import llm_client
from app.schemas.chat import Citation
from app.schemas.rag import QueryRewriteResult, RetrievalHit

logger = get_logger(__name__)


async def stream_answer(
    messages: list[dict],
    chunks_used: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream LLM answer as SSE-compatible dicts.

    Yields:
        {"event": "chunk", "data": {"content": "..."}}
        ...
        {"event": "done", "data": {"citations": [...], "latency_ms": ..., "token_count": ...}}
    """
    full_answer_parts: list[str] = []
    token_count = 0
    start_time = time.perf_counter()

    try:
        async for chunk_text in llm_client.chat_stream(messages):
            full_answer_parts.append(chunk_text)
            token_count += max(1, len(chunk_text))  # rough estimate
            yield {"event": "chunk", "data": {"content": chunk_text}}

    except Exception as exc:
        logger.error("LLM streaming failed: %s", exc, exc_info=True)
        error_msg = (
            "抱歉，知识检索助手暂时无法生成回答，请稍后重试。"
            "如有紧急健康问题，请及时就医。"
        )
        yield {"event": "chunk", "data": {"content": error_msg}}
        full_answer_parts.append(error_msg)

    latency_ms = int((time.perf_counter() - start_time) * 1000)
    full_answer = "".join(full_answer_parts)

    # Build citations from chunks_used vs actual answer
    citations: list[dict] = []
    if chunks_used:
        from app.services.citation_service import citation_service
        citations = citation_service.build_citations(chunks_used, full_answer)

    logger.info(
        "answer_stream completed: tokens≈%d, latency=%dms, citations=%d",
        token_count, latency_ms, len(citations),
    )

    yield {
        "event": "done",
        "data": {
            "answer_text": full_answer,
            "citations": citations,
            "latency_ms": latency_ms,
            "token_count": token_count,
        },
    }


# ---------------------------------------------------------------------------
# Legacy helpers kept for backward compatibility with rag_service / tests
# ---------------------------------------------------------------------------


def compose_answer(
    query: str,
    query_bundle: QueryRewriteResult,
    hits: list[RetrievalHit],
) -> str:
    entity_text = "、".join(query_bundle.entities) if query_bundle.entities else "当前问题中的关键症状或知识点"
    hit_lines = []
    for index, hit in enumerate(hits[:3], start=1):
        snippet = hit.text[:48] + ("..." if len(hit.text) > 48 else "")
        hit_lines.append(f"{index}. {hit.doc_title}：{snippet}")

    advice_line = "建议继续结合舌脉、病程、诱因与既往史综合辨证，优先把问题收敛到证候与经典出处。"
    if query_bundle.intent == "formula_or_herb_knowledge":
        advice_line = "建议进一步核对药物或方剂的出处、适应证、配伍与禁忌，不要直接替代个体化处方。"

    answer_sections = [
        f'症状分析：围绕"{entity_text}"进行检索，当前更适合从中医辨证与古籍出处两个层面理解问题。',
        "可能相关证候/知识点：" + ("；".join(hit.reason for hit in hits[:3]) or "暂未命中高置信线索。"),
        f"建议参考方向：{advice_line}",
        "风险提示：以下内容仅用于中医知识检索与学习参考，不能替代线下面诊；如症状持续、加重或伴明显不适，请及时就医。",
        "引用来源：" + ("；".join(hit_lines) if hit_lines else "暂无引用来源。"),
    ]
    return "\n".join(answer_sections)


def split_answer_for_stream(answer: str, chunk_size: int = 28) -> list[str]:
    return [answer[index : index + chunk_size] for index in range(0, len(answer), chunk_size)]


def estimate_tokens(answer: str, citations: list[Citation]) -> int:
    return max(64, len(answer) + sum(len(item.text) for item in citations) // 2)
