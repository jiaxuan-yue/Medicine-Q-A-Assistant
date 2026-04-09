"""知识图谱接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.core.exceptions import ResourceNotFoundError
from app.models.graph_entity import GraphEntity
from app.schemas.graph import (
    GraphEntityCreate,
    GraphEntityOut,
    GraphRelationshipCreate,
    GraphVisualizationData,
)
from app.utils.response import success_response

router = APIRouter()


# ── 查询类接口 ─────────────────────────────────────────────

@router.get("/entities")
async def search_entities(
    q: str = Query("", description="搜索关键词"),
    entity_type: str | None = Query(None, alias="type", description="实体类型筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    stmt = select(GraphEntity)
    count_stmt = select(func.count()).select_from(GraphEntity)

    if q:
        like_pattern = f"%{q}%"
        stmt = stmt.where(GraphEntity.name.ilike(like_pattern))
        count_stmt = count_stmt.where(GraphEntity.name.ilike(like_pattern))

    if entity_type:
        stmt = stmt.where(GraphEntity.entity_type == entity_type)
        count_stmt = count_stmt.where(GraphEntity.entity_type == entity_type)

    total = (await db.execute(count_stmt)).scalar() or 0
    stmt = stmt.order_by(GraphEntity.name).offset((page - 1) * size).limit(size)
    items = list((await db.execute(stmt)).scalars().all())

    return success_response(
        data={
            "items": [GraphEntityOut.model_validate(e).model_dump() for e in items],
            "total": total,
            "page": page,
            "size": size,
        }
    )


@router.get("/entities/{name}")
async def get_entity_detail(
    name: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    stmt = select(GraphEntity).where(GraphEntity.name == name)
    entity = (await db.execute(stmt)).scalar_one_or_none()
    if entity is None:
        raise ResourceNotFoundError(message="实体不存在")

    # 查找邻居：properties 中可能存储了 relationships，或从同一 entity_type 关联
    neighbors_stmt = (
        select(GraphEntity)
        .where(GraphEntity.name != name)
        .where(GraphEntity.entity_type == entity.entity_type)
        .limit(20)
    )
    neighbors = list((await db.execute(neighbors_stmt)).scalars().all())

    return success_response(
        data={
            "entity": GraphEntityOut.model_validate(entity).model_dump(),
            "neighbors": [GraphEntityOut.model_validate(n).model_dump() for n in neighbors],
        }
    )


@router.get("/paths")
async def find_path(
    from_entity: str = Query(..., alias="from", description="起始实体名称"),
    to_entity: str = Query(..., alias="to", description="目标实体名称"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    # 查找起止实体
    stmt_from = select(GraphEntity).where(GraphEntity.name == from_entity)
    stmt_to = select(GraphEntity).where(GraphEntity.name == to_entity)
    e_from = (await db.execute(stmt_from)).scalar_one_or_none()
    e_to = (await db.execute(stmt_to)).scalar_one_or_none()

    if e_from is None:
        raise ResourceNotFoundError(message=f"起始实体不存在: {from_entity}")
    if e_to is None:
        raise ResourceNotFoundError(message=f"目标实体不存在: {to_entity}")

    # 简单路径：直接关系（同类型实体间）
    path = [
        GraphEntityOut.model_validate(e_from).model_dump(),
        GraphEntityOut.model_validate(e_to).model_dump(),
    ]
    return success_response(data={"path": path})


@router.get("/visualization")
async def get_visualization_data(
    entity_type: str | None = Query(None, alias="type"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    stmt = select(GraphEntity)
    if entity_type:
        stmt = stmt.where(GraphEntity.entity_type == entity_type)
    stmt = stmt.limit(limit)
    entities = list((await db.execute(stmt)).scalars().all())

    nodes = [
        {
            "id": e.entity_id,
            "name": e.name,
            "type": e.entity_type,
            "group": e.entity_type,
        }
        for e in entities
    ]

    # 基于 properties 中的 related_entities 构建边
    edges: list[dict] = []
    entity_ids = {e.name for e in entities}
    for e in entities:
        props = e.properties or {}
        relations = props.get("relations", [])
        for rel in relations:
            target = rel.get("target", "")
            if target in entity_ids:
                edges.append(
                    {
                        "source": e.entity_id,
                        "target": target,
                        "relation": rel.get("type", "related"),
                    }
                )

    return success_response(
        data=GraphVisualizationData(nodes=nodes, edges=edges).model_dump()
    )


# ── 管理类接口 ─────────────────────────────────────────────

@router.post("/entities")
async def create_or_update_entity(
    payload: GraphEntityCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin")),
):
    # 查找是否已存在同名实体
    stmt = select(GraphEntity).where(GraphEntity.name == payload.name)
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.entity_type = payload.entity_type
        existing.aliases = payload.aliases
        existing.properties = payload.properties
        await db.flush()
        await db.refresh(existing)
        entity = existing
        msg = "实体更新成功"
    else:
        entity = GraphEntity(
            name=payload.name,
            entity_type=payload.entity_type,
            aliases=payload.aliases,
            properties=payload.properties,
        )
        db.add(entity)
        await db.flush()
        await db.refresh(entity)
        msg = "实体创建成功"

    return success_response(
        data=GraphEntityOut.model_validate(entity).model_dump(), message=msg
    )


@router.post("/relationships")
async def create_relationship(
    payload: GraphRelationshipCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_role("admin")),
):
    # 验证两端实体存在
    stmt_from = select(GraphEntity).where(GraphEntity.name == payload.from_entity)
    stmt_to = select(GraphEntity).where(GraphEntity.name == payload.to_entity)
    e_from = (await db.execute(stmt_from)).scalar_one_or_none()
    e_to = (await db.execute(stmt_to)).scalar_one_or_none()

    if e_from is None:
        raise ResourceNotFoundError(message=f"源实体不存在: {payload.from_entity}")
    if e_to is None:
        raise ResourceNotFoundError(message=f"目标实体不存在: {payload.to_entity}")

    # 将关系写入 from_entity 的 properties.relations
    props = e_from.properties or {}
    relations: list[dict] = props.get("relations", [])
    relations.append(
        {
            "target": payload.to_entity,
            "type": payload.relation_type,
            **(payload.properties or {}),
        }
    )
    props["relations"] = relations
    e_from.properties = props
    await db.flush()

    return success_response(
        data={
            "from_entity": payload.from_entity,
            "to_entity": payload.to_entity,
            "relation_type": payload.relation_type,
        },
        message="关系创建成功",
    )
