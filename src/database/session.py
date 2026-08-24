"""
Database session management (both Async and Sync).
Supports PostgreSQL (asyncpg) and SQLite (aiosqlite).
"""
from typing import AsyncGenerator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.core.config import settings

DB_URL = settings.DATABASE_URL

# ── Derivar URL síncrona ──────────────────────────────────────────────────────
if DB_URL.startswith("sqlite+aiosqlite://"):
    SYNC_URL = DB_URL.replace("sqlite+aiosqlite://", "sqlite://")
    _connect_args = {"check_same_thread": False}
else:
    SYNC_URL = DB_URL.replace("postgresql+asyncpg://", "postgresql://")
    _connect_args = {}

# ── Sync engine (Celery / scripts) ───────────────────────────────────────────
sync_engine = create_engine(SYNC_URL, echo=False, connect_args=_connect_args)

if SYNC_URL.startswith("sqlite://"):
    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

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
_async_kwargs = {}
if DB_URL.startswith("sqlite+aiosqlite://"):
    _async_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(DB_URL, echo=False, **_async_kwargs)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
