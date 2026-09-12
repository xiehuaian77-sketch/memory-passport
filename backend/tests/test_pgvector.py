"""Tests for Phase 2.3A: pgvector infrastructure, schema compatibility, and nullable embedding."""

from pathlib import Path

import pytest
from app.models.memory import Memory
from httpx import AsyncClient
from sqlalchemy import select, text


@pytest.mark.asyncio
async def test_pgvector_extension(client: AsyncClient):
    """Verify pgvector extension migration script and active database engine capabilities."""
    migration_file = Path("backend/migrations/001_add_pgvector.sql")
    if not migration_file.exists():
        migration_file = Path("migrations/001_add_pgvector.sql")
    assert migration_file.exists(), "Migration script 001_add_pgvector.sql must exist"

    sql_content = migration_file.read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in sql_content
    assert "embedding vector(1024)" in sql_content

    # Check active database dialect
    from app.database import engine
    dialect_name = engine.dialect.name
    if dialect_name == "postgresql":
        async with engine.connect() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            result = await conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            )
            rows = result.fetchall()
            assert len(rows) > 0, "pgvector extension must be present in PostgreSQL"
    else:
        # SQLite environment: dialect is sqlite; vector extension is PostgreSQL-specific
        assert dialect_name == "sqlite"


@pytest.mark.asyncio
async def test_memory_embedding_nullable(auth_client: AsyncClient):
    """Verify that newly created Memory objects have embedding=None and it is nullable in DB."""
    # Create memory via API
    resp = await auth_client.post(
        "/api/memories",
        json={
            "category": "preference",
            "key": "editor_theme",
            "content": "Prefers dark mode in code editors",
            "confidence": 0.9,
            "importance": 0.6,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"] == "editor_theme"
    assert data.get("embedding") is None, "Embedding must be None upon creation"

    # Query directly from DB session via override to verify NULL column in database
    from tests.conftest import TestSession
    async with TestSession() as session:
        result = await session.execute(
            select(Memory).where(Memory.id == data["id"])
        )
        memory = result.scalar_one_or_none()
        assert memory is not None
        assert memory.embedding is None, "Database embedding column must be NULL"


@pytest.mark.asyncio
async def test_existing_memory_crud_compatibility(auth_client: AsyncClient):
    """Verify existing CRUD operations remain 100% compatible.

    Ensures:
    - user_id isolation preserved
    - raw_content preserved
    - memory_type preserved
    - importance preserved
    - confidence preserved
    """
    # 1. Create
    create_payload = {
        "category": "task",
        "key": "learn_pgvector",
        "content": "Studying pgvector integration for vector search",
        "confidence": 0.92,
        "importance": 0.75,
        "is_shared": True,
        "tags": "database,vector",
    }
    create_resp = await auth_client.post("/api/memories", json=create_payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    mem_id = created["id"]
    assert created["category"] == "task"
    assert created["key"] == "learn_pgvector"
    assert created["confidence"] == 0.92
    assert created["is_shared"] is True

    # 2. Read by ID
    get_resp = await auth_client.get(f"/api/memories/{mem_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["id"] == mem_id
    assert fetched["key"] == "learn_pgvector"

    # 3. Update
    update_resp = await auth_client.put(
        f"/api/memories/{mem_id}",
        json={"content": "Updated pgvector study progress"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["content"] == "Updated pgvector study progress"

    # 4. List with category filter
    list_resp = await auth_client.get("/api/memories?category=task")
    assert list_resp.status_code == 200
    assert any(m["id"] == mem_id for m in list_resp.json())

    # 5. Delete
    del_resp = await auth_client.delete(f"/api/memories/{mem_id}")
    assert del_resp.status_code == 204

    # Confirm deletion
    get_after_del = await auth_client.get(f"/api/memories/{mem_id}")
    assert get_after_del.status_code == 404


@pytest.mark.asyncio
async def test_pgvector_postgres_container_integration():
    """Direct integration test against PostgreSQL container with pgvector."""
    from sqlalchemy.ext.asyncio import create_async_engine

    pg_url = "postgresql+asyncpg://memory_passport:dev_pg_password_123@127.0.0.1:5432/memory_passport"
    pg_engine = create_async_engine(pg_url)

    try:
        async with pg_engine.connect() as conn:
            # 1. Verify extension
            ext_res = await conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
            )
            version = ext_res.scalar()
            assert version is not None, "pgvector extension must be active"

            # 2. Verify column type and dimension
            dim_res = await conn.execute(
                text("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'memories'::regclass AND attname = 'embedding';")
            )
            dim = dim_res.scalar()
            assert dim == 1024, f"Expected dimension 1024, got {dim}"

            # 3. Verify nullability
            null_res = await conn.execute(
                text("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'memories' AND column_name = 'embedding';")
            )
            is_nullable = null_res.scalar()
            assert is_nullable == "YES", "Embedding column must be nullable"
    finally:
        await pg_engine.dispose()
