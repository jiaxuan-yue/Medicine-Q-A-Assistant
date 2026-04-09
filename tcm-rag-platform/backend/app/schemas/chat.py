"""对话与流式问答 schema。"""

from pydantic import BaseModel


class Citation(BaseModel):
    chunk_id: str
    doc_title: str
    text: str


class ChatSessionOut(BaseModel):
    session_id: str
    title: str
    summary: str | None
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[Citation] | None = None
    latency_ms: int | None = None
    created_at: str


class ChatStreamRequest(BaseModel):
    query: str


class ChatQueryRequest(BaseModel):
    query: str


class CreateSessionRequest(BaseModel):
    title: str | None = None
