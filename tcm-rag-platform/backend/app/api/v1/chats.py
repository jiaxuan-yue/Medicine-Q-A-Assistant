"""聊天接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.chat import ChatQueryRequest, CreateSessionRequest
from app.services.chat_service import chat_service
from app.utils.response import success_response

router = APIRouter()


@router.post("")
async def create_session(
    payload: CreateSessionRequest | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await chat_service.create_session(
        db,
        user_id=int(current_user["sub"]),
        title=payload.title if payload else None,
    )
    return success_response(data=data, message="会话创建成功")


@router.get("")
async def list_sessions(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await chat_service.list_sessions(
        db,
        user_id=int(current_user["sub"]),
        page=page,
        size=size,
    )
    return success_response(
        data={
            "items": items,
            "total": total,
            "page": page,
            "size": size,
        }
    )


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await chat_service.list_messages(db, user_id=int(current_user["sub"]), session_id=session_id)
    return success_response(data=data)


@router.post("/{session_id}/stream")
async def stream_chat(
    session_id: str,
    payload: ChatQueryRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    answer_payload = await chat_service.build_answer_payload(
        db,
        user_id=int(current_user["sub"]),
        session_id=session_id,
        query=payload.query,
    )
    return StreamingResponse(
        chat_service.stream_answer_events(answer_payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
