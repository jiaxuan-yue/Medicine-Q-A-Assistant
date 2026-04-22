"""
FastAPI 应用入口 — 中医药智能知识服务平台。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import get_logger, setup_logging, trace_id_ctx
from app.core.middleware import RequestLoggingMiddleware, SmartRateLimitMiddleware, TraceIDMiddleware
from app.db.session import async_session_factory, init_db
from app.integrations.es_client import es_client
from app.integrations.llm_client import llm_client
from app.integrations.neo4j_client import neo4j_client
from app.integrations.redis_client import close_redis, get_redis_client, init_redis
from app.integrations.vector_store import vector_store
from app.services.bootstrap_service import bootstrap_service

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动 → 初始化连接 → yield → 清理。"""

    # ── 启动 ──────────────────────────────────────────────
    setup_logging(level="DEBUG" if settings.DEBUG else "INFO")
    logger.info("%s v%s 正在启动", settings.APP_NAME, "1.0.0")
    llm_status = llm_client.get_config_status()
    log_method = logger.info if llm_status["api_key_status"] == "configured" else logger.warning
    log_method(
        "LLM 配置状态: provider=%s, api_key_status=%s, api_key=%s, chat_model=%s, rewrite_model=%s, embedding_model=%s, reranker_model=%s, timeout=%ss",
        llm_status["provider"],
        llm_status["api_key_status"],
        llm_status["api_key_masked"],
        llm_status["chat_model"],
        llm_status["rewrite_model"],
        llm_status["embedding_model"],
        llm_status["reranker_model"],
        llm_status["timeout_seconds"],
    )

    await init_db()
    async with async_session_factory() as session:
        await bootstrap_service.initialize(session)
        await session.commit()
    logger.info("数据库初始化完成: %s", settings.SQLALCHEMY_DATABASE_URI)

    await init_redis()

    logger.info("数据库 DSN: %s", settings.SQLALCHEMY_DATABASE_URI)

    # Elasticsearch
    try:
        await es_client.init()
    except Exception as exc:
        logger.warning("Elasticsearch 初始化失败，继续以降级模式运行: %s", exc)

    # FAISS vector store — load persisted index if exists
    try:
        vector_store.load()
        logger.info("FAISS 向量索引就绪 (%d 向量)", vector_store.size)
    except Exception as exc:
        logger.warning("FAISS 初始化失败，继续以降级模式运行: %s", exc)

    # Neo4j
    if settings.GRAPH_RECALL_ENABLED:
        try:
            await neo4j_client.init()
        except Exception as exc:
            logger.warning("Neo4j 初始化失败，继续以降级模式运行: %s", exc)
    else:
        logger.info("知识图谱召回已关闭，跳过 Neo4j 初始化")

    # Store references on app.state for access in request handlers
    app.state.redis_client = get_redis_client()
    app.state.es_client = es_client
    app.state.vector_store = vector_store
    app.state.neo4j_client = neo4j_client

    logger.info("%s 启动完成", settings.APP_NAME)

    yield

    # ── 关闭 ──────────────────────────────────────────────
    await es_client.close()
    if settings.GRAPH_RECALL_ENABLED:
        await neo4j_client.close()
    await close_redis()
    logger.info("%s 已停止", settings.APP_NAME)


# ── 创建 FastAPI 实例 ────────────────────────────────────

app = FastAPI(
    title="中医药智能知识服务平台",
    version="1.0.0",
    description="基于 RAG 的中医药古籍知识问答与检索平台",
    lifespan=lifespan,
)

# ── 注册中间件（顺序：先注册的后执行） ───────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SmartRateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TraceIDMiddleware)

# ── 注册全局异常处理器 ───────────────────────────────────
register_exception_handlers(app)

# ── 注册 API 路由 ────────────────────────────────────────
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
Path(settings.MEDIA_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR), name="media")


# ── 健康检查 ─────────────────────────────────────────────

@app.get("/health", tags=["健康检查"])
async def health_check():
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "app": settings.APP_NAME,
            "version": "1.0.0",
            "trace_id": trace_id_ctx.get("-"),
        },
    }
