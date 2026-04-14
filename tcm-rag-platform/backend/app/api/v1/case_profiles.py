"""用户多角色档案接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.repositories.case_profile_repo import case_profile_repo
from app.schemas.case_profile import CaseProfileCreate, CaseProfileUpdate
from app.services.case_profile_service import case_profile_service
from app.utils.response import success_response

router = APIRouter()


@router.get("")
async def list_case_profiles(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await case_profile_service.list_profiles(db, case_profile_repo, int(current_user["sub"]))
    return success_response(data=data)


@router.post("")
async def create_case_profile(
    payload: CaseProfileCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await case_profile_service.create_profile(db, case_profile_repo, int(current_user["sub"]), payload)
    return success_response(data=data, message="角色档案创建成功")


@router.put("/{profile_id}")
async def update_case_profile(
    profile_id: int,
    payload: CaseProfileUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await case_profile_service.update_profile(
        db,
        case_profile_repo,
        int(current_user["sub"]),
        profile_id,
        payload,
    )
    return success_response(data=data, message="角色档案更新成功")
