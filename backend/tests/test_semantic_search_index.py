"""Phase 2.3E: pgvector HNSW index, migration idempotency, and scale performance tests."""

import time
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.memory import Memory
from app.models.user import User

PG_URL = "postgresql+asyncpg://memory_passport:dev_pg_password_123@127.0.0.1:5432/memory_passport"


def get_pg_engine():
    return create_async_engine(PG_URL)


# ────────────────────── 1: HNSW Index Exists ──────────────────────

@pytest.mark.asyncio
async def test_hnsw_index_exists():
    """Verify that the HNSW index on memories.embedding exists in PostgreSQL."""
    engine = get_pg_engine()
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE tablename = 'memories' AND indexname = 'ix_memories_embedding_hnsw';"
                )
            )
            row = result.fetchone()
            assert row is not None, "HNSW index 'ix_memories_embedding_hnsw' must exist on memories table"
            assert "hnsw" in row.indexdef.lower(), "Index definition must specify USING hnsw"
            assert "vector_cosine_ops" in row.indexdef.lower(), "Index must use vector_cosine_ops"
    finally:
        await engine.dispose()


# ────────────────────── 2: HNSW Access Method & Opclass ──────────────────────

@pytest.mark.asyncio
async def test_hnsw_index_cosine_ops():
    """Verify HNSW index metadata in pg_am and pg_opclass."""
    engine = get_pg_engine()
    try:
        async with engine.connect() as conn:
            sql = """
            SELECT c.relname AS index_name,
                   a.amname AS access_method,
                   op.opcname AS operator_class
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indexrelid
            JOIN pg_am a ON a.oid = c.relam
            JOIN pg_opclass op ON op.oid = i.indclass[0]
            WHERE c.relname = 'ix_memories_embedding_hnsw';
            """
            result = await conn.execute(text(sql))
            row = result.fetchone()
            assert row is not None, "Index metadata query must return a row"
            assert row.access_method == "hnsw", f"Expected access method 'hnsw', got '{row.access_method}'"
            assert row.operator_class == "vector_cosine_ops", f"Expected 'vector_cosine_ops', got '{row.operator_class}'"
    finally:
        await engine.dispose()


# ────────────────────── 3: Migration Idempotency ──────────────────────

@pytest.mark.asyncio
async def test_hnsw_migration_idempotent():
    """Executing migration 002_add_hnsw_index.sql multiple times must not raise errors."""
    migration_path = Path("migrations/002_add_hnsw_index.sql")
    if not migration_path.exists():
        migration_path = Path("backend/migrations/002_add_hnsw_index.sql")
    assert migration_path.exists(), "Migration file 002_add_hnsw_index.sql must exist"

    sql_content = migration_path.read_text(encoding="utf-8-sig")
    engine = get_pg_engine()
    try:
        async with engine.begin() as conn:
            # First execution
            await conn.execute(text(sql_content))
            # Repeated execution (must be idempotent)
            await conn.execute(text(sql_content))
    finally:
        await engine.dispose()


# ────────────────────── 4: Data Integrity Verification ──────────────────────

