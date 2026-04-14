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
from app.services.prompt_service import prompt_service
from app.services.query_rewrite_service import rewrite_query, rewrite_query_async
from app.services.rag_service import generate_answer_package
from app.services.rerank_service import rerank_service
from app.services.retrieval_service import retrieve_documents
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
        # ── Step 1: Query Rewrite ──────────────────────────
        query_bundle = await rewrite_query_async(query, history_summary=session.summary)
        logger.info("query_rewrite: raw=%s, normalized=%s, entities=%s, intent=%s",
                     query, query_bundle.normalized_query, query_bundle.entities, query_bundle.intent)

        # ── Step 2: Retrieval ──────────────────────────────
        hits = retrieve_documents(query_bundle, top_k=10)

        # Convert hits to dicts for reranker
        hit_dicts = [
            {
                "chunk_id": h.chunk_id,
                "doc_id": h.doc_id,
                "doc_title": h.doc_title,
                "source": h.source,
                "retrieval_source": h.retrieval_source,
                "score": h.score,
                "reason": h.reason,
                "text": h.text,
            }
            for h in hits
        ]

        # ── Step 3: Rerank ─────────────────────────────────
        reranked = await rerank_service.rerank(
            query=query_bundle.normalized_query,
            candidates=hit_dicts,
            top_k=5,
        )
        logger.info("rerank: %d → %d candidates", len(hit_dicts), len(reranked))

        # ── Step 4: Build Prompt ───────────────────────────
        conversation_history = _build_conversation_history(session_id)
        messages = prompt_service.build_prompt(
            user_query=query,
            context_chunks=reranked,
            conversation_history=conversation_history,
            case_profile_summary=case_profile_summary,
        )

        # ── Save user message ─────────────────────────────
        store.add_message(
            session_id=session_id,
            role="user",
            content=query,
            rewritten_query=query_bundle.rewrite_queries[0] if query_bundle.rewrite_queries else query,
        )

        # ── Step 5: Stream LLM Answer ─────────────────────
        # Emit start event
        placeholder_id = None
        yield _format_sse("start", {"session_id": session_id, "message_id": ""})

        full_answer = ""
        citations: list[dict] = []
        latency_ms = 0
        token_count = 0

        async for event in stream_answer(messages, chunks_used=reranked):
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

    async def build_answer_payload(self, db, *, user_id: int, session_id: str, query: str) -> dict:
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
        }

    async def stream_answer_events(self, answer_payload: dict):
        """Delegate to the existing stream_chat generator."""
        from app.schemas.user import UserProfile
        user_id = answer_payload["user_id"]
        session_id = answer_payload["session_id"]
        query = answer_payload["query"]
        case_profile_summary = answer_payload.get("case_profile_summary")
        # Build a minimal UserProfile for the legacy stream_chat function
        dummy_user = UserProfile(
            id=user_id, username="", email="", role="user", status="active", created_at=""
        )
        async for chunk in stream_chat(dummy_user, session_id, query, case_profile_summary=case_profile_summary):
            yield chunk


chat_service = ChatService()
