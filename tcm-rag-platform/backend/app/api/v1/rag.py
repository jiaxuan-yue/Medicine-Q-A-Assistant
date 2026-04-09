"""RAG 预览接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.chat import ChatQueryRequest
from app.services.query_rewrite_service import query_rewrite_service
from app.services.retrieval_service import retrieval_service
from app.utils.response import success_response

router = APIRouter()


@router.post("/rewrite-preview")
async def rewrite_preview(payload: ChatQueryRequest, db: AsyncSession = Depends(get_db)):
    data = await query_rewrite_service.rewrite(db, payload.query)
    return success_response(data=data)


@router.post("/retrieve-preview")
async def retrieve_preview(payload: ChatQueryRequest, db: AsyncSession = Depends(get_db)):
    query_bundle = await query_rewrite_service.rewrite(db, payload.query)
    data = await retrieval_service.retrieve(db, query_bundle)
    return success_response(data=data)
