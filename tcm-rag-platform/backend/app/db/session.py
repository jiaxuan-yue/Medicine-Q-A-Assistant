"""
异步数据库引擎和会话工厂。
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _get_engine_kwargs() -> dict:
    kwargs = {
        "echo": settings.DEBUG,
        "pool_pre_ping": True,
    }
    if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite+aiosqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
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
        kwargs["connect_args"] = {"check_same_thread": False}
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
