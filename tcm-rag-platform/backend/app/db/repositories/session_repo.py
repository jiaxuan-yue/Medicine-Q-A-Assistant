"""会话与消息仓储。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageRole
from app.models.session import ChatSession


class SessionRepository:
    async def create_session(self, db: AsyncSession, *, user_id: int, title: str | None = None) -> ChatSession:
        session = ChatSession(user_id=user_id, title=title or "新对话")
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

    async def add_message(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        role: MessageRole,
        content: str,
        rewritten_query: str | None = None,
        citations: list[dict] | None = None,
        latency_ms: int | None = None,
    ) -> Message:
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            rewritten_query=rewritten_query,
            citations=citations,
            latency_ms=latency_ms,
        )
        db.add(message)
        await db.flush()
        await db.refresh(message)
        return message

    async def update_session_summary(
        self,
        db: AsyncSession,
        *,
        session: ChatSession,
        title: str | None = None,
        summary: str | None = None,
    ) -> ChatSession:
        if title:
            session.title = title
        if summary is not None:
            session.summary = summary
        await db.flush()
        await db.refresh(session)
        return session

    async def count_sessions(self, db: AsyncSession) -> int:
        return int(await db.scalar(select(func.count(ChatSession.id))) or 0)

    async def count_messages(self, db: AsyncSession) -> int:
        return int(await db.scalar(select(func.count(Message.id))) or 0)


session_repo = SessionRepository()
