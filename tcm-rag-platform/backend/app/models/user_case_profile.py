"""用户基础病例档案。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class UserCaseProfile(Base):
    __tablename__ = "user_case_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    gender = Column(String(16), nullable=True)
    age = Column(Integer, nullable=True)
    chief_complaint = Column(String(255), nullable=True)
    symptom_duration = Column(String(64), nullable=True)
    primary_symptoms = Column(JSON, nullable=True)
    has_visited_doctor = Column(Boolean, default=False, nullable=False)
    currently_taking_medicine = Column(Boolean, default=False, nullable=False)
    medication_details = Column(Text, nullable=True)
    sleep_status = Column(String(128), nullable=True)
    appetite_status = Column(String(128), nullable=True)
    bowel_status = Column(String(128), nullable=True)
    tongue_description = Column(String(255), nullable=True)
    medical_history = Column(Text, nullable=True)
    allergy_history = Column(Text, nullable=True)
    menstrual_history = Column(Text, nullable=True)
    profile_completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="case_profile")
