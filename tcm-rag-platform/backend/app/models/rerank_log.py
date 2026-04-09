"""重排日志模型。"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String

from app.db.base import Base


class RerankLog(Base):
    __tablename__ = "rerank_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), nullable=True, index=True)
    message_id = Column(String(36), nullable=True, index=True)
    input_chunks = Column(JSON, nullable=True)  # 重排前
    output_chunks = Column(JSON, nullable=True)  # 重排后
    rerank_scores = Column(JSON, nullable=True)  # 各分数明细
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
