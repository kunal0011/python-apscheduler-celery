"""
Pytest Configuration and Fixtures

Shared fixtures for unit and integration tests.
"""

import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.config import settings
from app.db.base import Base
from app.api.deps import get_db, get_redis


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create test database and session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def mock_redis() -> MagicMock:
    """Create mock Redis client."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.exists = AsyncMock(return_value=0)
    mock.ping = AsyncMock(return_value=True)
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def test_client(test_db: AsyncSession, mock_redis: MagicMock) -> Generator:
    """Create test client with overridden dependencies."""

    async def override_get_db():
        yield test_db

    async def override_get_redis():
        yield mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(test_db: AsyncSession, mock_redis: MagicMock) -> AsyncGenerator:
    """Create async test client."""

    async def override_get_db():
        yield test_db

    async def override_get_redis():
        yield mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_job_data() -> dict:
    """Sample job creation data."""
    return {
        "name": "test-job",
        "description": "Test job description",
        "trigger_type": "interval",
        "trigger_config": {"seconds": 60},
        "task_name": "example_task",
        "task_args": [],
        "task_kwargs": {"key": "value"},
    }


@pytest.fixture
def sample_task_data() -> dict:
    """Sample task submission data."""
    return {
        "task_name": "example_task",
        "args": [],
        "kwargs": {"order_id": "123"},
        "idempotency_key": "test-key-123",
    }
