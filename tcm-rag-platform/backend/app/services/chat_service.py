"""会话服务 — full RAG pipeline with LLM streaming."""

from __future__ import annotations

import json

from app.core.exceptions import AppException
from app.core.logger import get_logger
from app.db.repositories.case_profile_repo import case_profile_repo
from app.schemas.chat import ChatSessionOut, MessageOut
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserProfile
from app.services.answer_service import (
    compose_answer,
    estimate_tokens,
    split_answer_for_stream,
    stream_answer,
)
from app.services.dietary_generation_context_service import dietary_generation_context_service
from app.services.environment_mcp_client_service import flash_call_environment_mcp
from app.services.followup_service import followup_service
from app.services.light_agent_service import light_agent_service
from app.services.prompt_service import prompt_service
from app.services.query_rewrite_service import rewrite_query, rewrite_query_async
from app.services.rag_service import generate_answer_package
from app.services.rerank_service import rerank_service
from app.services.retrieval_service import retrieval_service
from app.services.store import MessageRecord, SessionRecord, store
from app.services.case_profile_service import (
    build_case_profile_summary,
    case_profile_service,
    is_case_profile_complete,
)

logger = get_logger(__name__)


def _serialize_session(session: SessionRecord) -> ChatSessionOut:
    return ChatSessionOut(
        session_id=session.session_id,
        title=session.title,
        summary=session.summary,
        case_profile_id=session.case_profile_id,
        case_profile_name=session.case_profile_name,
        case_profile_summary=session.case_profile_summary,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _serialize_message(message: MessageRecord) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        kind=message.kind,
        citations=message.citations,
        latency_ms=message.latency_ms,
        created_at=message.created_at,
    )


def create_chat_session(current_user: UserProfile) -> ChatSessionOut:
    session = store.create_session(current_user.id)
    return _serialize_session(session)


def list_chat_sessions(
    current_user: UserProfile,
    page: int = 1,
    size: int = 50,
) -> PaginatedResponse[ChatSessionOut]:
    sessions = [session for session in store.sessions.values() if session.user_id == current_user.id]
    sessions.sort(key=lambda item: item.updated_at, reverse=True)
    total = len(sessions)
    start = max(page - 1, 0) * size
    end = start + size
    return PaginatedResponse(
        items=[_serialize_session(item) for item in sessions[start:end]],
        total=total,
        page=page,
        size=size,
    )


def get_session_messages(current_user: UserProfile, session_id: str) -> list[MessageOut]:
    session = store.sessions.get(session_id)
    if session is None or session.user_id != current_user.id:
        raise AppException(code=30004, message="会话不存在", http_status=404)
    message_ids = store.session_messages.get(session_id, [])
    return [_serialize_message(store.messages[item]) for item in message_ids]


def _format_sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_conversation_history(session_id: str, limit: int = 6) -> list[dict]:
    """Build recent conversation history from in-memory store."""
    message_ids = store.session_messages.get(session_id, [])
    history: list[dict] = []
    for mid in message_ids[-(limit):]:
        msg = store.messages.get(mid)
        if msg:
            history.append({"role": msg.role, "content": msg.content})
    return history


