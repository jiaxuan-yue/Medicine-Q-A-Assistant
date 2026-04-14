"""多角色档案仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case_profile import CaseProfile


class CaseProfileRepository:
    async def list_by_user_id(self, db: AsyncSession, user_id: int) -> list[CaseProfile]:
        stmt = select(CaseProfile).where(CaseProfile.user_id == user_id).order_by(CaseProfile.updated_at.desc())
        return list((await db.scalars(stmt)).all())

    async def get_by_id(self, db: AsyncSession, profile_id: int) -> CaseProfile | None:
        stmt = select(CaseProfile).where(CaseProfile.id == profile_id)
        return await db.scalar(stmt)

    async def get_by_id_and_user_id(
        self,
        db: AsyncSession,
        *,
        profile_id: int,
        user_id: int,
    ) -> CaseProfile | None:
        stmt = select(CaseProfile).where(CaseProfile.id == profile_id, CaseProfile.user_id == user_id)
        return await db.scalar(stmt)

    async def create(self, db: AsyncSession, *, user_id: int, payload: dict) -> CaseProfile:
        profile = CaseProfile(user_id=user_id, **payload)
        db.add(profile)
        await db.flush()
        await db.refresh(profile)
        return profile

    async def update(self, db: AsyncSession, *, profile: CaseProfile, payload: dict) -> CaseProfile:
        for key, value in payload.items():
            setattr(profile, key, value)
        await db.flush()
        await db.refresh(profile)
        return profile


case_profile_repo = CaseProfileRepository()
