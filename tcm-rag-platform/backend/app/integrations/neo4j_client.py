"""Neo4j async driver wrapper for TCM knowledge graph."""

from __future__ import annotations

from neo4j import AsyncGraphDatabase, AsyncDriver

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Supported entity labels
ENTITY_LABELS = (
    "Symptom", "Syndrome", "Formula", "Herb",
    "Efficacy", "Contraindication", "TongueSign", "PulseSign",
)

# Supported relationship types
RELATIONSHIP_TYPES = (
    "ASSOCIATED_WITH", "RECOMMENDS", "CONTAINS",
    "HAS_EFFICACY", "HAS_CONTRAINDICATION", "SUPPORTS",
)


class Neo4jClient:
    """Resilient Neo4j async client — never crashes if Neo4j is down."""

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None
        self._available: bool = False

    # ── lifecycle ───────────────────────────────────────────

    async def init(self) -> None:
        """Connect using config.NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD."""
        try:
            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                max_connection_lifetime=300,
                notifications_min_severity="WARNING",
            )
            # verify connectivity
            async with self._driver.session() as session:
                result = await session.run("RETURN 1 AS n")
                await result.consume()
            self._available = True
            logger.info("Neo4j 连接就绪: %s", settings.NEO4J_URI)
        except Exception as exc:
            self._available = False
            logger.warning("Neo4j 不可用: %s", exc)

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            logger.info("Neo4j 连接已关闭")

    @property
    def available(self) -> bool:
        return self._available and self._driver is not None

    # ── generic query ───────────────────────────────────────

    async def run_query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Execute a Cypher query and return list of record dicts."""
        if not self.available:
            return []
        try:
            async with self._driver.session() as session:  # type: ignore[union-attr]
                result = await session.run(cypher, parameters=params or {})
                records = [record.data() async for record in result]
                return records
        except Exception as exc:
            logger.error("Neo4j 查询失败: %s | cypher=%s", exc, cypher[:200])
            return []

    # ── entity CRUD ─────────────────────────────────────────

    async def create_entity(
        self, name: str, entity_type: str, properties: dict | None = None
    ) -> None:
        """MERGE an entity node with the given label and properties."""
        if not self.available:
            return
        props = properties or {}
        cypher = (
            f"MERGE (n:{entity_type} {{name: $name}}) "
            "SET n += $props"
        )
        await self.run_query(cypher, {"name": name, "props": props})

    async def create_relationship(
        self,
        from_name: str,
        to_name: str,
        rel_type: str,
        properties: dict | None = None,
    ) -> None:
        """MERGE a relationship between two entities (matched by name)."""
        if not self.available:
            return
        props = properties or {}
        cypher = (
            "MATCH (a {name: $from_name}), (b {name: $to_name}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            "SET r += $props"
        )
        await self.run_query(
            cypher, {"from_name": from_name, "to_name": to_name, "props": props}
        )

    async def find_entity(self, name: str) -> dict | None:
        """Find a single entity by name across all labels."""
        records = await self.run_query(
            "MATCH (n {name: $name}) RETURN n, labels(n) AS labels LIMIT 1",
            {"name": name},
        )
        if not records:
            return None
        rec = records[0]
        node = rec.get("n", {})
        return {
            "name": node.get("name", name),
            "labels": rec.get("labels", []),
            "properties": dict(node),
        }

    # ── graph traversal ─────────────────────────────────────

    async def expand_entity(self, name: str, max_hops: int = 2) -> list[dict]:
        """Return related entities within max_hops."""
        cypher = (
            "MATCH (start {name: $name})-[r*1.." + str(max_hops) + "]-(related) "
            "RETURN DISTINCT related.name AS name, labels(related) AS labels, "
            "type(last(r)) AS rel_type"
        )
        records = await self.run_query(cypher, {"name": name})
        results: list[dict] = []
        seen: set[str] = set()
        for rec in records:
            n = rec.get("name")
            if n and n not in seen:
                seen.add(n)
                results.append(
                    {
                        "name": n,
                        "labels": rec.get("labels", []),
                        "rel_type": rec.get("rel_type", ""),
                    }
                )
        return results

    async def find_path(self, from_name: str, to_name: str) -> list[dict]:
        """Find shortest path between two entities."""
        cypher = (
            "MATCH p = shortestPath((a {name: $from_name})-[*..5]-(b {name: $to_name})) "
            "UNWIND nodes(p) AS node "
            "RETURN node.name AS name, labels(node) AS labels"
        )
        return await self.run_query(
            cypher, {"from_name": from_name, "to_name": to_name}
        )


neo4j_client = Neo4jClient()
