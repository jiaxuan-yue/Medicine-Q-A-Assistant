"""评测任务模型。"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Integer, String

from app.db.base import Base


class EvalStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvalTask(Base):
    __tablename__ = "eval_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4())
    )
    task_type = Column(String(64), nullable=False)  # retrieval/rewrite/generation/regression
    status = Column(Enum(EvalStatus), default=EvalStatus.PENDING)
    config_json = Column(JSON, nullable=True)  # 评测配置
    result_json = Column(JSON, nullable=True)  # 评测结果
    triggered_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
