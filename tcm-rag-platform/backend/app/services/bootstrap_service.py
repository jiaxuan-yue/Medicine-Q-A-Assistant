"""系统启动后的基础数据初始化。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.chunk_repo import chunk_repo
from app.db.repositories.document_repo import document_repo
from app.db.repositories.user_repo import user_repo
from app.models.document import DocumentStatus
from app.models.graph_entity import GraphEntity
from app.models.role import RoleName
from app.services.chunking_service import chunking_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path to data dictionaries (resolved relative to project root)
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "dictionaries"

# ---------------------------------------------------------------------------
# Module-level dictionary data – loaded once at import / startup
# ---------------------------------------------------------------------------
symptom_synonyms: dict[str, list[str]] = {}
herb_aliases: dict[str, list[str]] = {}
formula_aliases: dict[str, list[str]] = {}


def _load_json(filename: str) -> dict[str, list[str]]:
    """Load a JSON dictionary file, returning {} on any error."""
    path = _DATA_DIR / filename
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded %d entries from %s", len(data), path)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load dictionary %s: %s", path, exc)
        return {}


def load_dictionaries() -> None:
    """Load all TCM dictionaries from JSON files into module-level variables."""
    global symptom_synonyms, herb_aliases, formula_aliases  # noqa: PLW0603
    symptom_synonyms = _load_json("symptom_synonyms.json")
    herb_aliases = _load_json("herb_aliases.json")
    formula_aliases = _load_json("formula_aliases.json")


# Eagerly load on import so other modules can reference the data immediately.
load_dictionaries()


DEMO_DOCUMENTS = [
    {
        "title": "失眠口苦辨证参考",
        "source": "demo_knowledge",
        "authority_score": 0.92,
        "content": (
            "失眠伴口苦、急躁易怒，多见肝火扰心或肝郁化火。"
            "辨证时需结合舌红、苔黄、脉弦数等表现，治疗上强调清肝泻火、宁心安神。"
        ),
    },
    {
        "title": "脾虚乏力调理要点",
        "source": "demo_knowledge",
        "authority_score": 0.88,
        "content": (
            "乏力、食欲不振、腹胀便溏常与脾气虚弱相关。"
            "临床多从健脾益气入手，并观察纳差、面色少华、舌淡苔白等信息。"
        ),
    },
    {
        "title": "咽痛咳嗽知识卡片",
        "source": "demo_knowledge",
        "authority_score": 0.8,
        "content": (
            "咽痛伴咳嗽时，应先区分风热犯肺、燥邪伤肺等不同病机。"
            "如伴发热、口渴、痰黄，可优先关注热象。"
        ),
    },
]

DEMO_GRAPH_ENTITIES = [
    ("失眠", "Symptom"),
    ("口苦", "Symptom"),
    ("易怒", "Symptom"),
    ("肝火扰心", "Syndrome"),
    ("气虚", "Syndrome"),
    ("脾虚", "Syndrome"),
]


class BootstrapService:
    async def initialize(self, db: AsyncSession) -> None:
        # Ensure dictionaries are loaded (idempotent)
        load_dictionaries()
        for role_name in RoleName:
            await user_repo.ensure_role(db, role_name)
        await self._seed_graph_entities(db)
 
    async def ensure_demo_documents(self, db: AsyncSession, uploaded_by: int) -> None:
        if not settings.ENABLE_DEMO_DATA:
            return
        if await document_repo.count_documents(db) > 0:
            return
        for item in DEMO_DOCUMENTS:
            document = await document_repo.create_document(
                db,
                title=item["title"],
                source=item["source"],
                file_path=f"demo://{item['title']}",
                authority_score=item["authority_score"],
                uploaded_by=uploaded_by,
                status=DocumentStatus.PUBLISHED,
            )
            chunks = chunking_service.chunk_text(item["content"])
            await chunk_repo.bulk_create_chunks(db, doc_id=document.doc_id, chunks=chunks)

    async def _seed_graph_entities(self, db: AsyncSession) -> None:
        existing_names = set((await db.scalars(select(GraphEntity.name))).all())
        for name, entity_type in DEMO_GRAPH_ENTITIES:
            if name in existing_names:
                continue
            db.add(GraphEntity(name=name, entity_type=entity_type, aliases=[], properties={}))
        await db.flush()


from app.core.config import settings

bootstrap_service = BootstrapService()