async def stream_chat(
    current_user: UserProfile,
    session_id: str,
    query: str,
    case_profile_summary: str | None = None,
    weather_mcp_data: dict | None = None,
    user_location: dict | None = None,
):
    """Full RAG pipeline with real LLM streaming.

    Pipeline:
    1. Query rewrite (LLM-based if enabled, rule-based fallback)
    2. Retrieval (retrieve_documents from retrieval_service)
    3. Rerank (DashScope reranker + composite scoring)
    4. Build prompt (system + context + conversation history)
    5. Stream LLM answer (DashScope streaming)
    6. Extract citations (match chunks against answer)
    7. Save messages to store
    """
    session = store.sessions.get(session_id)
    if session is None or session.user_id != current_user.id:
        yield _format_sse("error", {"code": "SESSION_NOT_FOUND", "message": "会话不存在"})
        return

    try:
        effective_query = query
        clarification_context: str | None = None

        # ── Step 0: Follow-up Gate ─────────────────────────
        preview_plan = light_agent_service.plan(query, history_summary=session.summary)
        preview_bundle = rewrite_query(query, history_summary=session.summary)
        followup_decision = followup_service.process_turn(
            session,
            query=query,
            intent=preview_bundle.intent,
            answer_style=preview_plan.answer_style,
            case_profile_summary=case_profile_summary,
        )
        logger.info(
            "followup_gate: need_follow_up=%s, preview_style=%s, preview_intent=%s, effective_query=%s, clarification=%s",
            followup_decision.need_follow_up,
            preview_plan.answer_style,
            preview_bundle.intent,
            followup_decision.effective_query,
            followup_decision.clarification_context or "-",
        )

        if followup_decision.need_follow_up and followup_decision.follow_up_message:
            store.add_message(
                session_id=session_id,
                role="user",
                content=query,
                kind="user",
                rewritten_query=query,
            )
            yield _format_sse("start", {"session_id": session_id, "message_id": ""})
            full_followup = followup_decision.follow_up_message
            for piece in split_answer_for_stream(full_followup, chunk_size=32):
                yield _format_sse("chunk", {"content": piece})
            assistant_message = store.add_message(
                session_id=session_id,
                role="assistant",
                content=full_followup,
                kind="followup",
                citations=[],
                latency_ms=0,
            )
            yield _format_sse("citation", {"citations": []})
            yield _format_sse(
                "done",
                {
                    "message_id": assistant_message.id,
                    "message_kind": "followup",
                    "total_tokens": max(1, len(full_followup)),
                    "latency_ms": 0,
                },
            )
            return

        effective_query = followup_decision.effective_query or query
        clarification_context = followup_decision.clarification_context

        # ── Step 1: Light Agent Plan ───────────────────────
        tool_plan = light_agent_service.plan(effective_query, history_summary=session.summary)
        logger.info(
            "tool_plan: strategy=%s, llm_rewrite=%s, rerank=%s, retrieval_top_k=%d, answer_top_k=%d, style=%s, reason=%s",
            tool_plan.strategy,
            tool_plan.use_llm_rewrite,
            tool_plan.use_rerank,
            tool_plan.retrieval_top_k,
            tool_plan.answer_top_k,
            tool_plan.answer_style,
            tool_plan.reason,
        )

        # ── Tool 2: Query Rewrite ─────────────────────────
        query_bundle = await rewrite_query_async(
            effective_query,
            history_summary=session.summary,
            use_llm=tool_plan.use_llm_rewrite,
        )
        logger.info(
            "query_rewrite: raw=%s, normalized=%s, entities=%s, intent=%s",
            effective_query,
            query_bundle.normalized_query,
            query_bundle.entities,
            query_bundle.intent,
        )

        # ── Tool 3: Hybrid Retrieval ───────────────────────
        retrieval_bundle = await retrieval_service.retrieve(
            query=effective_query,
            rewrite_result=query_bundle,
            top_k=tool_plan.retrieval_top_k,
        )
        hits = retrieval_bundle["fused_docs"]

        # Convert hits to dicts for the following tools
        hit_dicts = [
            {
                "chunk_id": h.get("chunk_id", ""),
                "doc_id": h.get("doc_id", ""),
                "doc_title": h.get("doc_title", ""),
                "source": h.get("source_type", h.get("source", "")),
                "retrieval_source": h.get("source_type", h.get("source", "")),
                "score": h.get("score", 0.0),
                "reason": h.get("source_type", h.get("reason", "")),
                "text": h.get("chunk_text", h.get("text", "")),
                "metadata": h.get("metadata", {}),
            }
            for h in hits
        ]

        # ── Tool 4: Rerank (conditional) ───────────────────
        if light_agent_service.should_rerank(hit_dicts, tool_plan):
            reranked = await rerank_service.rerank(
                query=query_bundle.normalized_query,
                candidates=hit_dicts,
                top_k=tool_plan.rerank_top_k,
            )
            logger.info("rerank: %d → %d candidates", len(hit_dicts), len(reranked))
        else:
            reranked = light_agent_service.trim_for_answer(hit_dicts, tool_plan)
            logger.info("rerank skipped: using top %d fused candidates directly", len(reranked))

        # ── Tool 5: Flash-call environment MCP ─────────────
        live_context = await flash_call_environment_mcp(preferred_location=user_location)
        logger.info(
            "live_context: %s",
            live_context.get("environmental_context", "时间：未知 | 位置：未提供 | 天气：未获取"),
        )

        # ── Tool 6: Aggregate generation context ───────────
        effective_case_profile_summary = case_profile_summary
        if clarification_context:
            effective_case_profile_summary = (
                f"{case_profile_summary}；本轮补充：{clarification_context}"
                if case_profile_summary
                else f"本轮补充：{clarification_context}"
            )
        generation_context = dietary_generation_context_service.build_context(
            user_query=effective_query,
            case_profile_summary=effective_case_profile_summary,
            retrieved_chunks=reranked,
            weather_mcp_data=weather_mcp_data,
            live_context=live_context,
        )
        if clarification_context:
            generation_context["clarification_context"] = clarification_context
        logger.info(
            "generation_context: env=%s, location=%s, solar_term=%s, constitution=%s, ancient_chunks=%d, weather_source=%s",
            generation_context.get("environmental_context", "时间：未知 | 位置：未提供 | 天气：未获取"),
            generation_context["weather_mcp_data"].get("location", "未提供"),
            generation_context.get("current_solar_term", "未提供"),
            generation_context.get("user_constitution", "未提供"),
            len(generation_context.get("retrieved_ancient_chunks", [])),
            generation_context["weather_mcp_data"].get("source", "unknown"),
        )

        # ── Tool 7: Build Prompt ───────────────────────────
        conversation_history = _build_conversation_history(session_id)
        messages = prompt_service.build_prompt(
            user_query=effective_query,
            context_chunks=reranked,
            conversation_history=conversation_history,
            case_profile_summary=effective_case_profile_summary,
            answer_style=tool_plan.answer_style,
            generation_context=generation_context,
        )

        # ── Save user message ─────────────────────────────
        store.add_message(
            session_id=session_id,
            role="user",
            content=query,
            kind="user",
            rewritten_query=query_bundle.rewrite_queries[0] if query_bundle.rewrite_queries else query,
        )

        # ── Step 6: Stream LLM Answer ─────────────────────
        # Emit start event
        placeholder_id = None
        yield _format_sse("start", {"session_id": session_id, "message_id": ""})

        full_answer = ""
        citations: list[dict] = []
        latency_ms = 0
        token_count = 0

        async for event in stream_answer(
            messages,
            chunks_used=reranked,
            temperature=0.7,
            top_p=0.9,
        ):
            if event["event"] == "chunk":
                yield _format_sse("chunk", {"content": event["data"]["content"]})
            elif event["event"] == "done":
                done_data = event["data"]
                full_answer = done_data.get("answer_text", "")
                citations = done_data.get("citations", [])
                latency_ms = done_data.get("latency_ms", 0)
                token_count = done_data.get("token_count", 0)

        # ── Step 6 & 7: Save assistant message with citations ──
        citation_dicts = [
            {"chunk_id": c.get("chunk_id", ""), "doc_title": c.get("doc_title", ""), "text": c.get("text", "")}
            for c in citations
        ]
        assistant_message = store.add_message(
            session_id=session_id,
            role="assistant",
            content=full_answer,
            kind="answer",
            citations=citation_dicts,
            latency_ms=latency_ms,
        )

        # Update session summary
        session.summary = f"最近问题聚焦：{query_bundle.normalized_query[:36]}"

        # Emit citation and done events
        yield _format_sse("citation", {"citations": citation_dicts})
        yield _format_sse(
            "done",
            {
                "message_id": assistant_message.id,
                "message_kind": "answer",
                "total_tokens": token_count,
                "latency_ms": latency_ms,
            },
        )

    except Exception:
        logger.exception("stream_chat pipeline error")
        yield _format_sse("error", {"code": "STREAM_ERROR", "message": "流式回答生成失败"})


