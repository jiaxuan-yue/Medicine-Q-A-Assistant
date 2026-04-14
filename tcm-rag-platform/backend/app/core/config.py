"""
应用配置 — 基于 pydantic-settings，从 .env 文件和环境变量读取。
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SQLITE_PATH = _BASE_DIR / "data" / "tcm_rag.db"


class Settings(BaseSettings):
    # ── 应用 ──────────────────────────────────────────────
    APP_NAME: str = "TCM-RAG-Platform"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    BASE_DIR: str = str(_BASE_DIR)
    DATA_DIR: str = str(_BASE_DIR / "data")
    RAW_DOCUMENTS_DIR: str = str(_BASE_DIR / "data" / "raw" / "uploads")
    PROCESSED_DOCUMENTS_DIR: str = str(_BASE_DIR / "data" / "processed")
    ENABLE_DEMO_DATA: bool = True
    DATABASE_URL: str | None = None

    # ── MySQL ─────────────────────────────────────────────
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "tcm_rag"

    # ── Redis ─────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Elasticsearch ─────────────────────────────────────
    ES_HOSTS: list[str] = ["http://localhost:9200"]
    ES_INDEX_PREFIX: str = "tcm"

    # ── Neo4j ─────────────────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""

    # ── MinIO ─────────────────────────────────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = "tcm-documents"

    # ── DashScope LLM ────────────────────────────────────
    DASHSCOPE_API_KEY: str = ""
    LLM_MODEL: str = "qwen-max"
    LLM_REWRITE_MODEL: str = "qwen-plus"
    LLM_TIMEOUT: int = 15
    EMBEDDING_MODEL: str = "text-embedding-v3"
    EMBEDDING_DIM: int = 1024
    RERANKER_MODEL: str = "gte-rerank"

    # ── 检索参数 ──────────────────────────────────────────
    SPARSE_TOP_K: int = 20
    DENSE_TOP_K: int = 20
    GRAPH_TOP_K: int = 15
    FUSION_TOP_K: int = 20
    RERANK_K: int = 5
    RRF_K: int = 60
    GRAPH_MAX_HOPS: int = 2
    RETRIEVAL_TIMEOUT: float = 1.0

    # ── 特性开关 ──────────────────────────────────────────
    QUERY_REWRITE_ENABLED: bool = True
    GRAPH_RECALL_ENABLED: bool = True
    RERANKER_ENABLED: bool = True

    # ── JWT 安全 ──────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── 多轮对话 ──────────────────────────────────────────
    HISTORY_WINDOW_SIZE: int = 5
    HISTORY_SUMMARY_INTERVAL: int = 5

    # ── 限流 ──────────────────────────────────────────────
    RATE_LIMIT_USER: int = 60       # req/min
    RATE_LIMIT_QA: int = 10         # req/min
    RATE_LIMIT_ADMIN: int = 120     # req/min

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _coerce_debug(cls, value):
        """Accept common env strings such as release/debug in addition to bools."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "dev", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return value

    # ── 计算属性 ──────────────────────────────────────────
    @property
    def MYSQL_DSN(self) -> str:
        return (
            f"mysql+asyncmy://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def MYSQL_SYNC_DSN(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH}"

    @property
    def SQLALCHEMY_SYNC_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL.replace("+aiosqlite", "")
        return f"sqlite:///{DEFAULT_SQLITE_PATH}"

    model_config = SettingsConfigDict(
        env_file=str(_BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
