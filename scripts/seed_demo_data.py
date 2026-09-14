#!/usr/bin/env python3
"""Memory Passport - Hackathon Demo Data Seeding Script.

Initializes an idempotent, verifiable, and safe demo environment for:
- Demo User (email: demo@memorypassport.ai, password: demo123456)
- 10 Natural Memories (preferences, facts, architecture, guidelines)
- Temporal Memory Supersession (Python 3.10 superseded by Python 3.12)
- Conflict Intelligence Candidates (work schedule vs urgent standup)
- Memory Relationship Graph (SUPERSEDES, RELEVANT_TO, CONTRADICTS)
- Audit Logs for Governance / Provenance
- Golden Evaluation Dataset with 5 realistic test cases
- 2 Executed Evaluation Runs with real IR metrics (Hit Rate, MRR, Precision)

Completely offline-capable: uses a deterministic embedding generator when
no external API key is provided.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add backend directory to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Ensure SDK is on sys.path if needed
SDK_DIR = REPO_ROOT / "sdk" / "python"
if str(SDK_DIR) not in sys.path:
    sys.path.insert(0, str(SDK_DIR))

# Ensure canonical database is used if not explicitly overridden
canonical_db = (BACKEND_DIR / "memory_passport.db").resolve()
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{canonical_db}"

import bcrypt
from app.models.base import Base
from app.models.evaluation import EvaluationCase, EvaluationDataset, EvaluationRun
from app.models.governance import AuditAction, AuditActorType, MemoryAuditLog
from app.models.memory import Memory
from app.models.memory_relationship import MemoryRelationship, RelationshipType
from app.models.user import User
from app.services.evaluation_service import EvaluationService
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_demo_data")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeterministicEmbeddingProvider:
    """Offline deterministic 1024-dimension embedding generator.

    Uses bag-of-words MD5 hashing projected to a 1024-d unit vector.
    Guarantees semantically related sentences share positive cosine similarity
    without requiring external API calls or network access.
    """

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    async def embed(self, text: str) -> list[float]:
        words = text.lower().split()
        vec = [0.0] * self.dim
        for w in words:
            for i in range(3):
                h = int(hashlib.md5(f"{w}_{i}".encode()).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 16) % 2 == 0 else -1.0
                vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            return [round(x / norm, 6) for x in vec]
        vec[0] = 1.0
        return vec


def _hash_password(plain_password: str) -> str:
    pwd_bytes = plain_password.encode()[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


DEMO_MEMORIES_DATA = [
    {
        "key": "role_and_stack",
        "content": "Senior Full-Stack AI Engineer specializing in Python, FastAPI, React, Next.js, and Vector Databases.",
        "memory_type": "identity",
        "tags": "profile,tech,backend,frontend,demo_seed",
        "importance": 0.95,
        "confidence": 1.0,
        "status": "active",
        "version": 1,
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "valid_until": None,
    },
    {
        "key": "editor_theme_preference",
        "content": "Prefers VS Code with dark modern theme, 2 spaces indentation, and strict TypeScript/Ruff linting.",
        "memory_type": "preference",
        "tags": "preference,editor,tooling,demo_seed",
        "importance": 0.80,
        "confidence": 1.0,
        "status": "active",
        "version": 1,
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "valid_until": None,
    },
    {
        "key": "primary_database",
        "content": "Memory Passport uses PostgreSQL with pgvector for production vector storage and SQLite for local development.",
        "memory_type": "context",
        "tags": "architecture,database,postgres,sqlite,demo_seed",
        "importance": 0.90,
        "confidence": 1.0,
        "status": "active",
        "version": 1,
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "valid_until": None,
    },
    {
        "key": "python_runtime_version_v1",
        "content": "Current active backend service runtime is Python 3.10 across all microservices.",
        "memory_type": "context",
        "tags": "runtime,python,version,superseded,demo_seed",
        "importance": 0.70,
        "confidence": 1.0,
        "status": "superseded",
        "version": 1,
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "valid_until": datetime(2026, 3, 1, tzinfo=timezone.utc),
        "superseded_by_key": "python_runtime_version_v2",
    },
    {
        "key": "python_runtime_version_v2",
        "content": "Upgraded backend runtime to Python 3.12 for performance improvements and native typing features.",
        "memory_type": "context",
        "tags": "runtime,python,version,active,demo_seed",
        "importance": 0.92,
        "confidence": 1.0,
        "status": "active",
        "version": 2,
        "valid_from": datetime(2026, 3, 1, tzinfo=timezone.utc),
        "valid_until": None,
    },
    {
        "key": "deployment_cloud_target",
        "content": "Deploy backend services on containerized Linux servers using Docker with automatic health checks and non-root users.",
        "memory_type": "context",
        "tags": "devops,docker,deployment,security,demo_seed",
        "importance": 0.85,
        "confidence": 1.0,
        "status": "active",
        "version": 1,
        "valid_from": datetime(2025, 6, 1, tzinfo=timezone.utc),
        "valid_until": None,
    },
    {
        "key": "work_schedule_preference",
        "content": "Prefers deep work focus time in the mornings from 9:00 AM to 12:00 PM without any team meetings.",
        "memory_type": "preference",
        "tags": "preference,work,schedule,focus,demo_seed",
        "importance": 0.85,
        "confidence": 1.0,
        "status": "active",
        "version": 1,
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "valid_until": None,
    },
    {
        "key": "client_meeting_availability",
        "content": "Available for urgent client standup syncs daily at 10:00 AM.",
        "memory_type": "preference",
        "tags": "conflict,schedule,meeting,demo_seed",
        "importance": 0.75,
        "confidence": 0.85,
        "status": "conflicted",
        "version": 1,
        "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "valid_until": None,
    },
    {
        "key": "agent_response_guideline",
        "content": "Always provide concise, actionable technical advice with code snippets before explaining theoretical principles.",
        "memory_type": "context",
        "tags": "guideline,agent,communication,style,demo_seed",
        "importance": 0.88,
        "confidence": 1.0,
        "status": "active",
        "version": 1,
        "valid_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "valid_until": None,
    },
    {
        "key": "hackathon_project_milestone",
        "content": "Complete Hackathon Phase 6 demo integration showing real-time memory retrieval and evaluation metrics.",
        "memory_type": "task",
        "tags": "project,hackathon,milestone,demo_seed",
        "importance": 0.90,
        "confidence": 1.0,
        "status": "active",
        "version": 1,
        "valid_from": datetime(2026, 3, 1, tzinfo=timezone.utc),
        "valid_until": None,
    },
]

DEMO_RELATIONSHIPS_DATA = [
    ("python_runtime_version_v2", "python_runtime_version_v1", RelationshipType.SUPERSEDES, 1.0),
    ("python_runtime_version_v2", "role_and_stack", RelationshipType.RELEVANT_TO, 0.9),
    ("deployment_cloud_target", "primary_database", RelationshipType.RELEVANT_TO, 0.85),
    ("client_meeting_availability", "work_schedule_preference", RelationshipType.CONTRADICTS, 0.95),
    ("agent_response_guideline", "role_and_stack", RelationshipType.RELEVANT_TO, 0.8),
]

DEMO_EVALUATION_CASES_DATA = [
    {
        "query": "What Python version is currently used in the backend services?",
        "expected_keys": ["python_runtime_version_v2"],
        "tags": "temporal,python,runtime",
    },
    {
        "query": "What are Alex's editor and tooling preferences?",
        "expected_keys": ["editor_theme_preference"],
        "tags": "preferences,tooling",
    },
    {
        "query": "What is the primary database used by Memory Passport?",
        "expected_keys": ["primary_database"],
        "tags": "architecture,database",
    },
    {
        "query": "What is Alex's preferred morning schedule for deep work?",
        "expected_keys": ["work_schedule_preference"],
        "tags": "schedule,work",
    },
    {
        "query": "What guidelines should the AI agent follow when answering?",
        "expected_keys": ["agent_response_guideline"],
        "tags": "guideline,agent",
    },
]


def _ensure_sqlite_columns(sync_conn) -> None:
    """Ensure all required columns exist on SQLite database tables."""
    from sqlalchemy import text

    # Check memories table
    res = sync_conn.execute(text("PRAGMA table_info(memories)"))
    mem_cols = {row[1] for row in res.fetchall()}
    if mem_cols:  # If table exists
        mem_col_defs = [
            ("raw_content", "TEXT DEFAULT ''"),
            ("memory_type", "VARCHAR(50) DEFAULT 'preference'"),
            ("importance", "FLOAT DEFAULT 0.5"),
            ("status", "VARCHAR(20) DEFAULT 'active'"),
            ("version", "INTEGER DEFAULT 1"),
            ("source_conversation_id", "VARCHAR(36)"),
            ("source_message_id", "VARCHAR(36)"),
            ("valid_from", "TIMESTAMP"),
            ("valid_until", "TIMESTAMP"),
            ("superseded_by_memory_id", "VARCHAR(36)"),
            ("embedding", "TEXT"),
        ]
        for col_name, col_def in mem_col_defs:
            if col_name not in mem_cols:
                logger.info("Migrating SQLite schema: adding memories.%s", col_name)
                sync_conn.execute(text(f"ALTER TABLE memories ADD COLUMN {col_name} {col_def}"))

        if "category" in mem_cols:
            sync_conn.execute(text("UPDATE memories SET memory_type = category WHERE category IS NOT NULL AND (memory_type IS NULL OR memory_type = 'preference')"))
            try:
                sync_conn.execute(text("DROP INDEX IF EXISTS ix_memories_category"))
                sync_conn.execute(text("ALTER TABLE memories DROP COLUMN category"))
            except (DBAPIError, SQLAlchemyError, OSError) as exc:
                logger.debug("Legacy column cleanup skipped: %s", exc)

    # Check users table
    res_u = sync_conn.execute(text("PRAGMA table_info(users)"))
    u_cols = {row[1] for row in res_u.fetchall()}
    if u_cols:
        if "wallet_address" not in u_cols:
            logger.info("Migrating SQLite schema: adding users.wallet_address")
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN wallet_address VARCHAR(42)"))
        if "wallet_bound_at" not in u_cols:
            logger.info("Migrating SQLite schema: adding users.wallet_bound_at")
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN wallet_bound_at TIMESTAMP"))


async def seed_demo_environment(
    db_path: Path | None = None,
    database_url: str | None = None,
) -> dict[str, object]:
    """Execute complete, idempotent seeding of the demo environment."""
    if database_url:
        resolved_url = database_url
    elif db_path:
        resolved_url = f"sqlite+aiosqlite:///{db_path.resolve()}"
    else:
        canonical_db = BACKEND_DIR / "memory_passport.db"
        resolved_url = os.environ.get("DATABASE_URL") or f"sqlite+aiosqlite:///{canonical_db.resolve()}"

    logger.info("Connecting to database: %s", resolved_url)
    engine = create_async_engine(resolved_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # 1. Ensure all schema tables and columns exist
    async with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            await conn.run_sync(_ensure_sqlite_columns)
        await conn.run_sync(Base.metadata.create_all)

    provider = DeterministicEmbeddingProvider()
    summary: dict[str, object] = {}

    async with session_factory() as db:
        # 2. Demo User Seed / Idempotent Fetch
        demo_email = "demo@memorypassport.ai"
        stmt = select(User).where(User.email == demo_email)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if user is None:
            user = User(
                id=str(uuid.uuid4()),
                email=demo_email,
                hashed_password=_hash_password("demo123456"),
                passport_id="mp_demo_hackathon",
                display_name="Demo User",
                wallet_address="0x71C2E63B48421882c7aE9D58E16503c403Be43F0",
                wallet_bound_at=_utcnow(),
            )
            db.add(user)
            await db.flush()
            logger.info("Created Demo User: %s (id=%s)", demo_email, user.id)
        else:
            user.display_name = "Demo User"
            user.passport_id = "mp_demo_hackathon"
            if not user.wallet_address:
                user.wallet_address = "0x71C2E63B48421882c7aE9D58E16503c403Be43F0"
                user.wallet_bound_at = _utcnow()
            await db.flush()
            logger.info("Reusing existing Demo User: %s (id=%s)", demo_email, user.id)

        user_id = user.id
        summary["user_id"] = user_id
        summary["user_email"] = user.email

        # 3. Memories Seed / Idempotent Update
        memory_map: dict[str, Memory] = {}
        stmt_mem = select(Memory).where(Memory.user_id == user_id)
        existing_mems = (await db.execute(stmt_mem)).scalars().all()
        existing_by_key = {m.key: m for m in existing_mems}

        for item in DEMO_MEMORIES_DATA:
            k = item["key"]
            embed_vec = await provider.embed(item["content"])
            embed_json_str = json.dumps(embed_vec)

            if k in existing_by_key:
                mem = existing_by_key[k]
                mem.content = item["content"]
                mem.raw_content = item["content"]
                mem.memory_type = item["memory_type"]
                mem.tags = item["tags"]
                mem.importance = item["importance"]
                mem.confidence = item["confidence"]
                mem.status = item["status"]
                mem.version = item["version"]
                mem.valid_from = item["valid_from"]
                mem.valid_until = item["valid_until"]
                mem.embedding = embed_vec
                mem.embedding_json = embed_json_str
            else:
                mem = Memory(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    key=k,
                    content=item["content"],
                    raw_content=item["content"],
                    memory_type=item["memory_type"],
                    tags=item["tags"],
                    importance=item["importance"],
                    confidence=item["confidence"],
                    status=item["status"],
                    version=item["version"],
                    valid_from=item["valid_from"],
                    valid_until=item["valid_until"],
                    embedding=embed_vec,
                    embedding_json=embed_json_str,
                    source="manual",
                )
                db.add(mem)

            memory_map[k] = mem

        await db.flush()

        # Link supersessions
        for item in DEMO_MEMORIES_DATA:
            sup_key = item.get("superseded_by_key")
            if sup_key and sup_key in memory_map:
                memory_map[item["key"]].superseded_by_memory_id = memory_map[sup_key].id

        await db.flush()
        summary["memories_count"] = len(memory_map)
        logger.info("Seeded/Updated %d demo memories", len(memory_map))

        # 4. Memory Relationships
        stmt_rel = select(MemoryRelationship).where(MemoryRelationship.user_id == user_id)
        existing_rels = (await db.execute(stmt_rel)).scalars().all()
        rel_signatures = {
            (r.source_memory_id, r.target_memory_id, r.relationship_type)
            for r in existing_rels
        }

        seeded_rels_count = len(existing_rels)
        for s_key, t_key, rel_type, conf in DEMO_RELATIONSHIPS_DATA:
            if s_key in memory_map and t_key in memory_map:
                s_id = memory_map[s_key].id
                t_id = memory_map[t_key].id
                sig = (s_id, t_id, rel_type.value if hasattr(rel_type, "value") else str(rel_type))
                if sig not in rel_signatures:
                    rel = MemoryRelationship(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        source_memory_id=s_id,
                        target_memory_id=t_id,
                        relationship_type=rel_type.value if hasattr(rel_type, "value") else str(rel_type),
                        confidence=conf,
                    )
                    db.add(rel)
                    rel_signatures.add(sig)
                    seeded_rels_count += 1

        await db.flush()
        summary["relationships_count"] = seeded_rels_count
        logger.info("Total %d memory relationships active", seeded_rels_count)

        # 5. Seed Audit Logs for Provenance / Explain Demo
        stmt_audit = select(MemoryAuditLog).where(MemoryAuditLog.user_id == user_id)
        existing_audits = (await db.execute(stmt_audit)).scalars().all()

        if not existing_audits:
            old_mem = memory_map.get("python_runtime_version_v1")
            new_mem = memory_map.get("python_runtime_version_v2")
            if old_mem and new_mem:
                db.add(
                    MemoryAuditLog(
                        id=str(uuid.uuid4()),
                        memory_id=old_mem.id,
                        user_id=user_id,
                        actor_type=AuditActorType.USER.value,
                        actor_id=user_id,
                        action=AuditAction.SUPERSEDE.value,
                        from_version=1,
                        to_version=2,
                        metadata_json=json.dumps({
                            "reason": "Upgraded runtime to Python 3.12 for modern typing support",
                            "superseded_by": new_mem.id,
                        }),
                    )
                )

            conflict_mem = memory_map.get("client_meeting_availability")
            if conflict_mem:
                db.add(
                    MemoryAuditLog(
                        id=str(uuid.uuid4()),
                        memory_id=conflict_mem.id,
                        user_id=user_id,
                        actor_type=AuditActorType.SYSTEM.value,
                        actor_id="conflict_detector",
                        action=AuditAction.CONFLICT_DETECTED.value,
                        from_version=1,
                        to_version=1,
                        metadata_json=json.dumps({
                            "conflicting_with_key": "work_schedule_preference",
                            "detected_overlap": "Morning focus hours vs 10:00 AM client standup",
                        }),
                    )
                )
            await db.flush()

        # 6. Evaluation Dataset & Cases
        ds_name = "Developer Profile & Tech Stack Golden Dataset"
        stmt_ds = select(EvaluationDataset).where(
            EvaluationDataset.user_id == user_id,
            EvaluationDataset.name == ds_name,
        )
        ds = (await db.execute(stmt_ds)).scalar_one_or_none()

        if ds is None:
            ds = EvaluationDataset(
                id=str(uuid.uuid4()),
                user_id=user_id,
                name=ds_name,
                description="Golden benchmark dataset for evaluating developer preferences, runtime, and tech stack retrieval.",
                is_system=False,
            )
            db.add(ds)
            await db.flush()
            logger.info("Created Evaluation Dataset: %s", ds.id)

        dataset_id = ds.id
        summary["dataset_id"] = dataset_id

        # Seed Cases
        stmt_cases = select(EvaluationCase).where(EvaluationCase.dataset_id == dataset_id)
        existing_cases = {c.query: c for c in (await db.execute(stmt_cases)).scalars().all()}

        for c_data in DEMO_EVALUATION_CASES_DATA:
            q = c_data["query"]
            exp_ids = [memory_map[k].id for k in c_data["expected_keys"] if k in memory_map]
            exp_rel = {mid: 1.0 for mid in exp_ids}

            if q in existing_cases:
                c_obj = existing_cases[q]
                c_obj.expected_memory_ids_json = json.dumps(exp_ids)
                c_obj.expected_relevance_json = json.dumps(exp_rel)
                c_obj.tags = c_data["tags"]
            else:
                c_obj = EvaluationCase(
                    id=str(uuid.uuid4()),
                    dataset_id=dataset_id,
                    user_id=user_id,
                    query=q,
                    expected_memory_ids_json=json.dumps(exp_ids),
                    expected_relevance_json=json.dumps(exp_rel),
                    tags=c_data["tags"],
                )
                db.add(c_obj)

        await db.flush()
        cases_count = len((await db.execute(stmt_cases)).scalars().all())
        summary["cases_count"] = cases_count
        logger.info("Seeded %d evaluation test cases", cases_count)

        # 7. Seed 2 Completed Evaluation Runs with real IR metrics
        stmt_runs = select(EvaluationRun).where(
            EvaluationRun.dataset_id == dataset_id,
            EvaluationRun.status == "completed",
        )
        existing_runs = (await db.execute(stmt_runs)).scalars().all()

        if len(existing_runs) < 2:
            logger.info("Executing Evaluation Runs to populate benchmark metrics...")
            run_1 = await EvaluationService.run_evaluation(
                db,
                user_id=user_id,
                dataset_id=dataset_id,
                name="Baseline Keyword Retrieval",
                retrieval_config={
                    "search_mode": "keyword",
                    "top_k": 5,
                    "status": "active",
                },
                app_version="1.10.1",
                embedding_provider=provider,
            )
            logger.info("Completed Run 1: %s (metrics=%s)", run_1.id, run_1.summary_metrics_json)

            run_2 = await EvaluationService.run_evaluation(
                db,
                user_id=user_id,
                dataset_id=dataset_id,
                name="Enhanced Context Retrieval (Hybrid)",
                retrieval_config={
                    "search_mode": "retrieve",
                    "top_k": 5,
                    "status": "active",
                    "graph_enabled": True,
                    "min_relevance": 0.0,
                },
                app_version="1.10.1",
                embedding_provider=provider,
            )
            logger.info("Completed Run 2: %s (metrics=%s)", run_2.id, run_2.summary_metrics_json)

        stmt_runs_final = select(EvaluationRun).where(EvaluationRun.dataset_id == dataset_id)
        runs_final = (await db.execute(stmt_runs_final)).scalars().all()
        summary["runs_count"] = len(runs_final)

        await db.commit()

    await engine.dispose()
    logger.info("Demo Data Seeding completed successfully.")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Memory Passport Demo Data")
    parser.add_argument("--db-path", type=Path, default=None, help="Custom path to SQLite database")
    parser.add_argument("--database-url", type=str, default=None, help="Custom database URL")
    args = parser.parse_args()

    results = asyncio.run(seed_demo_environment(db_path=args.db_path, database_url=args.database_url))

    print("\n" + "=" * 60)
    print(" [PHASE 6.1] MEMORY PASSPORT DEMO SEED COMPLETED")
    print("=" * 60)
    print(f" Demo User:      {results.get('user_email')}")
    print(" Password:       demo123456")
    print(f" User ID:        {results.get('user_id')}")
    print(f" Memories:       {results.get('memories_count')} items (Active, Superseded, Conflicted)")
    print(f" Relationships:  {results.get('relationships_count')} graph edges")
    print(f" Evaluation:     1 Dataset, {results.get('cases_count')} Cases, {results.get('runs_count')} Runs")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
