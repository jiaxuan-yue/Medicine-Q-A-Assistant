"""FAISS vector store manager for dense retrieval."""

from __future__ import annotations

import os
import pickle
from pathlib import Path

import faiss
import numpy as np

from app.core.config import settings
from app.core.logger import get_logger
from app.integrations.embedding_client import embedding_client

logger = get_logger(__name__)

DEFAULT_INDEX_DIR = os.path.join(settings.PROCESSED_DOCUMENTS_DIR, "faiss_index")


class VectorStore:
    """FAISS IndexFlatIP manager with metadata mapping.

    Resilient: all public methods return empty results rather than raising
    if the index is uninitialised or the embedding service is unavailable.
    """

    def __init__(self) -> None:
        self._dim: int = settings.EMBEDDING_DIM
        self._index: faiss.IndexFlatIP | None = None
        self._metadata: list[dict] = []  # position → chunk metadata
        self._available: bool = False

    # ── lifecycle ───────────────────────────────────────────

    def _ensure_index(self) -> None:
        if self._index is None:
            self._index = faiss.IndexFlatIP(self._dim)
            self._metadata = []
            self._available = True

    @property
    def available(self) -> bool:
        return self._available and self._index is not None

    @property
    def size(self) -> int:
        return self._index.ntotal if self._index else 0

    # ── build / add ─────────────────────────────────────────

    async def build_index(
        self, embeddings: list[list[float]], metadata: list[dict]
    ) -> None:
        """Build a new FAISS index from scratch (replaces existing)."""
        try:
            self._index = faiss.IndexFlatIP(self._dim)
            vectors = np.array(embeddings, dtype=np.float32)
            faiss.normalize_L2(vectors)
            self._index.add(vectors)
            self._metadata = list(metadata)
            self._available = True
            logger.info("FAISS 索引已构建: %d 向量", self._index.ntotal)
        except Exception as exc:
            self._available = False
            logger.error("构建 FAISS 索引失败: %s", exc)

    async def add_vectors(
        self, embeddings: list[list[float]], metadata: list[dict]
    ) -> None:
        """Add vectors to existing index (incremental)."""
        self._ensure_index()
        try:
            vectors = np.array(embeddings, dtype=np.float32)
            faiss.normalize_L2(vectors)
            self._index.add(vectors)  # type: ignore[union-attr]
            self._metadata.extend(metadata)
            logger.info("FAISS 索引已追加: +%d (总 %d)", len(embeddings), self.size)
        except Exception as exc:
            logger.error("追加 FAISS 向量失败: %s", exc)

    # ── search ──────────────────────────────────────────────

    async def search(
        self, query_embedding: list[float], top_k: int = 20
    ) -> list[dict]:
        """Return list of {chunk_id, doc_id, chunk_text, score, metadata}."""
        if not self.available or self.size == 0:
            return []
        try:
            query_vec = np.array([query_embedding], dtype=np.float32)
            faiss.normalize_L2(query_vec)
            k = min(top_k, self.size)
            distances, indices = self._index.search(query_vec, k)  # type: ignore[union-attr]

            results: list[dict] = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx < 0 or idx >= len(self._metadata):
                    continue
                meta = self._metadata[idx]
                results.append(
                    {
                        "chunk_id": meta.get("chunk_id", ""),
                        "doc_id": meta.get("doc_id", ""),
                        "chunk_text": meta.get("chunk_text", ""),
                        "doc_title": meta.get("doc_title", ""),
                        "score": float(dist),
                        "metadata": meta.get("metadata", {}),
                    }
                )
            return results
        except Exception as exc:
            logger.error("FAISS 搜索失败: %s", exc)
            return []

    # ── persistence ─────────────────────────────────────────

    def save(self, path: str | None = None) -> None:
        """Save FAISS index and metadata to disk."""
        if not self.available:
            return
        save_dir = path or DEFAULT_INDEX_DIR
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        try:
            faiss.write_index(self._index, os.path.join(save_dir, "index.faiss"))  # type: ignore[arg-type]
            with open(os.path.join(save_dir, "metadata.pkl"), "wb") as f:
                pickle.dump(self._metadata, f)
            logger.info("FAISS 索引已保存: %s (%d 向量)", save_dir, self.size)
        except Exception as exc:
            logger.error("保存 FAISS 索引失败: %s", exc)

    def load(self, path: str | None = None) -> None:
        """Load FAISS index and metadata from disk."""
        load_dir = path or DEFAULT_INDEX_DIR
        index_path = os.path.join(load_dir, "index.faiss")
        meta_path = os.path.join(load_dir, "metadata.pkl")
        if not os.path.exists(index_path):
            logger.info("FAISS 索引文件不存在: %s，跳过加载", index_path)
            self._ensure_index()
            return
        try:
            self._index = faiss.read_index(index_path)
            with open(meta_path, "rb") as f:
                self._metadata = pickle.load(f)
            self._available = True
            logger.info("FAISS 索引已加载: %s (%d 向量)", load_dir, self.size)
        except Exception as exc:
            logger.error("加载 FAISS 索引失败: %s", exc)
            self._ensure_index()


vector_store = VectorStore()
