"""文档模型。"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(
        String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4())
    )
    title = Column(String(512), nullable=False)
    source = Column(String(256), nullable=True)  # 来源（教材名/药典等）
    file_path = Column(String(512), nullable=True)  # MinIO 路径
    version = Column(Integer, default=1)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING)
    authority_score = Column(Float, default=0.5)  # 1.0=药典, 0.9=教材, 0.85=指南, 0.7=说明书, 0.5=FAQ
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    uploader = relationship("User", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document")
