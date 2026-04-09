"""答案与引用日志模型。"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text

from app.db.base import Base


class AnswerLog(Base):
    __tablename__ = "answer_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), nullable=True, index=True)
    message_id = Column(String(36), unique=True, nullable=True, index=True)
    answer_text = Column(Text, nullable=True)
    cited_chunks = Column(JSON, nullable=True)  # 实际被引用的 chunk 列表
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    model_name = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
