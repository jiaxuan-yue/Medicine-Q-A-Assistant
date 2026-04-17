"""会话服务：基于 MySQL 的聊天会话与流式问答主链路。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.logger import get_logger
from app.db.repositories.case_profile_repo import case_profile_repo
from app.db.repositories.session_repo import session_repo
from app.models.message import Message, MessageRole
from app.models.session import ChatSession
from app.schemas.chat import ChatSessionOut, MessageOut
from app.services.answer_service import split_answer_for_stream, stream_answer
from app.services.case_profile_service import (
    build_case_profile_summary,
    case_profile_service,
    is_case_profile_complete,
)
from app.services.dietary_generation_context_service import dietary_generation_context_service
from app.services.environment_mcp_client_service import flash_call_environment_mcp
from app.services.followup_service import (
    build_consultation_context_summary,
    followup_service,
    merge_consultation_context,
)
from app.services.followup_question_service import followup_question_service
from app.services.light_agent_service import light_agent_service
from app.services.prompt_service import prompt_service
from app.services.query_rewrite_service import rewrite_query, rewrite_query_async
from app.services.rerank_service import rerank_service
from app.services.retrieval_service import retrieval_service

logger = get_logger(__name__)


def _isoformat(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.isoformat()


def _role_value(role: Any) -> str:
    return getattr(role, "value", role)


def _serialize_session(session: ChatSession) -> ChatSessionOut:
    return ChatSessionOut(
        session_id=session.session_id,
        title=session.title or "新对话",
        summary=session.summary,
        case_profile_id=session.case_profile_id,
        case_profile_name=session.case_profile_name,
        case_profile_summary=session.case_profile_summary,
        created_at=_isoformat(session.created_at),
        updated_at=_isoformat(session.updated_at),
    )


def _serialize_message(message: Message) -> MessageOut:
    return MessageOut(
        id=message.message_id,
        role=_role_value(message.role),
        content=message.content,
        kind=message.kind,
        citations=message.citations or [],
        latency_ms=message.latency_ms,
        created_at=_isoformat(message.created_at),
    )


def _format_sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _merge_case_profile_summary(
    case_profile_summary: str | None,
    clarification_context: str | None,
) -> str | None:
    if not clarification_context:
        return case_profile_summary
    if case_profile_summary:
        return f"{case_profile_summary}；本轮补充：{clarification_context}"
    return f"本轮补充：{clarification_context}"


def _compose_case_profile_context(
    base_case_profile_summary: str | None,
    consultation_context: dict[str, Any] | None = None,
    clarification_context: str | None = None,
) -> str | None:
    parts: list[str] = []
    base_summary = (base_case_profile_summary or "").strip()
    session_summary = build_consultation_context_summary(consultation_context)
    if base_summary:
        parts.append(base_summary)
    if session_summary:
        parts.append(f"会话已知：{session_summary}")
    if clarification_context:
        parts.append(f"本轮补充：{clarification_context}")
    return "；".join(part for part in parts if part) or None


def _render_followup_card(question: str, *, current_round: int, max_rounds: int) -> str:
    return "\n".join(
        [
            f"第 {current_round} 问 / 共 {max_rounds} 问",
            question.strip(),
            "直接回复这一项就可以，我收到后继续。",
        ]
    )


async def _build_conversation_history(
    db: AsyncSession,
    *,
    session_id: str,
    user_id: int,
    limit: int = 6,
) -> list[dict[str, str]]:
    messages = await session_repo.list_recent_messages(
        db,
        session_id=session_id,
        user_id=user_id,
        limit=limit,
    )
    return [
        {
            "role": _role_value(message.role),
            "content": message.content,
        }
        for message in messages
    ]


async def stream_chat(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: str,
    query: str,
    case_profile_summary: str | None = None,
    weather_mcp_data: dict | None = None,
    user_location: dict | None = None,
):
    """完整聊天主链路：会话、消息、追问状态均持久化到 MySQL。"""
    session = await session_repo.get_owned_session(db, session_id=session_id, user_id=user_id)
    if session is None:
        yield _format_sse("error", {"code": "SESSION_NOT_FOUND", "message": "会话不存在"})
        return

    stored_case_profile_summary = case_profile_summary or session.case_profile_summary
    stored_consultation_context = session.consultation_context or {}

    try:
        effective_query = query
        clarification_context: str | None = None

        preview_plan = light_agent_service.plan(query, history_summary=session.summary)
        if preview_plan.answer_style != "chat":
            preview_bundle = rewrite_query(query, history_summary=session.summary)
            followup_decision = followup_service.process_turn(
                session,
                query=query,
                intent=preview_bundle.intent,
                answer_style=preview_plan.answer_style,
                case_profile_summary=stored_case_profile_summary,
                known_context=stored_consultation_context,
            )
            updated_consultation_context = merge_consultation_context(
                stored_consultation_context,
                followup_decision.collected_slots,
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
                await session_repo.add_message(
                    db,
                    session_id=session_id,
                    role=MessageRole.USER,
                    content=query,
                    kind="user",
                    rewritten_query=query,
                )
                # Release SQLite write lock before keeping the SSE response open.
                await db.commit()
                yield _format_sse("start", {"session_id": session_id, "message_id": ""})
                fallback_lines = (followup_decision.follow_up_message or "").splitlines()
                fallback_question = fallback_lines[1].strip() if len(fallback_lines) >= 2 else "请继续补充这一项。"
                followup_question = await followup_question_service.generate_question(
                    domain=followup_decision.domain or "symptom",
                    target=followup_decision.question_target or (session.followup_state or {}).get("last_asked_target") or "primary_symptom",
                    collected_slots=followup_decision.collected_slots,
                    latest_query=query,
                    asked_targets=list((session.followup_state or {}).get("asked_targets", [])),
                )
                full_followup = _render_followup_card(
                    followup_question or fallback_question,
                    current_round=followup_decision.round_count or int((session.followup_state or {}).get("round_count", 1)),
                    max_rounds=3,
                )
                for piece in split_answer_for_stream(full_followup, chunk_size=32):
                    yield _format_sse("chunk", {"content": piece})
                assistant_message = await session_repo.add_message(
                    db,
                    session_id=session_id,
                    role=MessageRole.ASSISTANT,
                    content=full_followup,
                    kind="followup",
                    citations=[],
                    latency_ms=0,
                )
                await session_repo.update_session(
                    db,
                    session=session,
                    case_profile_summary=stored_case_profile_summary,
                    consultation_context=updated_consultation_context,
                    followup_state=session.followup_state or {},
                )
                await db.commit()
                yield _format_sse("citation", {"citations": []})
                yield _format_sse(
                    "done",
                    {
                        "message_id": assistant_message.message_id,
                        "message_kind": "followup",
                        "total_tokens": max(1, len(full_followup)),
                        "latency_ms": 0,
                    },
                )
                return

            effective_query = followup_decision.effective_query or query
            clarification_context = followup_decision.clarification_context
            stored_consultation_context = updated_consultation_context

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

        if tool_plan.answer_style in {"chat", "consult"}:
            effective_case_profile_summary = _compose_case_profile_context(
                stored_case_profile_summary,
                stored_consultation_context,
                clarification_context,
            )
            consult_generation_context: dict[str, str] = {}
            if tool_plan.answer_style == "consult":
                live_context = await flash_call_environment_mcp(preferred_location=user_location)
                consult_generation_context = {
                    "environmental_context": live_context.get(
                        "environmental_context",
                        "时间：未知 | 位置：未提供 | 天气：未获取",
                    ),
                    "clarification_context": clarification_context or "",
                }

            conversation_history = await _build_conversation_history(
                db,
                session_id=session_id,
                user_id=user_id,
            )
            messages = prompt_service.build_prompt(
                user_query=effective_query,
                context_chunks=[],
                conversation_history=conversation_history,
                case_profile_summary=effective_case_profile_summary,
                answer_style=tool_plan.answer_style,
                generation_context=consult_generation_context,
            )

            await session_repo.add_message(
                db,
                session_id=session_id,
                role=MessageRole.USER,
                content=query,
                kind="user",
                rewritten_query=query,
            )
            # Persist the user message before the potentially long LLM stream starts.
            await db.commit()

            yield _format_sse("start", {"session_id": session_id, "message_id": ""})

            full_answer = ""
            latency_ms = 0
            token_count = 0
            async for event in stream_answer(
                messages,
                chunks_used=[],
                temperature=0.6,
                top_p=0.9,
            ):
                if event["event"] == "chunk":
                    yield _format_sse("chunk", {"content": event["data"]["content"]})
                elif event["event"] == "done":
                    done_data = event["data"]
                    full_answer = done_data.get("answer_text", "")
                    latency_ms = done_data.get("latency_ms", 0)
                    token_count = done_data.get("token_count", 0)

            assistant_message = await session_repo.add_message(
                db,
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=full_answer,
                kind="answer",
                citations=[],
                latency_ms=latency_ms,
            )
            await session_repo.update_session(
                db,
                session=session,
                summary=(
                    "最近是简短对话"
                    if tool_plan.answer_style == "chat"
                    else f"最近问题聚焦：{effective_query[:36]}"
                ),
                case_profile_summary=stored_case_profile_summary,
                consultation_context=stored_consultation_context,
                followup_state={},
            )
            await db.commit()
            yield _format_sse("citation", {"citations": []})
            yield _format_sse(
                "done",
                {
                    "message_id": assistant_message.message_id,
                    "message_kind": "answer",
                    "total_tokens": token_count,
                    "latency_ms": latency_ms,
                },
            )
            return

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

        retrieval_bundle = await retrieval_service.retrieve(
            query=effective_query,
            rewrite_result=query_bundle,
            top_k=tool_plan.retrieval_top_k,
        )
        logger.info(
            "retrieval_counts: sparse=%d dense=%d fused=%d",
            len(retrieval_bundle.get("sparse_docs", [])),
            len(retrieval_bundle.get("dense_docs", [])),
            len(retrieval_bundle.get("fused_docs", [])),
        )
        hits = retrieval_bundle["fused_docs"]
        hit_dicts = [
            {
                "chunk_id": hit.get("chunk_id", ""),
                "doc_id": hit.get("doc_id", ""),
                "doc_title": hit.get("doc_title", ""),
                "source": hit.get("source_type", hit.get("source", "")),
                "retrieval_source": hit.get("source_type", hit.get("source", "")),
                "score": hit.get("score", 0.0),
                "reason": hit.get("source_type", hit.get("reason", "")),
                "text": hit.get("chunk_text", hit.get("text", "")),
                "metadata": hit.get("metadata", {}),
            }
            for hit in hits
        ]

        if light_agent_service.should_rerank(hit_dicts, tool_plan):
            reranked = await rerank_service.rerank(
                query=query_bundle.normalized_query,
                candidates=hit_dicts,
                top_k=tool_plan.rerank_top_k,
            )
            logger.info("rerank: %d -> %d candidates", len(hit_dicts), len(reranked))
        else:
            reranked = light_agent_service.trim_for_answer(hit_dicts, tool_plan)
            logger.info("rerank skipped: using top %d fused candidates directly", len(reranked))

        live_context = await flash_call_environment_mcp(preferred_location=user_location)
        logger.info(
            "live_context: %s",
            live_context.get("environmental_context", "时间：未知 | 位置：未提供 | 天气：未获取"),
        )

        effective_case_profile_summary = _compose_case_profile_context(
            stored_case_profile_summary,
            stored_consultation_context,
            clarification_context,
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

        conversation_history = await _build_conversation_history(
            db,
            session_id=session_id,
            user_id=user_id,
        )
        messages = prompt_service.build_prompt(
            user_query=effective_query,
            context_chunks=reranked,
            conversation_history=conversation_history,
            case_profile_summary=effective_case_profile_summary,
            answer_style=tool_plan.answer_style,
            generation_context=generation_context,
        )

        await session_repo.add_message(
            db,
            session_id=session_id,
            role=MessageRole.USER,
            content=query,
            kind="user",
            rewritten_query=(
                query_bundle.rewrite_queries[0]
                if query_bundle.rewrite_queries
                else query
            ),
        )
        # Persist the user turn before any long-running generation work to avoid holding
        # a SQLite write transaction for the full SSE lifetime.
        await db.commit()

        yield _format_sse("start", {"session_id": session_id, "message_id": ""})

        full_answer = ""
        citations: list[dict[str, Any]] = []
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

        citation_dicts = [
            {
                "chunk_id": citation.get("chunk_id", ""),
                "doc_title": citation.get("doc_title", ""),
                "text": citation.get("text", ""),
            }
            for citation in citations
        ]
        assistant_message = await session_repo.add_message(
            db,
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=full_answer,
            kind="answer",
            citations=citation_dicts,
            latency_ms=latency_ms,
        )
        await session_repo.update_session(
            db,
            session=session,
            summary=f"最近问题聚焦：{query_bundle.normalized_query[:36]}",
            case_profile_summary=stored_case_profile_summary,
            consultation_context=stored_consultation_context,
            followup_state={},
        )
        await db.commit()

        yield _format_sse("citation", {"citations": citation_dicts})
        yield _format_sse(
            "done",
            {
                "message_id": assistant_message.message_id,
                "message_kind": "answer",
                "total_tokens": token_count,
                "latency_ms": latency_ms,
            },
        )
    except Exception:
        await db.rollback()
        logger.exception("stream_chat pipeline error")
        yield _format_sse("error", {"code": "STREAM_ERROR", "message": "流式回答生成失败"})


class ChatService:
    """基于 MySQL 的聊天服务。"""

    async def create_session(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        title: str | None = None,
        case_profile_id: int,
    ) -> dict[str, Any]:
        profile = await case_profile_service.get_profile_or_raise(
            db,
            case_profile_repo,
            user_id,
            case_profile_id,
        )
        if not is_case_profile_complete(profile):
            raise AppException(code=20006, message="所选角色档案未完善，无法开始问答", http_status=400)

        session = await session_repo.create_session(
            db,
            user_id=user_id,
            title=title or "新对话",
            case_profile_id=profile.id,
            case_profile_name=profile.profile_name,
            case_profile_summary=build_case_profile_summary(profile),
            consultation_context={},
        )
        return _serialize_session(session).model_dump()

    async def list_sessions(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        sessions, total = await session_repo.list_sessions(
            db,
            user_id=user_id,
            page=page,
            size=size,
        )
        items = [_serialize_session(session).model_dump() for session in sessions]
        return items, total

    async def list_messages(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        session_id: str,
    ) -> list[dict[str, Any]]:
        session = await session_repo.get_owned_session(db, session_id=session_id, user_id=user_id)
        if session is None:
            raise AppException(code=30004, message="会话不存在", http_status=404)

        messages = await session_repo.list_messages(
            db,
            session_id=session_id,
            user_id=user_id,
        )
        return [_serialize_message(message).model_dump() for message in messages]

    async def build_answer_payload(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        session_id: str,
        query: str,
        user_location: dict | None = None,
    ) -> dict[str, Any]:
        session = await session_repo.get_owned_session(db, session_id=session_id, user_id=user_id)
        if session is None:
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

        current_profile_summary = build_case_profile_summary(case_profile)
        await session_repo.update_session(
            db,
            session=session,
            case_profile_id=case_profile.id,
            case_profile_name=case_profile.profile_name,
            case_profile_summary=current_profile_summary,
        )
        # The /stream endpoint returns a StreamingResponse, so committing here prevents
        # the request-scoped transaction from holding a write lock for the whole stream.
        await db.commit()

        return {
            "user_id": user_id,
            "session_id": session_id,
            "query": query,
            "case_profile_summary": current_profile_summary,
            "weather_mcp_data": None,
            "user_location": user_location,
        }

    async def stream_answer_events(self, db: AsyncSession, answer_payload: dict[str, Any]):
        async for chunk in stream_chat(
            db,
            user_id=answer_payload["user_id"],
            session_id=answer_payload["session_id"],
            query=answer_payload["query"],
            case_profile_summary=answer_payload.get("case_profile_summary"),
            weather_mcp_data=answer_payload.get("weather_mcp_data"),
            user_location=answer_payload.get("user_location"),
        ):
            yield chunk


chat_service = ChatService()
