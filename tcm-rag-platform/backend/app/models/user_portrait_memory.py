"""User portrait memories distilled from conversations."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class PortraitMemoryStatus(str, enum.Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class UserPortraitMemory(Base):
    __tablename__ = "user_portrait_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(
        String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4())
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id = Column(
        String(36),
        ForeignKey("sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_message_id = Column(String(36), nullable=True, index=True)
    memory_type = Column(String(32), nullable=False, index=True)
    facet_key = Column(String(128), nullable=False, index=True)
    content = Column(Text, nullable=False)
    status = Column(
        Enum(PortraitMemoryStatus),
        default=PortraitMemoryStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    importance_score = Column(Float, default=0.6, nullable=False)
    confidence_score = Column(Float, default=0.7, nullable=False)
    reinforcement_count = Column(Integer, default=1, nullable=False)
    embedding_json = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    superseded_at = Column(DateTime, nullable=True)
    superseded_by = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="portrait_memories")
