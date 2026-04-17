"""会话与消息仓储。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageRole
from app.models.session import ChatSession

_UNSET = object()


class SessionRepository:
    async def create_session(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        title: str | None = None,
        case_profile_id: int | None = None,
        case_profile_name: str | None = None,
        case_profile_summary: str | None = None,
        consultation_context: dict[str, Any] | None = None,
    ) -> ChatSession:
        session = ChatSession(
            user_id=user_id,
            title=title or "新对话",
            case_profile_id=case_profile_id,
            case_profile_name=case_profile_name,
            case_profile_summary=case_profile_summary,
            consultation_context=consultation_context or {},
            followup_state={},
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session

    async def list_sessions(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        page: int,
        size: int,
    ) -> tuple[list[ChatSession], int]:
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        total = int(
            await db.scalar(select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)) or 0
        )
        sessions = list((await db.scalars(stmt)).all())
        return sessions, total

    async def get_owned_session(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: int,
    ) -> ChatSession | None:
        stmt = select(ChatSession).where(
            ChatSession.session_id == session_id,
            ChatSession.user_id == user_id,
        )
        return await db.scalar(stmt)

    async def list_messages(self, db: AsyncSession, *, session_id: str, user_id: int) -> list[Message]:
        stmt = (
            select(Message)
            .join(ChatSession, ChatSession.session_id == Message.session_id)
            .where(Message.session_id == session_id, ChatSession.user_id == user_id)
            .order_by(Message.created_at.asc())
        )
        return list((await db.scalars(stmt)).all())

    async def list_recent_messages(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: int,
        limit: int = 6,
    ) -> list[Message]:
        stmt = (
            select(Message)
            .join(ChatSession, ChatSession.session_id == Message.session_id)
            .where(Message.session_id == session_id, ChatSession.user_id == user_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list((await db.scalars(stmt)).all())
        messages.reverse()
        return messages

    async def add_message(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        role: MessageRole,
        content: str,
        kind: str | None = None,
        rewritten_query: str | None = None,
        citations: list[dict] | None = None,
        latency_ms: int | None = None,
    ) -> Message:
        normalized_role = role if isinstance(role, MessageRole) else MessageRole(role)
        message = Message(
            session_id=session_id,
            role=normalized_role,
            content=content,
            kind=kind or "answer",
            rewritten_query=rewritten_query,
            citations=citations,
            latency_ms=latency_ms,
        )
        db.add(message)

        session = await db.scalar(select(ChatSession).where(ChatSession.session_id == session_id))
        if session is not None:
            session.updated_at = datetime.utcnow()
            if normalized_role == MessageRole.USER and (not session.title or session.title == "新对话"):
                session.title = content.strip().replace("\n", " ")[:16] or "新对话"

        await db.flush()
        await db.refresh(message)
        return message

    async def update_session(
        self,
        db: AsyncSession,
        *,
        session: ChatSession,
        title: str | None | object = _UNSET,
        summary: str | None | object = _UNSET,
        case_profile_id: int | None | object = _UNSET,
        case_profile_name: str | None | object = _UNSET,
        case_profile_summary: str | None | object = _UNSET,
        consultation_context: dict[str, Any] | None | object = _UNSET,
        followup_state: dict[str, Any] | None | object = _UNSET,
    ) -> ChatSession:
        if title is not _UNSET:
            session.title = title
        if summary is not _UNSET:
            session.summary = summary
        if case_profile_id is not _UNSET:
            session.case_profile_id = case_profile_id
        if case_profile_name is not _UNSET:
            session.case_profile_name = case_profile_name
        if case_profile_summary is not _UNSET:
            session.case_profile_summary = case_profile_summary
        if consultation_context is not _UNSET:
            session.consultation_context = consultation_context
        if followup_state is not _UNSET:
            session.followup_state = followup_state
        session.updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(session)
        return session

    async def count_sessions(self, db: AsyncSession) -> int:
        return int(await db.scalar(select(func.count(ChatSession.id))) or 0)

    async def count_messages(self, db: AsyncSession) -> int:
        return int(await db.scalar(select(func.count(Message.id))) or 0)


session_repo = SessionRepository()
