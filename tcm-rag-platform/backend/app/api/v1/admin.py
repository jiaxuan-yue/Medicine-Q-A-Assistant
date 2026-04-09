"""管理后台接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.core.exceptions import BadRequestError, ResourceNotFoundError
from app.db.repositories.document_repo import document_repo
from app.db.repositories.user_repo import user_repo
from app.models.document import DocumentStatus
from app.models.role import RoleName
from app.schemas.document import DocumentReviewRequest as ReviewDocumentRequest
from app.schemas.user import UserRoleUpdateRequest as UpdateUserRoleRequest
from app.services.document_service import document_service, serialize_document
from app.services.user_service import serialize_user
from app.utils.response import success_response

router = APIRouter()


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=200),
    role: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin")),
):
    try:
        items, total = await user_repo.list_users(db, page=page, size=size, role=role)
    except ValueError as exc:
        raise BadRequestError(message="无效的角色类型") from exc
    return success_response(
        data={
            "items": [serialize_user(item) for item in items],
            "total": total,
            "page": page,
            "size": size,
        }
    )


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    payload: UpdateUserRoleRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin")),
):
    user = await user_repo.get_by_id(db, user_id)
    if not user:
        raise ResourceNotFoundError(message="用户不存在")
    try:
        role_name = RoleName(payload.role)
    except ValueError as exc:
        raise BadRequestError(message="无效的角色类型") from exc
    updated_user = await user_repo.update_primary_role(db, user, role_name)
    return success_response(data=serialize_user(updated_user), message="角色更新成功")


@router.post("/documents/{doc_id}/review")
async def review_document(
    doc_id: str,
    payload: ReviewDocumentRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin", "reviewer")),
):
    document = await document_repo.get_by_doc_id(db, doc_id)
    if not document:
        raise ResourceNotFoundError(message="文档不存在")
    status = DocumentStatus.PUBLISHED if payload.action == "approve" else DocumentStatus.REJECTED
    updated = await document_repo.update_status(db, document=document, status=status)
    return success_response(data=serialize_document(updated), message="审核完成")


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin", "reviewer", "operator")),
):
    data = await document_service.build_dashboard_stats(db)
    return success_response(data=data)
