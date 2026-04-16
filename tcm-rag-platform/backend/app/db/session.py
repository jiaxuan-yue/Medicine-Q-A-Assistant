"""
异步数据库引擎和会话工厂。
"""

from contextlib import contextmanager

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _get_engine_kwargs() -> dict:
    kwargs = {
        "echo": settings.DEBUG,
        "pool_pre_ping": True,
    }
    if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite+aiosqlite"):
        kwargs["connect_args"] = {
            "check_same_thread": False,
            "timeout": 30,
        }
        # SQLite 在本地调试阶段容易被索引器/多个轻量读取阻塞；
        # NullPool + WAL + busy_timeout 能显著降低 "database is locked" 概率。
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    return kwargs

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    **_get_engine_kwargs(),
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session():
    """Yield an async DB session (for use outside FastAPI DI)."""
    async with async_session_factory() as session:
        yield session


# ── Synchronous session for Celery workers ──────────────────

def _get_sync_engine_kwargs() -> dict:
    kwargs = {
        "echo": settings.DEBUG,
        "pool_pre_ping": True,
    }
    uri = settings.SQLALCHEMY_SYNC_DATABASE_URI
    if uri.startswith("sqlite://"):
        kwargs["connect_args"] = {
            "check_same_thread": False,
            "timeout": 30,
        }
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
    return kwargs

sync_engine = create_engine(
    settings.SQLALCHEMY_SYNC_DATABASE_URI,
    **_get_sync_engine_kwargs(),
)

sync_session_factory = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
)


def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=30000;")
    finally:
        cursor.close()


if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite+aiosqlite"):
    event.listen(engine.sync_engine, "connect", _configure_sqlite_connection)

if settings.SQLALCHEMY_SYNC_DATABASE_URI.startswith("sqlite://"):
    event.listen(sync_engine, "connect", _configure_sqlite_connection)


@contextmanager
def get_sync_session():
    """Yield a synchronous DB session (for Celery tasks)."""
    session = sync_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def init_db() -> None:
    """初始化数据库表结构。"""
    from app import models  # noqa: F401
    from app.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_chat_persistence_columns)


def _ensure_chat_persistence_columns(sync_conn) -> None:
    inspector = inspect(sync_conn)

    def ensure_columns(table_name: str, column_ddls: dict[str, str]) -> None:
        if table_name not in inspector.get_table_names():
            return
        existing_columns = {item["name"] for item in inspector.get_columns(table_name)}
        for column_name, ddl in column_ddls.items():
            if column_name in existing_columns:
                continue
            sync_conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")

    ensure_columns(
        "sessions",
        {
            "case_profile_id": "case_profile_id INTEGER NULL",
            "case_profile_name": "case_profile_name VARCHAR(128) NULL",
            "case_profile_summary": "case_profile_summary TEXT NULL",
            "followup_state": "followup_state JSON NULL",
        },
    )
    ensure_columns(
        "messages",
        {
            "kind": "kind VARCHAR(32) NULL DEFAULT 'answer'",
        },
    )
    if "messages" in inspector.get_table_names():
        sync_conn.exec_driver_sql("UPDATE messages SET kind = 'answer' WHERE kind IS NULL")
