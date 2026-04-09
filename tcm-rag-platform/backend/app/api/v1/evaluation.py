"""评测接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.schemas.evaluation import EvalRunRequest, EvalTaskOut
from app.services.evaluation_service import evaluation_service
from app.utils.response import success_response

router = APIRouter()


@router.post("/run")
async def trigger_eval_run(
    payload: EvalRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    user_id = int(current_user["sub"])
    task = await evaluation_service.create_eval_task(
        db,
        eval_type=payload.eval_type,
        dataset_path=payload.dataset_path,
        triggered_by=user_id,
    )
    return success_response(
        data=EvalTaskOut.model_validate(task).model_dump(),
        message="评测任务已创建",
    )


@router.get("/tasks")
async def list_eval_tasks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    items, total = await evaluation_service.list_eval_tasks(db, page=page, size=size)
    return success_response(
        data={
            "items": [EvalTaskOut.model_validate(t).model_dump() for t in items],
            "total": total,
            "page": page,
            "size": size,
        }
    )


@router.get("/tasks/{task_id}")
async def get_eval_task_detail(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    data = await evaluation_service.get_eval_results(db, task_id)
    return success_response(data=data)


@router.get("/compare")
async def compare_eval_runs(
    task_id_1: int = Query(..., description="第一个评测任务 ID"),
    task_id_2: int = Query(..., description="第二个评测任务 ID"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    data = await evaluation_service.compare_eval_runs(db, task_id_1, task_id_2)
    return success_response(data=data)