# ── DB-backed ChatService (used by API layer) ────────────────

class ChatService:
    """Async chat service wrapping in-memory store for API layer."""

    async def create_session(
        self,
        db,
        *,
        user_id: int,
        title: str | None = None,
        case_profile_id: int,
    ) -> dict:
        profile = await case_profile_service.get_profile_or_raise(db, case_profile_repo, user_id, case_profile_id)
        if not is_case_profile_complete(profile):
            raise AppException(code=20006, message="所选角色档案未完善，无法开始问答", http_status=400)

        session = store.create_session(
            user_id,
            title=title or "新对话",
            case_profile_id=profile.id,
            case_profile_name=profile.profile_name,
            case_profile_summary=build_case_profile_summary(profile),
        )
        return _serialize_session(session).model_dump()

    async def list_sessions(self, db, *, user_id: int, page: int = 1, size: int = 50) -> tuple[list[dict], int]:
        sessions = [s for s in store.sessions.values() if s.user_id == user_id]
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        total = len(sessions)
        start = max(page - 1, 0) * size
        items = [_serialize_session(s).model_dump() for s in sessions[start:start + size]]
        return items, total

    async def list_messages(self, db, *, user_id: int, session_id: str) -> list[dict]:
        session = store.sessions.get(session_id)
        if session is None or session.user_id != user_id:
            raise AppException(code=30004, message="会话不存在", http_status=404)
        message_ids = store.session_messages.get(session_id, [])
        return [_serialize_message(store.messages[mid]).model_dump() for mid in message_ids if mid in store.messages]

    async def build_answer_payload(
        self,
        db,
        *,
        user_id: int,
        session_id: str,
        query: str,
        user_location: dict | None = None,
    ) -> dict:
        """Prepare answer context for streaming."""
        session = store.sessions.get(session_id)
        if session is None or session.user_id != user_id:
            raise AppException(code=30004, message="会话不存在", http_status=404)
        if not session.case_profile_id:
            raise AppException(code=20006, message="当前会话未绑定角色档案，请重新创建对话", http_status=400)

        case_profile = await case_profile_service.get_profile_or_raise(
            db,
            case_profile_repo,
            user_id,
            session.case_profile_id,
        )
        if not is_case_profile_complete(case_profile):
            raise AppException(code=20006, message="当前角色档案未完善，请补充后再开始问答", http_status=400)

        return {
            "user_id": user_id,
            "session_id": session_id,
            "query": query,
            "case_profile_summary": build_case_profile_summary(case_profile),
            "weather_mcp_data": None,
            "user_location": user_location,
        }

    async def stream_answer_events(self, answer_payload: dict):
        """Delegate to the existing stream_chat generator."""
        from app.schemas.user import UserProfile
        user_id = answer_payload["user_id"]
        session_id = answer_payload["session_id"]
        query = answer_payload["query"]
        case_profile_summary = answer_payload.get("case_profile_summary")
        weather_mcp_data = answer_payload.get("weather_mcp_data")
        user_location = answer_payload.get("user_location")
        # Build a minimal UserProfile for the legacy stream_chat function
        dummy_user = UserProfile(
            id=user_id, username="", email="", role="user", status="active", created_at=""
        )
        async for chunk in stream_chat(
            dummy_user,
            session_id,
            query,
            case_profile_summary=case_profile_summary,
            weather_mcp_data=weather_mcp_data,
            user_location=user_location,
        ):
            yield chunk


chat_service = ChatService()
