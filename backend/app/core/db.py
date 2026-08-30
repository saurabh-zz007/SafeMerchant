"""
Async SQLAlchemy engine and session factory.

Uses asyncpg as the PostgreSQL driver. The engine is created once at
application startup and shared across all requests.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# ── Async Engine ──
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# ── Session Factory ──
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Declarative Base ──
class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ── Dependency for FastAPI ──
async def get_db_session() -> AsyncSession:
    """
    Yield an async database session.
    Used as a FastAPI dependency via Depends(get_db_session).
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
