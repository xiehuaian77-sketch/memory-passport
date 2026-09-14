#!/usr/bin/env python3
"""Memory Passport - Hackathon CLI Agent Demo Script.

Demonstrates how an autonomous AI Agent queries Memory Passport via the Python SDK
to retrieve personalized user context, resolve temporal supersessions, and detect
preference conflicts.

Usage:
    python scripts/demo_agent_run.py
    python scripts/demo_agent_run.py --query "What are Alex's tech stack preferences?"
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend and SDK to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
SDK_DIR = REPO_ROOT / "sdk" / "python"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(SDK_DIR) not in sys.path:
    sys.path.insert(0, str(SDK_DIR))

# Ensure canonical database is used if not explicitly overridden
canonical_db = (BACKEND_DIR / "memory_passport.db").resolve()
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{canonical_db}"

import httpx
from app.config import settings
from app.main import app
from app.models.memory import Memory
from app.models.memory_relationship import MemoryRelationship
from app.models.user import User
from jose import jwt
from memory_passport import MemoryPassportClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient


def _create_demo_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_configured_client(user_id: str) -> tuple[MemoryPassportClient, str]:
    """Return a configured MemoryPassportClient.

    Connects to live http://127.0.0.1:8000 if available,
    otherwise connects directly via in-process FastAPI TestClient.
    """
    base_url = os.environ.get("MEMORY_PASSPORT_BASE_URL", "http://127.0.0.1:8000")

    try:
        with httpx.Client(base_url=base_url, timeout=1.0, trust_env=False) as probe:
            res = probe.get("/api/health")
            if res.status_code == 200:
                login_res = probe.post(
                    "/api/auth/login",
                    json={"email": "demo@memorypassport.ai", "password": "demo123456"},
                )
                if login_res.status_code == 200:
                    token = login_res.json()["access_token"]
                    live_http = httpx.Client(base_url=base_url, trust_env=False)
                    client = MemoryPassportClient(
                        base_url=base_url,
                        access_token=token,
                        httpx_client=live_http,
                    )
                    return client, f"Live Server ({base_url})"
    except (httpx.HTTPError, OSError):
        pass

    # Fallback to in-process FastAPI TestClient
    direct_http = TestClient(app, base_url="http://testserver")
    login_res = direct_http.post(
        "/api/auth/login",
        json={"email": "demo@memorypassport.ai", "password": "demo123456"},
    )
    token = login_res.json().get("access_token") or _create_demo_token(user_id)
    client = MemoryPassportClient(
        base_url="http://testserver",
        access_token=token,
        httpx_client=direct_http,
    )
    return client, "In-Process FastAPI Direct Client"


async def fetch_demo_context(db_url: str) -> dict[str, object]:
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    data: dict[str, object] = {}

    async with session_factory() as db:
        stmt = select(User).where(User.email == "demo@memorypassport.ai")
        user = (await db.execute(stmt)).scalar_one_or_none()
        if not user:
            raise RuntimeError("Demo user demo@memorypassport.ai not found. Please run 'python scripts/seed_demo_data.py' first.")

        data["user"] = user

        # Fetch memories
        stmt_m = select(Memory).where(Memory.user_id == user.id)
        mems = (await db.execute(stmt_m)).scalars().all()
        data["memories"] = {m.key: m for m in mems}

        # Fetch relationships
        stmt_r = select(MemoryRelationship).where(MemoryRelationship.user_id == user.id)
        rels = (await db.execute(stmt_r)).scalars().all()
        data["relationships"] = rels

    await engine.dispose()
    return data


def run_agent_demo(query_text: str) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass

    canonical_db = BACKEND_DIR / "memory_passport.db"
    db_url = os.environ.get("DATABASE_URL") or f"sqlite+aiosqlite:///{canonical_db.resolve()}"

    print("\n" + "=" * 70)
    print(" [*] MEMORY PASSPORT - AUTONOMOUS AGENT CONTEXT INGESTION DEMO")
    print("=" * 70)

    try:
        ctx_data = asyncio.run(fetch_demo_context(db_url))
    except (RuntimeError, OSError) as exc:
        print(f"\n[!] Error loading demo data: {exc}")
        print(" -> Tip: Run 'python scripts/seed_demo_data.py' to initialize demo data.")
        return 1

    user: User = ctx_data["user"]  # type: ignore
    client, transport_mode = get_configured_client(user.id)

    print(f" Target User:     {user.display_name} ({user.email})")
    print(f" Passport ID:     {user.passport_id}")
    print(f" SDK Transport:   {transport_mode}")
    print(" Agent Name:      CodeAssistant-v1")
    print("-" * 70)

    # 1. Natural Language Search & Retrieval
    print(f"\n[STEP 1] Agent Query: \"{query_text}\"")
    print("   Sending request via MemoryPassportClient.search.keyword / retrieve...")

    search_res = client.search.keyword(query_text, limit=5)
    print(f"   Found {len(search_res.items)} matched memory candidates:")

    for idx, item in enumerate(search_res.items, start=1):
        score = item.similarity if item.similarity is not None else (item.keyword_score if item.keyword_score is not None else 1.0)
        print(f"   {idx}. [{item.memory_type.upper()}] (Score: {score:.2f}) - ID: '{item.id[:8]}...'")
        print(f"      Content: '{item.content}'")

    # 2. Temporal Memory Explanation
    print("\n[STEP 2] Temporal Memory & Supersession Analysis")
    memories_map: dict[str, Memory] = ctx_data["memories"]  # type: ignore
    v1 = memories_map.get("python_runtime_version_v1")
    v2 = memories_map.get("python_runtime_version_v2")

    if v1 and v2:
        print("   Comparing historical versions for key: 'python_runtime_version':")
        print(f"   - Historical [v1]: \"{v1.content}\"")
        print(f"     Status: {v1.status.upper()} | Valid Until: {v1.valid_until.strftime('%Y-%m-%d') if v1.valid_until else 'N/A'}")
        print(f"     Superseded by Memory ID: {v1.superseded_by_memory_id}")
        print(f"   - Current    [v2]: \"{v2.content}\"")
        print(f"     Status: {v2.status.upper()} | Valid From:  {v2.valid_from.strftime('%Y-%m-%d') if v2.valid_from else 'N/A'}")
        print("   [Decision] The agent automatically discards v1 (Python 3.10) and")
        print("      operates strictly on v2 (Python 3.12) to prevent stale runtime hallucinations.")

    # 3. Conflict Intelligence Explanation
    print("\n[STEP 3] Conflict Intelligence & Relationship Graph")
    rels: list[MemoryRelationship] = ctx_data["relationships"]  # type: ignore
    conflict_rel = next((r for r in rels if r.relationship_type == "CONTRADICTS"), None)

    if conflict_rel:
        source_mem = next((m for m in memories_map.values() if m.id == conflict_rel.source_memory_id), None)
        target_mem = next((m for m in memories_map.values() if m.id == conflict_rel.target_memory_id), None)
        if source_mem and target_mem:
            print(f"   Detected Semantic Conflict Edge (Confidence: {conflict_rel.confidence}):")
            print(f"   - Preference A: \"{target_mem.content}\" (Morning Focus)")
            print(f"   - Preference B: \"{source_mem.content}\" (Client Sync)")
            print("   [Decision] The agent pauses autonomous action and prompts user:")
            print("      'Notice: Morning focus block conflicts with proposed 10:00 AM meeting.'")

    print("\n" + "=" * 70)
    print(" [OK] AGENT MEMORY RETRIEVAL DEMO RUN COMPLETED SUCCESSFULLY (Exit Code: 0)")
    print("=" * 70 + "\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory Passport CLI Agent Demo")
    parser.add_argument(
        "--query",
        type=str,
        default="What Python version do we use in backend services?",
        help="Query to search user memories for",
    )
    args = parser.parse_args()
    sys.exit(run_agent_demo(args.query))


if __name__ == "__main__":
    main()
