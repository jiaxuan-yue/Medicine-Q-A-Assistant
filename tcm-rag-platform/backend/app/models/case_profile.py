"""用户多角色基础档案。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class CaseProfile(Base):
    __tablename__ = "case_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_name = Column(String(64), nullable=False)
    gender = Column(String(16), nullable=True)
    age = Column(Integer, nullable=True)
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(Integer, nullable=True)
    medical_history = Column(Text, nullable=True)
    allergy_history = Column(Text, nullable=True)
    current_medications = Column(Text, nullable=True)
    menstrual_history = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    profile_completed = Column(Boolean, default=False, nullable=False)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="case_profiles")
