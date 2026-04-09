"""知识图谱相关 schema。"""

from __future__ import annotations

from pydantic import BaseModel


class GraphEntityOut(BaseModel):
    id: int
    entity_id: str
    name: str
    entity_type: str
    aliases: list[str] | None = None
    properties: dict | None = None

    model_config = {"from_attributes": True}


class GraphRelationOut(BaseModel):
    from_entity: str
    to_entity: str
    relation_type: str


class GraphVisualizationData(BaseModel):
    nodes: list[dict]
    edges: list[dict]


class GraphEntityCreate(BaseModel):
    name: str
    entity_type: str
    aliases: list[str] | None = None
    properties: dict | None = None


class GraphRelationshipCreate(BaseModel):
    from_entity: str
    to_entity: str
    relation_type: str
    properties: dict | None = None
