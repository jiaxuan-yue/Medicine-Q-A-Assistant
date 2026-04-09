"""认证接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.repositories.user_repo import user_repo
from app.schemas.auth import LoginRequest, RefreshTokenRequest, RegisterRequest
from app.services.auth_service import auth_service
from app.services.user_service import serialize_user, user_service
from app.utils.response import success_response

router = APIRouter()


@router.post("/register")
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    data = await auth_service.register(db, payload)
    return success_response(data=data, message="注册成功")


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    data = await auth_service.login(db, payload)
    return success_response(data=data, message="登录成功")


@router.post("/refresh")
async def refresh(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    data = await auth_service.refresh(db, payload.refresh_token)
    return success_response(data=data, message="刷新成功")


@router.post("/logout")
async def logout():
    return success_response(message="退出成功")


@router.get("/me")
async def me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.get_user_or_raise(db, user_repo, int(current_user["sub"]))
    return success_response(data=serialize_user(user))
