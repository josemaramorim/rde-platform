"""
Database session management (both Async and Sync).
Supports PostgreSQL (asyncpg) and SQLite (aiosqlite).
"""
from typing import AsyncGenerator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from src.core.config import settings

DB_URL = settings.DATABASE_URL

# ── Derivar URL síncrona ──────────────────────────────────────────────────────
if DB_URL.startswith("sqlite+aiosqlite://"):
    SYNC_URL = DB_URL.replace("sqlite+aiosqlite://", "sqlite://")
else:
    SYNC_URL = DB_URL.replace("postgresql+asyncpg://", "postgresql://")

# ── Sync engine (Celery / scripts) ───────────────────────────────────────────
sync_kwargs: dict = {"echo": False}
if SYNC_URL.startswith("sqlite://"):
    sync_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    sync_kwargs["poolclass"] = NullPool
else:
    sync_kwargs["pool_size"] = 20
    sync_kwargs["max_overflow"] = 40
    sync_kwargs["pool_pre_ping"] = True

sync_engine = create_engine(SYNC_URL, **sync_kwargs)

if SYNC_URL.startswith("sqlite://"):
    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        try:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        except Exception:
            pass

SessionLocal = sessionmaker(
    bind=sync_engine, autocommit=False, autoflush=False
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Async engine (FastAPI) ────────────────────────────────────────────────────
_async_kwargs: dict = {"echo": False}
if DB_URL.startswith("sqlite+aiosqlite://"):
    _async_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    _async_kwargs["poolclass"] = NullPool
else:
    _async_kwargs["pool_size"] = 20
    _async_kwargs["max_overflow"] = 40
    _async_kwargs["pool_pre_ping"] = True

engine = create_async_engine(DB_URL, **_async_kwargs)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


get_async_db = get_async_session

