"""召回日志模型。"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text

from app.db.base import Base


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), nullable=True, index=True)
    message_id = Column(String(36), nullable=True, index=True)
    query = Column(Text, nullable=False)
    rewritten_query = Column(Text, nullable=True)
    sparse_hits = Column(JSON, nullable=True)  # BM25 命中 chunk_ids + scores
    dense_hits = Column(JSON, nullable=True)  # 向量命中 chunk_ids + scores
    graph_hits = Column(JSON, nullable=True)  # 图谱命中 chunk_ids + scores
    merged_hits = Column(JSON, nullable=True)  # RRF 融合后结果
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
