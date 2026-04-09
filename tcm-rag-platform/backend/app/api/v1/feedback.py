"""反馈接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.schemas.feedback import FeedbackCreate, FeedbackOut, FeedbackStatsOut
from app.services.badcase_service import badcase_service
from app.services.feedback_service import feedback_service
from app.utils.response import success_response

router = APIRouter()


@router.post("")
async def submit_feedback(
    payload: FeedbackCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(current_user["sub"])

    # 如果是 badcase，自动归类并写入 metadata
    if payload.feedback_type == "badcase":
        category = badcase_service.categorize_badcase(payload.content)
        meta = payload.metadata_json or {}
        meta["category"] = category
        payload = payload.model_copy(update={"metadata_json": meta})

    fb = await feedback_service.create_feedback(db, user_id=user_id, data=payload)
    return success_response(data=FeedbackOut.model_validate(fb).model_dump(), message="反馈提交成功")


@router.get("/stats")
async def feedback_stats(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin")),
):
    data = await feedback_service.get_feedback_stats(db)
    return success_response(data=data)


@router.get("/{feedback_id}")
async def get_feedback(
    feedback_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fb = await feedback_service.get_feedback(db, feedback_id)
    return success_response(data=FeedbackOut.model_validate(fb).model_dump())


@router.get("")
async def list_feedback(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = current_user.get("role", "")
    user_id = None if role == "admin" else int(current_user["sub"])
    items, total = await feedback_service.list_feedback(db, user_id=user_id, page=page, size=size)
    return success_response(
        data={
            "items": [FeedbackOut.model_validate(i).model_dump() for i in items],
            "total": total,
            "page": page,
            "size": size,
        }
    )