@pytest.mark.asyncio
async def test_hnsw_does_not_modify_memory_data():
    """Applying migration must preserve existing memory count, content, and embeddings."""
    engine = get_pg_engine()
    PgSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    test_user_id = None
    test_mem_id = None

    try:
        async with PgSession() as session:
            # 1. Create a baseline memory
            user = User(
                email="integrity_test_user@example.com",
                hashed_password="dummy_password",
                passport_id="mp_integrity_001",
                display_name="Integrity User",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            test_user_id = user.id

            sample_vec = [0.01 * (i % 50) for i in range(1024)]
            mem = Memory(
                user_id=test_user_id,
                memory_type="context",
                key="integrity_key",
                content="Data integrity preservation test string.",
                embedding=sample_vec,
            )
            session.add(mem)
            await session.commit()
            test_mem_id = mem.id

        # 2. Record data before re-running migration
        async with engine.connect() as conn:
            cnt_before = (await conn.execute(text("SELECT count(*) FROM memories"))).scalar()
            row_before = (
                await conn.execute(
                    text("SELECT content, embedding FROM memories WHERE id = :id"),
                    {"id": test_mem_id},
                )
            ).fetchone()

        # 3. Execute migration
        migration_path = Path("migrations/002_add_hnsw_index.sql")
        if not migration_path.exists():
            migration_path = Path("backend/migrations/002_add_hnsw_index.sql")
        sql_content = migration_path.read_text(encoding="utf-8-sig")
        async with engine.begin() as conn:
            await conn.execute(text(sql_content))

        # 4. Record data after migration
        async with engine.connect() as conn:
            cnt_after = (await conn.execute(text("SELECT count(*) FROM memories"))).scalar()
            row_after = (
                await conn.execute(
                    text("SELECT content, embedding FROM memories WHERE id = :id"),
                    {"id": test_mem_id},
                )
            ).fetchone()

        # Assert zero change to data
        assert cnt_before == cnt_after, "Total memories count must be unchanged"
        assert row_before.content == row_after.content, "Memory content must be unchanged"
        assert row_before.embedding == row_after.embedding, "Memory embedding vector must be unchanged"

    finally:
        async with PgSession() as session:
            if test_mem_id:
                await session.execute(text("DELETE FROM memories WHERE id = :id"), {"id": test_mem_id})
            if test_user_id:
                await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": test_user_id})
            await session.commit()
        await engine.dispose()


# ────────────────────── 5: Query Plan & EXPLAIN Analysis ──────────────────────

@pytest.mark.asyncio
async def test_hnsw_query_plan_analysis():
    """Verify that EXPLAIN (ANALYZE, BUFFERS) runs cleanly on semantic search query."""
    engine = get_pg_engine()
    dummy_query_vector = "[" + ",".join(str(0.01) for _ in range(1024)) + "]"
    try:
        async with engine.connect() as conn:
            explain_sql = f"""
            EXPLAIN (ANALYZE, BUFFERS)
            SELECT id, content, memory_type, importance, confidence, created_at, updated_at,
                   (embedding <=> '{dummy_query_vector}'::vector) AS distance
            FROM memories
            WHERE user_id = 'test_user_id' AND embedding IS NOT NULL
            ORDER BY embedding <=> '{dummy_query_vector}'::vector ASC
            LIMIT 10;
            """
            result = await conn.execute(text(explain_sql))
            rows = result.fetchall()
            plan_text = "\n".join(r[0] for r in rows)
            assert "Limit" in plan_text, "Query plan must include Limit"
            assert "Execution Time" in plan_text, "Analyze must include execution time"
    finally:
        await engine.dispose()


# ────────────────────── 6: Semantic Search with HNSW Regression ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_with_hnsw_regression():
    """Verify semantic search logic in PostgreSQL with HNSW index active."""
    engine = get_pg_engine()
    PgSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    test_user_id = None
    created_ids = []

    try:
        async with PgSession() as session:
            user = User(
                email="hnsw_regression_user@example.com",
                hashed_password="pw",
                passport_id="mp_hnsw_reg_001",
                display_name="HNSW Reg User",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            test_user_id = user.id

            # Create test vectors
            target_vec = [1.0 / (1024 ** 0.5)] * 1024
            orthogonal_vec = [0.0] * 1024
            orthogonal_vec[0] = 1.0

            m1 = Memory(
                user_id=test_user_id,
                memory_type="preference",
                key="ai",
                content="Target match for AI Agent search",
                embedding=target_vec,
            )
            m2 = Memory(
                user_id=test_user_id,
                memory_type="preference",
                key="other",
                content="Unrelated memory",
                embedding=orthogonal_vec,
            )
            session.add_all([m1, m2])
            await session.commit()
            created_ids.extend([m1.id, m2.id])

            # Query via repository semantic_search (uses PostgreSQL native <=> operator)
            from app.repositories import memory_repo
            results = await memory_repo.semantic_search(
                session,
                user_id=test_user_id,
                query_vector=target_vec,
                limit=10,
            )
            assert len(results) == 2
            top_mem, top_sim = results[0]
            assert top_mem.key == "ai"
            assert top_sim > results[1][1], "Exact match must have higher similarity"
            assert top_sim == pytest.approx(1.0, abs=0.01)

    finally:
        async with PgSession() as session:
            for mid in created_ids:
                await session.execute(text("DELETE FROM memories WHERE id = :id"), {"id": mid})
            if test_user_id:
                await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": test_user_id})
            await session.commit()
        await engine.dispose()


# ────────────────────── 7: 1000 Memories Scale & Performance Test ──────────────────────

@pytest.mark.asyncio
async def test_hnsw_scale_performance_1000_memories():
    """Scale test with 1000 memories using pre-computed vectors.

    Measures query latency, verifies Top-K correctness, and cleanly removes all test rows.
    """
    engine = get_pg_engine()
    PgSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    test_user_id = None
    total_records = 1000

    try:
        async with PgSession() as session:
            # 1. Create dedicated user
            user = User(
                email="scale_perf_user@example.com",
                hashed_password="hashed_pw",
                passport_id="mp_scale_1000",
                display_name="Scale User",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            test_user_id = user.id

            # 2. Bulk insert 1000 memories with valid 1024-dim vectors
            # Target memory with unique direction
            target_direction = [0.0] * 1024
            target_direction[42] = 1.0

            memories_batch = [
                Memory(
                    user_id=test_user_id,
                    memory_type="task",
                    key="target_item",
                    content="Specific target item to retrieve among 1000 records",
                    embedding=target_direction,
                )
            ]

            # 999 background records with varied orthogonal/pseudo-random vectors
            for i in range(1, total_records):
                vec = [0.0] * 1024
                # Spread values across dimensions
                dim_idx = i % 1024
                if dim_idx == 42:
                    dim_idx = 43  # avoid exact collision with target
                vec[dim_idx] = 1.0

                memories_batch.append(
                    Memory(
                        user_id=test_user_id,
                        memory_type="context",
                        key=f"item_{i}",
                        content=f"Background context record #{i}",
                        embedding=vec,
                    )
                )

            session.add_all(memories_batch)
            await session.commit()

            # Confirm 1000 records created for this user
            count_res = await session.execute(
                text("SELECT count(*) FROM memories WHERE user_id = :uid"),
                {"uid": test_user_id},
            )
            assert count_res.scalar() == total_records

            # 3. Perform Semantic Search for Top-K=5 and measure latency
            from app.repositories import memory_repo

            start_time = time.perf_counter()
            results = await memory_repo.semantic_search(
                session,
                user_id=test_user_id,
                query_vector=target_direction,
                limit=5,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            # 4. Verify results
            assert len(results) == 5, f"Expected 5 Top-K items, got {len(results)}"
            top_mem, top_score = results[0]
            assert top_mem.key == "target_item", "Top result must be the exact target item"
            assert top_score == pytest.approx(1.0, abs=0.01), "Target match similarity should be ~1.0"

            print(f"\n[PERF METRIC] 1000 memories query latency: {elapsed_ms:.2f} ms")

    finally:
        # 5. Full cleanup
        async with PgSession() as session:
            if test_user_id:
                await session.execute(
                    text("DELETE FROM memories WHERE user_id = :uid"),
                    {"uid": test_user_id},
                )
                await session.execute(
                    text("DELETE FROM users WHERE id = :uid"),
                    {"uid": test_user_id},
                )
                await session.commit()

            # Verify zero residual test records
            if test_user_id:
                verify_res = await session.execute(
                    text("SELECT count(*) FROM memories WHERE user_id = :uid"),
                    {"uid": test_user_id},
                )
                assert verify_res.scalar() == 0, "No scale test memories must remain"

        await engine.dispose()
