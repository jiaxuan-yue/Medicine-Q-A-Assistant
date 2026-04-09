"""反馈模型。"""

import enum
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Integer, String, Text

from app.db.base import Base


class FeedbackType(str, enum.Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    CORRECTION = "correction"
    BADCASE = "badcase"


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    feedback_type = Column(Enum(FeedbackType), nullable=False)
    content = Column(Text, nullable=True)  # 纠错内容或评论
    metadata_json = Column(JSON, nullable=True)  # 额外信息
    created_at = Column(DateTime, default=datetime.utcnow)
