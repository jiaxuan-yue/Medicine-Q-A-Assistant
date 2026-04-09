"""知识图谱查询服务 — 实体搜索、邻居扩展、路径查找、查询扩展建议。"""

from __future__ import annotations

from app.core.config import settings
from app.core.logger import get_logger
from app.integrations.neo4j_client import neo4j_client, ENTITY_LABELS

logger = get_logger(__name__)


async def search_entities(
    query: str, entity_type: str | None = None
) -> list[dict]:
    """Search graph entities whose name contains the query string.

    Args:
        query: partial or full entity name
        entity_type: optional label filter (e.g. "Symptom", "Herb")

    Returns:
        list of {name, labels, properties}
    """
    if not neo4j_client.available:
        return []

    if entity_type and entity_type in ENTITY_LABELS:
        cypher = (
            f"MATCH (n:{entity_type}) WHERE n.name CONTAINS $q "
            "RETURN n.name AS name, labels(n) AS labels, properties(n) AS props "
            "LIMIT 20"
        )
    else:
        cypher = (
            "MATCH (n) WHERE n.name CONTAINS $q "
            "RETURN n.name AS name, labels(n) AS labels, properties(n) AS props "
            "LIMIT 20"
        )

    records = await neo4j_client.run_query(cypher, {"q": query})
    return [
        {
            "name": r.get("name", ""),
            "labels": r.get("labels", []),
            "properties": r.get("props", {}),
        }
        for r in records
    ]


async def get_entity_neighbors(
    entity_name: str, max_hops: int | None = None
) -> dict:
    """Expand an entity and return its neighborhood.

    Returns:
        {entity: {name, labels, properties}, neighbors: [...]}
    """
    hops = max_hops or settings.GRAPH_MAX_HOPS
    entity = await neo4j_client.find_entity(entity_name)
    if not entity:
        return {"entity": None, "neighbors": []}

    neighbors = await neo4j_client.expand_entity(entity_name, max_hops=hops)
    return {"entity": entity, "neighbors": neighbors}


async def find_paths(from_entity: str, to_entity: str) -> list[dict]:
    """Find shortest path between two entities.

    Returns:
        list of path nodes [{name, labels}, ...]
    """
    return await neo4j_client.find_path(from_entity, to_entity)


async def get_graph_suggestions(entities: list[str]) -> list[str]:
    """Suggest related entities for query expansion.

    Given a list of entity names from a user query, expand via graph
    and return unique neighbor names that could help retrieval.
    """
    if not neo4j_client.available or not entities:
        return []

    suggestions: list[str] = []
    seen: set[str] = set(entities)

    for entity_name in entities:
        neighbors = await neo4j_client.expand_entity(entity_name, max_hops=1)
        for nb in neighbors:
            name = nb.get("name", "")
            if name and name not in seen:
                seen.add(name)
                suggestions.append(name)

    # Limit suggestions to a reasonable number
    return suggestions[:15]
