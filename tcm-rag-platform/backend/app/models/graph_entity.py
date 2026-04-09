"""图谱实体映射模型。"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String

from app.db.base import Base


class GraphEntity(Base):
    __tablename__ = "graph_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(
        String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4())
    )
    name = Column(String(256), nullable=False, index=True)
    entity_type = Column(
        String(64), nullable=False, index=True
    )  # Symptom/Syndrome/Formula/Herb/Effect/Contraindication/TongueSign/PulseSign
    aliases = Column(JSON, nullable=True)  # 别名列表
    properties = Column(JSON, nullable=True)  # 性味归经等属性
    neo4j_node_id = Column(String(64), nullable=True)  # Neo4j 内部 ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
