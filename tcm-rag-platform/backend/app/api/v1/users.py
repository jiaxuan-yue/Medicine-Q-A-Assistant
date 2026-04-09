"""用户接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.repositories.user_repo import user_repo
from app.services.user_service import serialize_user, user_service
from app.utils.response import success_response

router = APIRouter()


@router.get("/me")
async def get_my_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.get_user_or_raise(db, user_repo, int(current_user["sub"]))
    return success_response(data=serialize_user(user))
