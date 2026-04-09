"""文档接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.core.exceptions import BadRequestError, ResourceNotFoundError
from app.db.repositories.document_repo import document_repo
from app.models.document import DocumentStatus
from app.services.document_ingest_service import document_ingest_service
from app.services.document_service import serialize_document
from app.utils.response import success_response

router = APIRouter()


@router.get("")
async def list_documents(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=200),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin", "reviewer", "operator")),
):
    if status:
        try:
            DocumentStatus(status)
        except ValueError as exc:
            raise BadRequestError(message="无效的文档状态") from exc
    items, total = await document_repo.list_documents(db, page=page, size=size, status=status)
    return success_response(
        data={
            "items": [serialize_document(item) for item in items],
            "total": total,
            "page": page,
            "size": size,
        }
    )


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin", "reviewer", "operator")),
):
    document = await document_repo.get_by_doc_id(db, doc_id)
    if not document:
        raise ResourceNotFoundError(message="文档不存在")
    return success_response(data=serialize_document(document))


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin", "reviewer", "operator")),
):
    document = await document_ingest_service.ingest_upload(
        db,
        uploaded_by=int(current_user["sub"]),
        file=file,
    )
    return success_response(data=serialize_document(document), message="文档上传成功")
