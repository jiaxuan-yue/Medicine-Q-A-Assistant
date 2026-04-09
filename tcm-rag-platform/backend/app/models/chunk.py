"""文档分块模型。"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(
        String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4())
    )
    doc_id = Column(
        String(36), ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index = Column(Integer, nullable=False)  # 在文档中的顺序
    chunk_text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)
    metadata_json = Column(JSON, nullable=True)  # 章节、标题等元数据
    embedding_id = Column(String(64), nullable=True)  # FAISS 向量 ID
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")
