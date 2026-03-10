import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.base import Base
from app.models.user import User


# Use an in-memory SQLite database for tests.
# SQLite async requires aiosqlite.
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create all tables before each test and drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Override the get_db dependency with the test database session."""
    async with test_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a raw async session for test setup/teardown."""
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a standard test user in the database."""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("testpassword123"),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin test user in the database."""
    user = User(
        username="adminuser",
        email="admin@example.com",
        hashed_password=hash_password("adminpassword123"),
        is_active=True,
        is_admin=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict[str, str]:
    """Return Authorization headers with a valid JWT for the test user."""
    token = create_access_token(user_id=test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_auth_headers(admin_user: User) -> dict[str, str]:
    """Return Authorization headers with a valid JWT for the admin user."""
    token = create_access_token(user_id=admin_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_docker():
    """Mock DockerManager so tests don't need real containers."""
    with patch("app.services.docker_manager.DockerManager") as mock_cls:
        instance = mock_cls.return_value
        instance.exec_in_container = AsyncMock(return_value=(0, "mock output"))
        instance.get_container_status.return_value = {
            "name": "test-container",
            "status": "running",
            "running": True,
            "uptime": "2d 4h",
        }
        instance.get_all_tool_statuses.return_value = [
            {"name": "theharvester", "status": "running", "running": True},
            {"name": "nmap-scanner", "status": "running", "running": True},
            {"name": "nuclei", "status": "running", "running": True},
            {"name": "zap", "status": "running", "running": True},
        ]
        yield instance
