"""反馈相关 schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    message_id: str
    feedback_type: str = Field(..., description="thumbs_up / thumbs_down / correction / badcase")
    content: str | None = None
    metadata_json: dict | None = None


class FeedbackOut(BaseModel):
    id: int
    message_id: str
    user_id: int
    feedback_type: str
    content: str | None = None
    metadata_json: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackStatsOut(BaseModel):
    total: int
    by_type: dict[str, int]
    trend: list[dict]
