"""用户仓储。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.role import Role, RoleName
from app.models.user import User
from app.models.user_case_profile import UserCaseProfile


class UserRepository:
    async def count_users(self, db: AsyncSession) -> int:
        return int(await db.scalar(select(func.count(User.id))) or 0)

    async def get_by_id(self, db: AsyncSession, user_id: int) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.roles), selectinload(User.case_profile))
            .where(User.id == user_id)
        )
        return await db.scalar(stmt)

    async def get_by_username(self, db: AsyncSession, username: str) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.roles), selectinload(User.case_profile))
            .where(User.username == username)
        )
        return await db.scalar(stmt)

    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.roles), selectinload(User.case_profile))
            .where(User.email == email)
        )
        return await db.scalar(stmt)

    async def ensure_role(self, db: AsyncSession, role_name: RoleName) -> Role:
        stmt = select(Role).where(Role.name == role_name)
        role = await db.scalar(stmt)
        if role:
            return role
        role = Role(name=role_name, description=role_name.value)
        db.add(role)
        await db.flush()
        return role

    async def create(
        self,
        db: AsyncSession,
        *,
        username: str,
        email: str,
        password_hash: str,
        role_name: RoleName,
    ) -> User:
        role = await self.ensure_role(db, role_name)
        user = User(username=username, email=email, password_hash=password_hash)
        user.roles = [role]
        db.add(user)
        await db.flush()
        await db.refresh(user, attribute_names=["roles"])
        return user

    async def list_users(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        role: str | None = None,
    ) -> tuple[list[User], int]:
        stmt = select(User).options(selectinload(User.roles)).order_by(User.created_at.desc())
        count_stmt = select(func.count(User.id))
        if role:
            role_name = RoleName(role)
            stmt = stmt.join(User.roles).where(Role.name == role_name)
            count_stmt = count_stmt.join(User.roles).where(Role.name == role_name)

        stmt = stmt.offset((page - 1) * size).limit(size)
        users = list((await db.scalars(stmt)).all())
        total = int(await db.scalar(count_stmt) or 0)
        return users, total

    async def update_primary_role(self, db: AsyncSession, user: User, role_name: RoleName) -> User:
        role = await self.ensure_role(db, role_name)
        user.roles = [role]
        await db.flush()
        await db.refresh(user, attribute_names=["roles"])
        return user

    async def get_case_profile_by_user_id(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> UserCaseProfile | None:
        stmt = select(UserCaseProfile).where(UserCaseProfile.user_id == user_id)
        return await db.scalar(stmt)

    async def upsert_case_profile(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        profile_data: dict,
    ) -> UserCaseProfile:
        profile = await self.get_case_profile_by_user_id(db, user_id)
        if profile is None:
            profile = UserCaseProfile(user_id=user_id)
            db.add(profile)

        for key, value in profile_data.items():
            setattr(profile, key, value)

        await db.flush()
        await db.refresh(profile)
        return profile


user_repo = UserRepository()
