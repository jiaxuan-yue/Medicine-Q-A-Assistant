"""角色模型和用户-角色关联表。"""

import enum

from sqlalchemy import Column, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class RoleName(str, enum.Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    OPERATOR = "operator"
    USER = "user"


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Enum(RoleName), unique=True, nullable=False)
    description = Column(String(256), nullable=True)

    users = relationship("User", secondary="user_roles", back_populates="roles")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
