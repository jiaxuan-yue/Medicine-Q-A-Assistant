"""Repository for user portrait memories."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_portrait_memory import PortraitMemoryStatus, UserPortraitMemory


class UserPortraitMemoryRepository:
    async def list_active_by_user_id(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        memory_types: list[str] | None = None,
    ) -> list[UserPortraitMemory]:
        stmt = (
            select(UserPortraitMemory)
            .where(
                UserPortraitMemory.user_id == user_id,
                UserPortraitMemory.status == PortraitMemoryStatus.ACTIVE,
            )
            .order_by(UserPortraitMemory.last_seen_at.desc(), UserPortraitMemory.created_at.desc())
        )
        if memory_types:
            stmt = stmt.where(UserPortraitMemory.memory_type.in_(memory_types))
        return list((await db.scalars(stmt)).all())

    async def list_active_by_facet(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        facet_key: str,
    ) -> list[UserPortraitMemory]:
        stmt = (
            select(UserPortraitMemory)
            .where(
                UserPortraitMemory.user_id == user_id,
                UserPortraitMemory.facet_key == facet_key,
                UserPortraitMemory.status == PortraitMemoryStatus.ACTIVE,
            )
            .order_by(UserPortraitMemory.last_seen_at.desc(), UserPortraitMemory.created_at.desc())
        )
        return list((await db.scalars(stmt)).all())

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        session_id: str | None,
        source_message_id: str | None,
        memory_type: str,
        facet_key: str,
        content: str,
        importance_score: float,
        confidence_score: float,
        embedding_json: list[float] | None,
        metadata_json: dict | None,
        first_seen_at: datetime,
        last_seen_at: datetime,
    ) -> UserPortraitMemory:
        memory = UserPortraitMemory(
            user_id=user_id,
            session_id=session_id,
            source_message_id=source_message_id,
            memory_type=memory_type,
            facet_key=facet_key,
            content=content,
            importance_score=importance_score,
            confidence_score=confidence_score,
            embedding_json=embedding_json,
            metadata_json=metadata_json or {},
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
        )
        db.add(memory)
        await db.flush()
        await db.refresh(memory)
        return memory

    async def reinforce(
        self,
        db: AsyncSession,
        *,
        memory: UserPortraitMemory,
        session_id: str | None,
        source_message_id: str | None,
        confidence_score: float | None = None,
        metadata_json: dict | None = None,
        seen_at: datetime,
    ) -> UserPortraitMemory:
        memory.session_id = session_id or memory.session_id
        memory.source_message_id = source_message_id or memory.source_message_id
        memory.last_seen_at = seen_at
        memory.reinforcement_count += 1
        if confidence_score is not None:
            memory.confidence_score = max(memory.confidence_score, confidence_score)
        if metadata_json:
            existing = dict(memory.metadata_json or {})
            existing.update(metadata_json)
            memory.metadata_json = existing
        await db.flush()
        await db.refresh(memory)
        return memory

    async def supersede(
        self,
        db: AsyncSession,
        *,
        memory: UserPortraitMemory,
        superseded_by: str | None,
        when: datetime,
    ) -> UserPortraitMemory:
        memory.status = PortraitMemoryStatus.SUPERSEDED
        memory.superseded_at = when
        memory.superseded_by = superseded_by
        await db.flush()
        await db.refresh(memory)
        return memory


user_portrait_memory_repo = UserPortraitMemoryRepository()
