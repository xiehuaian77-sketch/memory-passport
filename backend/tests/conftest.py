"""Pytest configuration and shared fixtures."""

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test env vars BEFORE importing app modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_memory_passport.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["LLM_API_KEY"] = ""
os.environ["EMBEDDING_API_KEY"] = ""
os.environ["MCP_API_KEY"] = "test-mcp-key"

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

from app.models.base import Base  # noqa: E402


# Use a single event loop for all tests
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///./test_memory_passport.db",
    connect_args={"check_same_thread": False},
)
TestSession = async_sessionmaker(TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after."""
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """Register a user and return an authenticated client."""
    resp = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "testpass123",
        "display_name": "Test User",
    })
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
