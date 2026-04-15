"""Elasticsearch async client wrapper for TCM chunk indexing."""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Default index for chunk-level documents
TCM_CHUNKS_INDEX = f"{settings.ES_INDEX_PREFIX}_chunks"

# Mappings with ik_max_word analyzer for Chinese text
TCM_CHUNKS_MAPPINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "ik_chinese": {
                    "type": "custom",
                    "tokenizer": "ik_max_word",
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "chunk_text": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "normalized_text": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "doc_id": {"type": "keyword"},
            "chunk_id": {"type": "keyword"},
            "doc_title": {"type": "keyword"},
            "metadata": {"type": "object", "enabled": False},
        }
    },
}


class ESClient:
    """Resilient Elasticsearch async client — never crashes if ES is down."""

    def __init__(self) -> None:
        self._client: AsyncElasticsearch | None = None
        self._available: bool = False

    # ── lifecycle ───────────────────────────────────────────

    async def init(self) -> None:
        """Connect to Elasticsearch using config.ES_HOSTS."""
        try:
            self._client = AsyncElasticsearch(
                hosts=settings.ES_HOSTS,
                request_timeout=10,
                retry_on_timeout=True,
                max_retries=2,
            )
            info = await self._client.info()
            self._available = True
            logger.info(
                "Elasticsearch 连接就绪: %s (version %s)",
                settings.ES_HOSTS,
                info["version"]["number"],
            )
        except Exception as exc:
            self._available = False
            logger.warning("Elasticsearch 不可用: %s", exc)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            logger.info("Elasticsearch 连接已关闭")

    @property
    def available(self) -> bool:
        return self._available and self._client is not None

    # ── index management ────────────────────────────────────

    async def create_index(self, index_name: str, mappings: dict | None = None) -> None:
        """Create an index if it does not exist."""
        if not self.available:
            return
        try:
            exists = await self._client.indices.exists(index=index_name)  # type: ignore[union-attr]
            if not exists:
                body = mappings or TCM_CHUNKS_MAPPINGS
                await self._client.indices.create(  # type: ignore[union-attr]
                    index=index_name,
                    settings=body.get("settings"),
                    mappings=body.get("mappings"),
                )
                logger.info("创建索引 %s 成功", index_name)
        except Exception as exc:
            logger.error("创建索引 %s 失败: %s", index_name, exc)

    async def delete_index(self, index_name: str) -> None:
        if not self.available:
            return
        try:
            await self._client.indices.delete(index=index_name, ignore=[404])  # type: ignore[union-attr]
            logger.info("删除索引 %s", index_name)
        except Exception as exc:
            logger.error("删除索引 %s 失败: %s", index_name, exc)

    # ── document operations ─────────────────────────────────

    async def index_document(self, index_name: str, doc_id: str, body: dict) -> None:
        """Index a single document."""
        if not self.available:
            return
        try:
            await self._client.index(index=index_name, id=doc_id, document=body)  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("索引文档 %s 失败: %s", doc_id, exc)

    async def bulk_index(self, index_name: str, documents: list[dict]) -> int:
        """Bulk index documents. Returns count of successfully indexed docs."""
        if not self.available:
            return 0
        try:
            actions = []
            for doc in documents:
                action = {
                    "_index": index_name,
                    "_id": doc.get("chunk_id", doc.get("doc_id")),
                    "_source": doc,
                }
                actions.append(action)
            success, errors = await async_bulk(self._client, actions, raise_on_error=False)
            if errors:
                logger.warning("Bulk 索引部分失败: %d errors", len(errors))
            return success
        except Exception as exc:
            logger.error("Bulk 索引失败: %s", exc)
            return 0

    # ── search ──────────────────────────────────────────────

    async def search_bm25(
        self, index_name: str, query: str, top_k: int = 20
    ) -> list[dict]:
        """BM25 search, return list of {doc_id, chunk_id, chunk_text, score, metadata}."""
        if not self.available:
            return []
        try:
            resp = await self._client.search(  # type: ignore[union-attr]
                index=index_name,
                query={
                    "multi_match": {
                        "query": query,
                        "fields": ["normalized_text^4", "chunk_text^2", "doc_title"],
                        "type": "best_fields",
                    }
                },
                size=top_k,
                _source=True,
            )
            results: list[dict] = []
            for hit in resp["hits"]["hits"]:
                source = hit["_source"]
                results.append(
                    {
                        "doc_id": source.get("doc_id", ""),
                        "chunk_id": source.get("chunk_id", hit["_id"]),
                        "chunk_text": source.get("chunk_text", ""),
                        "normalized_text": source.get("normalized_text", source.get("chunk_text", "")),
                        "doc_title": source.get("doc_title", ""),
                        "score": float(hit["_score"]),
                        "metadata": source.get("metadata", {}),
                    }
                )
            return results
        except Exception as exc:
            logger.error("BM25 搜索失败: %s", exc)
            return []


es_client = ESClient()
