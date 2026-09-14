"""Tests for Phase 6.1 Demo Data Seeding System.

Verifies:
- Idempotent execution of seed_demo_environment()
- Demo user presence and credentials verification
- 10 natural memories with proper lifecycle statuses
- Temporal supersession linkage (v1 -> v2)
- Graph relationship edges (SUPERSEDES, RELEVANT_TO, CONTRADICTS)
- Evaluation dataset, test cases, and executed runs with IR metrics
- Zero secrets leakage
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure repo root and backend are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app.models.evaluation import EvaluationCase, EvaluationDataset, EvaluationRun
from app.models.memory import Memory
from app.models.memory_relationship import MemoryRelationship
from app.models.user import User
from seed_demo_data import seed_demo_environment


@pytest.mark.asyncio
async def test_demo_seed_idempotency_and_completeness(tmp_path: Path) -> None:
    """Test full seeding workflow on an isolated database and assert idempotency."""
    test_db_path = tmp_path / "test_demo_isolated.db"
    db_url = f"sqlite+aiosqlite:///{test_db_path.resolve()}"

    # Run 1: Initial Seed
    res_1 = await seed_demo_environment(database_url=db_url)
    assert res_1["user_email"] == "demo@memorypassport.ai"
    assert res_1["memories_count"] == 10
    assert res_1["relationships_count"] == 5
    assert res_1["cases_count"] == 5
    assert res_1["runs_count"] == 2

    # Verify DB directly
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as db:
        # 1. User verification
        user_stmt = select(User).where(User.email == "demo@memorypassport.ai")
        user = (await db.execute(user_stmt)).scalar_one_or_none()
        assert user is not None
        assert user.display_name == "Demo User"
        assert user.passport_id == "mp_demo_hackathon"
        assert user.wallet_address == "0x71C2E63B48421882c7aE9D58E16503c403Be43F0"

        # 2. Memories verification
        mem_stmt = select(Memory).where(Memory.user_id == user.id)
        memories = (await db.execute(mem_stmt)).scalars().all()
        assert len(memories) == 10

        mem_by_key = {m.key: m for m in memories}
        assert "python_runtime_version_v1" in mem_by_key
        assert "python_runtime_version_v2" in mem_by_key

        v1 = mem_by_key["python_runtime_version_v1"]
        v2 = mem_by_key["python_runtime_version_v2"]
        assert v1.status == "superseded"
        assert v2.status == "active"
        assert v1.superseded_by_memory_id == v2.id

        conflict_mem = mem_by_key["client_meeting_availability"]
        assert conflict_mem.status == "conflicted"

        # 3. Relationships verification
        rel_stmt = select(MemoryRelationship).where(MemoryRelationship.user_id == user.id)
        rels = (await db.execute(rel_stmt)).scalars().all()
        assert len(rels) == 5

        rel_types = {r.relationship_type for r in rels}
        assert "SUPERSEDES" in rel_types
        assert "RELEVANT_TO" in rel_types
        assert "CONTRADICTS" in rel_types

        # 4. Evaluation verification
        ds_stmt = select(EvaluationDataset).where(EvaluationDataset.user_id == user.id)
        ds = (await db.execute(ds_stmt)).scalar_one_or_none()
        assert ds is not None

        case_stmt = select(EvaluationCase).where(EvaluationCase.dataset_id == ds.id)
        cases = (await db.execute(case_stmt)).scalars().all()
        assert len(cases) == 5

        run_stmt = select(EvaluationRun).where(EvaluationRun.dataset_id == ds.id)
        runs = (await db.execute(run_stmt)).scalars().all()
        assert len(runs) == 2
        for r in runs:
            assert r.status == "completed"
            assert r.summary_metrics_json is not None
            assert "total_cases" in r.summary_metrics_json

    await engine.dispose()

    # Run 2: Idempotent Reseed on same DB
    res_2 = await seed_demo_environment(database_url=db_url)
    assert res_2["user_email"] == "demo@memorypassport.ai"
    assert res_2["memories_count"] == 10
    assert res_2["relationships_count"] == 5
    assert res_2["cases_count"] == 5
    assert res_2["runs_count"] == 2

    # Verify counts did not inflate
    engine_2 = create_async_engine(db_url, echo=False)
    session_factory_2 = async_sessionmaker(engine_2, expire_on_commit=False, class_=AsyncSession)
    async with session_factory_2() as db:
        user_count = (await db.execute(select(func.count(User.id)).where(User.email == "demo@memorypassport.ai"))).scalar()
        mem_count = (await db.execute(select(func.count(Memory.id)).where(Memory.user_id == user.id))).scalar()
        rel_count = (await db.execute(select(func.count(MemoryRelationship.id)).where(MemoryRelationship.user_id == user.id))).scalar()
        run_count = (await db.execute(select(func.count(EvaluationRun.id)).where(EvaluationRun.dataset_id == ds.id))).scalar()

        assert user_count == 1
        assert mem_count == 10
        assert rel_count == 5
        assert run_count == 2

    await engine_2.dispose()


@pytest.mark.asyncio
async def test_demo_seed_no_secrets_leaked() -> None:
    """Verify script files contain no live API secrets."""
    forbidden_tokens = ["sk-" + "proj-", "sk-" + "live-", "sk-" + "ant-", "ghp_"]
    target_files = [
        SCRIPTS_DIR / "seed_demo_data.py",
        SCRIPTS_DIR / "demo_agent_run.py",
    ]

    for tf in target_files:
        if tf.exists():
            text = tf.read_text(encoding="utf-8")
            for tok in forbidden_tokens:
                assert tok not in text, f"Forbidden secret token {tok} found in {tf}"
