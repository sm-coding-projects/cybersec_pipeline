from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _create_engine(url: str | None = None) -> Any:
    """Create the async engine. Separated for testability."""
    db_url = url or settings.database_url
    kwargs: dict[str, Any] = {
        "echo": False,
        "pool_pre_ping": True,
    }
    # SQLite doesn't support pool_size / max_overflow
    if "sqlite" not in db_url:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    return create_async_engine(db_url, **kwargs)


engine = _create_engine()

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
