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
    case_profile_id: int | None = None
    case_profile_name: str | None = None
    case_profile_summary: str | None = None
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    kind: str | None = None
    citations: list[Citation] | None = None
    latency_ms: int | None = None
    created_at: str


class ChatStreamRequest(BaseModel):
    query: str


class UserLocationPayload(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: float | None = None
    source: str | None = "browser-geolocation"
    label: str | None = None
    city: str | None = None
    province: str | None = None


class ChatQueryRequest(BaseModel):
    query: str
    user_location: UserLocationPayload | None = None


class CreateSessionRequest(BaseModel):
    title: str | None = None
    case_profile_id: int
