"""会话模型。"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class ChatSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4())
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(256), default="新对话")
    summary = Column(Text, nullable=True)  # 对话摘要（多轮压缩）
    case_profile_id = Column(Integer, nullable=True)
    case_profile_name = Column(String(128), nullable=True)
    case_profile_summary = Column(Text, nullable=True)
    consultation_context = Column(JSON, nullable=True)
    followup_state = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", order_by="Message.created_at")
