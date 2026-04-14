"""用户模型。"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    roles = relationship("Role", secondary="user_roles", back_populates="users")
    sessions = relationship("ChatSession", back_populates="user")
    documents = relationship("Document", back_populates="uploader")
    case_profile = relationship(
        "UserCaseProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    case_profiles = relationship(
        "CaseProfile",
        back_populates="user",
        cascade="all, delete-orphan",
    )
