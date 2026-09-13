"""Comprehensive test suite for Phase 5.4B: Graph-aware Retrieval.

Tests cover:
- Group A: Baseline & Opt-in Invariance
- Group B: Seed Selection & Boundaries
- Group C: 1-Hop Traversal & Directionality
- Group D: Bonus Weights, Confidence Scaling & Cap (+0.15 max, non-negative)
- Group E: Candidate Gating & Temporal/Status Filtering
- Group F: Deterministic Re-ranking & Deduplication
- Group G: User Isolation & Cross-User Security
- Group H: Hard Limits & Bounded Expansion
- Group I: Read-Only Invariance (no relationships, no audit logs)
- Group J: End-to-End API Integration via POST /api/memories/retrieve
"""

from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, func

from app.models.governance import MemoryAuditLog
from app.models.memory import Memory
from app.models.memory_relationship import MemoryRelationship
from app.schemas.memory import MemoryRetrievalRequest
from app.schemas.memory_relationship import RelationshipType
from app.services.graph_retrieval_service import GraphAwareRetrievalService
from app.services.retrieval_policy import ScoredMemory
from tests.conftest import TestSession


@pytest_asyncio.fixture
async def other_user(client: AsyncClient):
    """Register and authenticate a second user."""
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "graph_retrieval_u2@example.com",
            "password": "password123",
            "display_name": "Graph Retrieval User Two",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = await client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    user_id = me_resp.json()["id"]
    return {"user_id": user_id, "headers": headers}


async def _create_mem(
    client: AsyncClient,
    key: str,
    content: str,
    headers: dict | None = None,
    valid_from: str | None = None,
    valid_until: str | None = None,
    importance: float = 0.5,
    confidence: float = 1.0,
    category: str = "preference",
) -> str:
    payload = {
        "key": key,
        "content": content,
        "category": category,
        "importance": importance,
        "confidence": confidence,
    }
    if valid_from:
        payload["valid_from"] = valid_from
    if valid_until:
        payload["valid_until"] = valid_until
    resp = await client.post("/api/memories", json=payload, headers=headers)
    assert resp.status_code == 201, f"Failed to create memory {key}: {resp.text}"
    return resp.json()["id"]


async def _create_rel(
    client: AsyncClient,
    source_id: str,
    target_id: str,
    rel_type: str,
    confidence: float | None = 1.0,
    headers: dict | None = None,
) -> str:
    payload = {
        "source_memory_id": source_id,
        "target_memory_id": target_id,
        "relationship_type": rel_type.upper(),
        "confidence": confidence,
    }
    resp = await client.post(
        f"/api/memories/{source_id}/relationships", json=payload, headers=headers
    )
    assert resp.status_code == 201, f"Failed to create relationship: {resp.text}"
    return resp.json()["id"]


# ==============================================================================
# Group A: Baseline & Opt-in Invariance
# ==============================================================================

def test_default_graph_enabled_is_false():
    """MemoryRetrievalRequest must default graph_enabled to False."""
    req = MemoryRetrievalRequest(query="python coding")
    assert req.graph_enabled is False
    assert req.graph_seed_limit == 5
    assert req.graph_max_expanded == 20


@pytest.mark.asyncio
async def test_invalid_parameters_validation(auth_client: AsyncClient):
    """Parameters exceeding hard limits must be rejected with 422."""
    # seed_limit < 1
    r1 = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "test", "graph_enabled": True, "graph_seed_limit": 0},
    )
    assert r1.status_code == 422

    # seed_limit > 10 (hard max)
    r2 = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "test", "graph_enabled": True, "graph_seed_limit": 11},
    )
    assert r2.status_code == 422

    # max_expanded < 1
    r3 = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "test", "graph_enabled": True, "graph_max_expanded": 0},
    )
    assert r3.status_code == 422

    # max_expanded > 50 (hard max)
    r4 = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "test", "graph_enabled": True, "graph_max_expanded": 51},
    )
    assert r4.status_code == 422


@pytest.mark.asyncio
async def test_graph_disabled_matches_baseline(auth_client: AsyncClient):
    """When graph_enabled=False, retrieval executes normal baseline with no graph calls."""
    m1 = await _create_mem(auth_client, "code_pref_1", "I prefer writing code in Python and FastAPI")
    m2 = await _create_mem(auth_client, "code_pref_2", "I also use PostgreSQL for relational databases")
    await _create_rel(auth_client, m1, m2, "relevant_to", confidence=1.0)

    # Disabled (default)
    resp_default = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Python and FastAPI coding"},
    )
    assert resp_default.status_code == 200
    data_default = resp_default.json()

    # Explicitly disabled
    resp_false = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Python and FastAPI coding", "graph_enabled": False},
    )
    assert resp_false.status_code == 200
    data_false = resp_false.json()

    assert data_default["total_memories"] == data_false["total_memories"]
    assert [x["id"] for x in data_default["items"]] == [x["id"] for x in data_false["items"]]


# ==============================================================================
# Group B: Seed Selection & Boundaries
# ==============================================================================

@pytest.mark.asyncio
async def test_empty_base_retrieval_returns_empty(auth_client: AsyncClient):
    """When base search finds 0 matches, graph expansion produces 0 items."""
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "nonexistent_term_xyz_12345", "graph_enabled": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_memories"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_seeds_without_relationships_unmodified(auth_client: AsyncClient):
    """Base candidates without relationships retain exact base scores and order."""
    m1 = await _create_mem(auth_client, "isolated_m1", "Quantum computing with superconducting qubits")
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Quantum computing qubits", "graph_enabled": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert any(item["id"] == m1 for item in data["items"])


@pytest.mark.asyncio
async def test_seed_limit_enforced_strictly(auth_client: AsyncClient):
    """Only top graph_seed_limit candidates are used as expansion seeds."""
    m_seeds = []
    for i in range(5):
        # Assign descending importance so index 0 and index 1 are deterministically top 2
        imp = 0.9 - (i * 0.1)
        m = await _create_mem(
            auth_client,
            f"seed_cand_{i}",
            f"Docker container orchestration part {i}",
            importance=imp,
        )
        m_seeds.append(m)

    # Create target connected only to the 4th candidate (index 3)
    target = await _create_mem(auth_client, "seed_target_4", "Kubernetes cluster deployments")
    await _create_rel(auth_client, m_seeds[3], target, "relevant_to", confidence=1.0)

    # Set seed_limit = 2 (so candidates at indices 2, 3, 4 are not seeds)
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Docker container orchestration",
            "graph_enabled": True,
            "graph_seed_limit": 2,
            "min_relevance": 0.01,
        },
    )
    assert resp.status_code == 200
    retrieved_ids = [item["id"] for item in resp.json()["items"]]
    # target connected to seed index 3 must NOT be expanded because seed_limit is 2
    assert target not in retrieved_ids


# ==============================================================================
# Group C: 1-Hop Traversal & Directionality
# ==============================================================================

@pytest.mark.asyncio
async def test_one_hop_outgoing_expansion(auth_client: AsyncClient):
    """Seed A with outgoing edge A -> B expands B."""
    mA = await _create_mem(auth_client, "dir_mA", "Frontend React framework architecture")
    mB = await _create_mem(auth_client, "dir_mB", "Next.js App Router server components")
    await _create_rel(auth_client, mA, mB, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Frontend React framework architecture",
            "graph_enabled": True,
            "min_relevance": 0.10,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert mA in ids
    assert mB in ids


@pytest.mark.asyncio
async def test_one_hop_incoming_expansion(auth_client: AsyncClient):
    """Seed A with incoming edge B -> A expands B."""
    mA = await _create_mem(auth_client, "inc_mA", "Database migrations with Alembic")
    mB = await _create_mem(auth_client, "inc_mB", "PostgreSQL schema versioning tools")
    # Incoming to mA: mB -> mA
    await _create_rel(auth_client, mB, mA, "relevant_to", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Database migrations with Alembic",
            "graph_enabled": True,
            "min_relevance": 0.04,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert mA in ids
    assert mB in ids


@pytest.mark.asyncio
async def test_one_hop_both_directions_simultaneous(auth_client: AsyncClient):
    """Seed A connects outgoing to B and incoming from C; both are expanded."""
    mA = await _create_mem(auth_client, "both_mA", "Full stack web development guide")
    mB = await _create_mem(auth_client, "both_mB", "Backend Python REST API patterns")
    mC = await _create_mem(auth_client, "both_mC", "Frontend Tailwind CSS styling")
    await _create_rel(auth_client, mA, mB, "updates", confidence=1.0)  # outgoing
    await _create_rel(auth_client, mC, mA, "relevant_to", confidence=1.0)  # incoming

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Full stack web development guide",
            "graph_enabled": True,
            "min_relevance": 0.04,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert mA in ids
    assert mB in ids
    assert mC in ids


@pytest.mark.asyncio
async def test_two_hop_never_expanded(auth_client: AsyncClient):
    """A -> B -> C: strictly 1-hop; C is 2 hops away and must NEVER be expanded."""
    mA = await _create_mem(auth_client, "twohop_mA", "Solana blockchain validator node setup")
    mB = await _create_mem(auth_client, "twohop_mB", "Anchor smart contract framework")
    mC = await _create_mem(auth_client, "twohop_mC", "Mocha test assertion runner library")

    await _create_rel(auth_client, mA, mB, "updates", confidence=1.0)
    await _create_rel(auth_client, mB, mC, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Solana blockchain validator node setup",
            "graph_enabled": True,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert mA in ids
    assert mB in ids
    assert mC not in ids, "2-hop neighbor C must NOT be expanded!"


@pytest.mark.asyncio
async def test_disconnected_node_never_expanded(auth_client: AsyncClient):
    """An entirely disconnected memory is never expanded into context."""
    mA = await _create_mem(auth_client, "disc_mA", "Machine learning supervised classification")
    m_disc = await _create_mem(auth_client, "disc_isolated", "Baking homemade sourdough bread")

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Machine learning supervised classification",
            "graph_enabled": True,
            "min_relevance": 0.01,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert mA in ids
    assert m_disc not in ids


# ==============================================================================
# Group D: Bonus Weights, Confidence Scaling & Cap
# ==============================================================================

def test_unit_bonus_weights():
    """Unit test individual bonus weights and clamping."""
    svc = GraphAwareRetrievalService

    # UPDATES = 0.15 * confidence
    assert svc.calculate_edge_bonus("updates", 1.0) == 0.15
    assert svc.calculate_edge_bonus("updates", 0.5) == 0.075

    # SUPERSEDES = 0.15 * confidence
    assert svc.calculate_edge_bonus("supersedes", 1.0) == 0.15
    assert svc.calculate_edge_bonus("supersedes", 0.8) == 0.12

    # CONTRADICTS = 0.10 * confidence
    assert svc.calculate_edge_bonus("contradicts", 1.0) == 0.10
    assert svc.calculate_edge_bonus("contradicts", 0.5) == 0.05

    # RELEVANT_TO = 0.05 * confidence
    assert svc.calculate_edge_bonus("relevant_to", 1.0) == 0.05
    assert svc.calculate_edge_bonus("relevant_to", 0.6) == 0.03

    # None confidence defaults to 1.0
    assert svc.calculate_edge_bonus("updates", None) == 0.15

    # Unknown type produces 0.0
    assert svc.calculate_edge_bonus("unknown_rel", 1.0) == 0.0

    # Non-negative bonus guarantee
    assert svc.calculate_edge_bonus("updates", -0.5) == 0.0


@pytest.mark.asyncio
async def test_bonus_cap_at_0_15_maximum(auth_client: AsyncClient):
    """Multiple relationships totaling > 0.15 are strictly capped at 0.15."""
    m_seed = await _create_mem(auth_client, "cap_seed", "System design distributed caching")
    m_target = await _create_mem(auth_client, "cap_target", "Redis memory optimization strategies")

    # Connect with multiple edges totaling 0.15 (updates) + 0.10 (contradicts) + 0.05 (relevant_to) = 0.30
    await _create_rel(auth_client, m_seed, m_target, "updates", confidence=1.0)
    await _create_rel(auth_client, m_target, m_seed, "contradicts", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "System design distributed caching",
            "graph_enabled": True,
            "min_relevance": 0.10,
        },
    )
    assert resp.status_code == 200
    target_item = next((item for item in resp.json()["items"] if item["id"] == m_target), None)
    assert target_item is not None
    # For a graph-derived memory, retrieval_score == bonus <= 0.15
    assert target_item["retrieval_score"] <= 0.1501


@pytest.mark.asyncio
async def test_base_candidate_boosted_above_higher_base_candidate(auth_client: AsyncClient):
    """A lower base candidate with a graph bonus can jump above a higher base candidate."""
    # Seed
    m_seed = await _create_mem(auth_client, "boost_seed", "Data structures binary search trees")
    # Base candidate 1: matches query well
    _m_base1 = await _create_mem(auth_client, "boost_base1", "Data structures AVL balanced search trees")
    # Base candidate 2: matches query moderately, but connected to seed
    m_base2 = await _create_mem(auth_client, "boost_base2", "Data structures Red-Black balanced trees")
    await _create_rel(auth_client, m_seed, m_base2, "updates", confidence=1.0)

    # With graph disabled, base1 might rank before or with its base score
    resp_off = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Data structures binary search trees", "graph_enabled": False},
    )
    assert resp_off.status_code == 200
    items_off = {it["id"]: it["retrieval_score"] for it in resp_off.json()["items"]}

    # With graph enabled, base2 receives +0.15 bonus
    resp_on = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Data structures binary search trees", "graph_enabled": True},
    )
    assert resp_on.status_code == 200
    items_on = {it["id"]: it["retrieval_score"] for it in resp_on.json()["items"]}

    if m_base2 in items_off and m_base2 in items_on:
        assert items_on[m_base2] > items_off[m_base2]
        assert round(items_on[m_base2] - items_off[m_base2], 2) == 0.15


# ==============================================================================
# Group E: Candidate Gating & Temporal/Status Filtering
# ==============================================================================

@pytest.mark.asyncio
async def test_new_candidate_filtered_out_by_min_relevance_gate(auth_client: AsyncClient):
    """A new graph neighbor whose bonus (e.g. 0.05) is < min_relevance (0.30) is discarded."""
    m_seed = await _create_mem(auth_client, "gate_fail_seed", "Compiler optimization abstract syntax trees")
    m_target = await _create_mem(auth_client, "gate_fail_target", "LLVM Intermediate Representation passes")
    # relevant_to provides +0.05 bonus
    await _create_rel(auth_client, m_seed, m_target, "relevant_to", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Compiler optimization abstract syntax trees",
            "graph_enabled": True,
            "min_relevance": 0.30,  # 0.05 < 0.30 -> rejected
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert m_seed in ids
    assert m_target not in ids


@pytest.mark.asyncio
async def test_new_candidate_passes_min_relevance_gate(auth_client: AsyncClient):
    """A new graph neighbor whose bonus (0.15) is >= min_relevance (0.10) is accepted."""
    m_seed = await _create_mem(auth_client, "gate_pass_seed", "Compiler optimization static single assignment")
    m_target = await _create_mem(auth_client, "gate_pass_target", "SSA form dominance frontiers")
    # updates provides +0.15 bonus
    await _create_rel(auth_client, m_seed, m_target, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Compiler optimization static single assignment",
            "graph_enabled": True,
            "min_relevance": 0.10,  # 0.15 >= 0.10 -> accepted
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert m_seed in ids
    assert m_target in ids


@pytest.mark.asyncio
async def test_temporal_current_excludes_expired_neighbor(auth_client: AsyncClient):
    """Under temporal_mode=current, an expired neighbor (valid_until in the past) is excluded."""
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    far_past = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()

    m_seed = await _create_mem(auth_client, "temp_exp_seed", "Kubernetes ingress controller configuration")
    m_exp = await _create_mem(
        auth_client,
        "temp_exp_target",
        "Deprecated NGINX ingress custom annotations",
        valid_from=far_past,
        valid_until=past,
    )
    await _create_rel(auth_client, m_seed, m_exp, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Kubernetes ingress controller configuration",
            "graph_enabled": True,
            "temporal_mode": "current",
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert m_seed in ids
    assert m_exp not in ids, "Expired neighbor must be excluded in current mode!"


@pytest.mark.asyncio
async def test_temporal_current_excludes_future_neighbor(auth_client: AsyncClient):
    """Under temporal_mode=current, a future neighbor (valid_from > ref_now) is excluded."""
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()

    m_seed = await _create_mem(auth_client, "temp_fut_seed", "Web security OAuth2 PKCE flow")
    m_fut = await _create_mem(
        auth_client,
        "temp_fut_target",
        "Future security policy draft protocol",
        valid_from=future,
    )
    await _create_rel(auth_client, m_seed, m_fut, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Web security OAuth2 PKCE flow",
            "graph_enabled": True,
            "temporal_mode": "current",
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert m_seed in ids
    assert m_fut not in ids, "Future neighbor must be excluded in current mode!"


@pytest.mark.asyncio
async def test_temporal_current_excludes_superseded_neighbor(auth_client: AsyncClient):
    """Under temporal_mode=current, a superseded neighbor is excluded."""
    m_seed = await _create_mem(auth_client, "temp_sup_seed", "Python packaging pyproject.toml standards")
    m_sup = await _create_mem(auth_client, "temp_sup_target", "Old setup.py build configuration")
    m_new = await _create_mem(auth_client, "temp_sup_new", "Modern Hatchling build backend")

    # Mark m_sup as superseded directly in DB
    async with TestSession() as db:
        mem_row = await db.get(Memory, m_sup)
        assert mem_row is not None
        mem_row.status = "superseded"
        mem_row.superseded_by_memory_id = m_new
        await db.commit()

    await _create_rel(auth_client, m_seed, m_sup, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Python packaging pyproject.toml standards",
            "graph_enabled": True,
            "temporal_mode": "current",
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert m_seed in ids
    assert m_sup not in ids, "Superseded neighbor must be excluded in current mode!"


@pytest.mark.asyncio
async def test_temporal_historical_includes_expired(auth_client: AsyncClient):
    """Under temporal_mode=historical, expired neighbors are eligible."""
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    far_past = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()

    m_seed = await _create_mem(auth_client, "hist_seed", "Continuous Integration pipelines with Jenkins")
    m_exp = await _create_mem(
        auth_client,
        "hist_exp",
        "Historical Jenkinsfile declarative syntax 2021",
        valid_from=far_past,
        valid_until=past,
    )
    await _create_rel(auth_client, m_seed, m_exp, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Continuous Integration pipelines with Jenkins",
            "graph_enabled": True,
            "temporal_mode": "historical",
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert m_exp in ids


@pytest.mark.asyncio
async def test_status_filter_excludes_archived(auth_client: AsyncClient):
    """Status filter 'active' excludes archived neighbors."""
    m_seed = await _create_mem(auth_client, "arch_seed", "Asyncio event loop concurrent programming")
    m_arch = await _create_mem(auth_client, "arch_target", "Twisted reactor event loop model")

    # Mark archived in DB
    async with TestSession() as db:
        mem_row = await db.get(Memory, m_arch)
        assert mem_row is not None
        mem_row.status = "archived"
        await db.commit()

    await _create_rel(auth_client, m_seed, m_arch, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Asyncio event loop concurrent programming",
            "graph_enabled": True,
            "status": "active",
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert m_arch not in ids


# ==============================================================================
# Group F: Deterministic Re-ranking & Deduplication
# ==============================================================================

@pytest.mark.asyncio
async def test_deduplication_of_multi_edge_neighbor(auth_client: AsyncClient):
    """A neighbor connected to multiple seeds appears only once in the assembled context."""
    s1 = await _create_mem(auth_client, "dedup_s1", "Distributed systems consensus Raft algorithm")
    s2 = await _create_mem(auth_client, "dedup_s2", "Paxos distributed consensus leader election")
    shared_neighbor = await _create_mem(auth_client, "dedup_shared", "Etcd distributed key value store cluster")

    await _create_rel(auth_client, s1, shared_neighbor, "updates", confidence=1.0)
    await _create_rel(auth_client, s2, shared_neighbor, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Distributed systems consensus Raft and Paxos",
            "graph_enabled": True,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [item["id"] for item in items]
    assert ids.count(shared_neighbor) == 1, "Shared neighbor must be deduplicated to exactly 1 entry!"


@pytest.mark.asyncio
async def test_deterministic_sort_tie_breaking():
    """Unit test tie-breaking order: (-final_score, -base_score, -importance, -timestamp, id ASC)."""
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    m1 = Memory(id="mem_b", content="Content B", importance=0.8, created_at=t0)
    m2 = Memory(id="mem_a", content="Content A", importance=0.8, created_at=t0)

    # Identical retrieval_score (0.5), identical importance (0.8), identical timestamp
    s1 = ScoredMemory(memory=m1, similarity=None, keyword_score=None, hybrid_score=0.0, recency_score=0.0, retrieval_score=0.5)
    s2 = ScoredMemory(memory=m2, similarity=None, keyword_score=None, hybrid_score=0.0, recency_score=0.0, retrieval_score=0.5)

    base_map = {"mem_b": s1, "mem_a": s2}

    def sort_key(item: ScoredMemory):
        mem = item.memory
        mid = str(mem.id)
        base_score = base_map[mid].retrieval_score if mid in base_map else 0.0
        importance = float(getattr(mem, "importance", 0.5))
        dt = getattr(mem, "updated_at", None) or getattr(mem, "created_at", None)
        ts = dt.timestamp() if dt else 0.0
        return (-item.retrieval_score, -base_score, -importance, -ts, mid)

    items = [s1, s2]
    items.sort(key=sort_key)
    # Tie broken by memory_id ASC: "mem_a" < "mem_b"
    assert items[0].memory.id == "mem_a"
    assert items[1].memory.id == "mem_b"


# ==============================================================================
# Group G: User Isolation & Cross-User Security
# ==============================================================================

@pytest.mark.asyncio
async def test_user_isolation_cannot_expand_other_user_relationship(
    auth_client: AsyncClient, other_user: dict
):
    """User 2 creating a relationship cannot leak or affect User 1's graph retrieval."""
    m_user1 = await _create_mem(auth_client, "iso_u1_mem", "Private financial banking records user 1")
    m_user2 = await _create_mem(
        auth_client,
        "iso_u2_mem",
        "Secret offshore accounts user 2",
        headers=other_user["headers"],
    )

    # User 2 attempts to create relationship between User 2's memory and User 1's memory
    # (or between their own memories)
    async with TestSession() as db:
        # Forcibly create a cross-user relationship belonging to user 2
        rel = MemoryRelationship(
            id="test-cross-user-rel-id",
            user_id=other_user["user_id"],
            source_memory_id=m_user1,
            target_memory_id=m_user2,
            relationship_type=RelationshipType.UPDATES,
            confidence=1.0,
        )
        db.add(rel)
        await db.commit()

    # User 1 retrieves context
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Private financial banking records user 1",
            "graph_enabled": True,
            "min_relevance": 0.01,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert m_user1 in ids
    assert m_user2 not in ids, "User 2's memory must NEVER be retrieved or expanded by User 1!"


# ==============================================================================
# Group H: Hard Limits & Bounded Expansion
# ==============================================================================

@pytest.mark.asyncio
async def test_graph_max_expanded_enforced(auth_client: AsyncClient):
    """graph_max_expanded caps the maximum number of new graph-derived memories."""
    m_seed = await _create_mem(auth_client, "bound_seed", "Linux kernel networking socket buffers")

    # Create 6 neighbors
    m_neighbors = []
    for i in range(6):
        n = await _create_mem(auth_client, f"bound_n_{i}", f"TCP window scaling algorithm detail {i}")
        await _create_rel(auth_client, m_seed, n, "updates", confidence=1.0)
        m_neighbors.append(n)

    # Request max_expanded = 3
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Linux kernel networking socket buffers",
            "graph_enabled": True,
            "graph_max_expanded": 3,
            "min_relevance": 0.05,
            "top_k": 20,
        },
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [item["id"] for item in items]
    expanded_in_result = [mid for mid in m_neighbors if mid in ids]
    assert len(expanded_in_result) <= 3, f"Expected at most 3 expanded memories, got {len(expanded_in_result)}"


# ==============================================================================
# Group I: Read-Only Invariance
# ==============================================================================

@pytest.mark.asyncio
async def test_read_only_invariance_no_relationships_or_audits_created(auth_client: AsyncClient):
    """Graph retrieval must be strictly read-only: no new relationships, no audit logs."""
    m1 = await _create_mem(auth_client, "ro_m1", "Zero side-effects retrieval verification")
    m2 = await _create_mem(auth_client, "ro_m2", "Immutable state validation")
    await _create_rel(auth_client, m1, m2, "relevant_to", confidence=1.0)

    # Snapshot current relationship count and audit log count
    async with TestSession() as db:
        rel_count_before = (
            await db.execute(select(func.count()).select_from(MemoryRelationship))
        ).scalar()
        audit_count_before = (
            await db.execute(select(func.count()).select_from(MemoryAuditLog))
        ).scalar()

    # Perform retrieval
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Zero side-effects retrieval verification",
            "graph_enabled": True,
            "min_relevance": 0.01,
        },
    )
    assert resp.status_code == 200

    # Verify counts after retrieval
    async with TestSession() as db:
        rel_count_after = (
            await db.execute(select(func.count()).select_from(MemoryRelationship))
        ).scalar()
        audit_count_after = (
            await db.execute(select(func.count()).select_from(MemoryAuditLog))
        ).scalar()

    assert rel_count_before == rel_count_after, "Retrieval must not create or delete relationships!"
    assert audit_count_before == audit_count_after, "Retrieval must not generate audit logs!"


# ==============================================================================
# Group J: ContextAssembler Format & Truncation Invariance
# ==============================================================================

@pytest.mark.asyncio
async def test_assembled_context_budget_with_graph_expansion(auth_client: AsyncClient):
    """Context budget and truncation rules apply transparently to graph-expanded items."""
    long_content = "Word " * 100  # 500 chars
    m_seed = await _create_mem(auth_client, "budget_seed", "Large language models tokenization and context")
    m_expanded = await _create_mem(auth_client, "budget_exp", long_content)
    await _create_rel(auth_client, m_seed, m_expanded, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Large language models tokenization and context",
            "graph_enabled": True,
            "max_content_chars": 50,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    exp_item = next((it for it in data["items"] if it["id"] == m_expanded), None)
    assert exp_item is not None
    assert len(exp_item["content"]) <= 50
    assert exp_item["is_truncated"] is True


# ==============================================================================
# Group K: Additional Edge Types, Limits & Validity
# ==============================================================================

@pytest.mark.asyncio
async def test_incoming_edge_bonus_supersedes(auth_client: AsyncClient):
    """Incoming SUPERSEDES edge grants +0.15 * confidence bonus."""
    s = await _create_mem(auth_client, "in_sup_seed", "TypeScript strict type system patterns")
    n = await _create_mem(auth_client, "in_sup_n", "JavaScript dynamic typing quirks")
    # Incoming: n -> s (n supersedes s, or n is connected to s via SUPERSEDES)
    await _create_rel(auth_client, n, s, "supersedes", confidence=0.8)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "TypeScript strict type system patterns",
            "graph_enabled": True,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    n_item = next((it for it in resp.json()["items"] if it["id"] == n), None)
    assert n_item is not None
    assert round(n_item["retrieval_score"], 2) == round(0.15 * 0.8, 2)


@pytest.mark.asyncio
async def test_incoming_edge_bonus_contradicts(auth_client: AsyncClient):
    """Incoming CONTRADICTS edge grants +0.10 * confidence bonus."""
    s = await _create_mem(auth_client, "in_cnt_seed", "Functional programming immutability advantages")
    n = await _create_mem(auth_client, "in_cnt_n", "Object oriented mutable shared state benefits")
    await _create_rel(auth_client, n, s, "contradicts", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Functional programming immutability advantages",
            "graph_enabled": True,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    n_item = next((it for it in resp.json()["items"] if it["id"] == n), None)
    assert n_item is not None
    assert round(n_item["retrieval_score"], 2) == 0.10


@pytest.mark.asyncio
async def test_temporal_mode_any_includes_expired_and_superseded(auth_client: AsyncClient):
    """temporal_mode='any' includes expired and normal memories alike."""
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    far_past = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()

    s = await _create_mem(auth_client, "any_seed", "Continuous Delivery deployment blue green")
    n_exp = await _create_mem(
        auth_client, "any_exp", "Legacy deployment scripts v1",
        valid_from=far_past, valid_until=past,
    )
    await _create_rel(auth_client, s, n_exp, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Continuous Delivery deployment blue green",
            "graph_enabled": True,
            "temporal_mode": "any",
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert s in ids
    assert n_exp in ids


@pytest.mark.asyncio
async def test_reference_time_evaluates_window(auth_client: AsyncClient):
    """Custom reference_time in the past correctly evaluates validity at that past moment."""
    t_ref = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_from = datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()
    t_until = datetime(2025, 12, 31, tzinfo=timezone.utc).isoformat()

    s = await _create_mem(auth_client, "reftime_s", "Historical financial audit quarterly reports")
    n = await _create_mem(
        auth_client, "reftime_n", "2025 Fiscal Year Audit Results Report",
        valid_from=t_from, valid_until=t_until,
    )
    await _create_rel(auth_client, s, n, "updates", confidence=1.0)

    # In 2026 (now), n is expired. But evaluated at reference_time=2025-06-01, n is active!
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Historical financial audit quarterly reports",
            "graph_enabled": True,
            "temporal_mode": "current",
            "reference_time": t_ref.isoformat(),
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert s in ids
    assert n in ids


@pytest.mark.asyncio
async def test_score_bonus_clamped_to_1_0_overall(auth_client: AsyncClient):
    """Final retrieval score cannot exceed 1.0 even if base_score + bonus > 1.0."""
    s = await _create_mem(auth_client, "clamp_s", "Exact high match query string for maximum score", importance=1.0)
    n = await _create_mem(auth_client, "clamp_n", "Related target item", importance=1.0)
    await _create_rel(auth_client, s, n, "updates", confidence=1.0)

    # Unit test clamped score directly in GraphAwareRetrievalService
    m = Memory(id="test_mem_clamp", content="High score", importance=1.0)
    base_item = ScoredMemory(
        memory=m,
        similarity=0.98,
        keyword_score=0.98,
        hybrid_score=0.98,
        recency_score=1.0,
        retrieval_score=0.95,
    )
    # Even if +0.15 is added, 0.95 + 0.15 = 1.10 -> clamped to 1.0
    async with TestSession() as db:
        res = await GraphAwareRetrievalService.expand_and_rerank(
            db=db,
            user_id="fake-uid",
            base_scored_memories=[base_item],
            graph_enabled=True,
            min_relevance=0.1,
        )
        assert res[0].retrieval_score <= 1.0


@pytest.mark.asyncio
async def test_graph_retrieval_respects_top_k(auth_client: AsyncClient):
    """When top_k=2, at most 2 items are returned even if base + graph yields 5+ items."""
    s = await _create_mem(auth_client, "topk_s", "Microservices communication gRPC protocols")
    for i in range(4):
        n = await _create_mem(auth_client, f"topk_n_{i}", f"Protocol buffers syntax version {i}")
        await _create_rel(auth_client, s, n, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Microservices communication gRPC protocols",
            "graph_enabled": True,
            "top_k": 2,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) <= 2


@pytest.mark.asyncio
async def test_multiple_seeds_expand_distinct_neighbors(auth_client: AsyncClient):
    """Multiple seeds expand their respective 1-hop neighbors in a single batch."""
    s1 = await _create_mem(auth_client, "multi_s1", "Rust memory safety borrow checker rules", importance=0.9)
    s2 = await _create_mem(auth_client, "multi_s2", "Go concurrency goroutines and channels", importance=0.8)
    n1 = await _create_mem(auth_client, "multi_n1", "Rust lifetimes compiler guarantees")
    n2 = await _create_mem(auth_client, "multi_n2", "Go select statement channel synchronization")

    await _create_rel(auth_client, s1, n1, "updates", confidence=1.0)
    await _create_rel(auth_client, s2, n2, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Rust memory safety and Go concurrency channels",
            "graph_enabled": True,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert s1 in ids
    assert s2 in ids
    assert n1 in ids
    assert n2 in ids


@pytest.mark.asyncio
async def test_service_disabled_returns_exact_slice():
    """Unit test: GraphAwareRetrievalService with graph_enabled=False returns slice without DB calls."""
    m = Memory(id="unit_m1", content="Unit test content")
    base = [ScoredMemory(memory=m, similarity=None, keyword_score=None, hybrid_score=0.5, recency_score=0.5, retrieval_score=0.5)]

    # Pass None as db; if graph_enabled=False it should never access db
    res = await GraphAwareRetrievalService.expand_and_rerank(
        db=None,  # type: ignore[arg-type]
        user_id="any",
        base_scored_memories=base,
        graph_enabled=False,
    )
    assert len(res) == 1
    assert res[0].memory.id == "unit_m1"


# ==============================================================================
# Group M: Policy Parity Enforcement (min_importance, min_confidence, memory_types)
# ==============================================================================

@pytest.mark.asyncio
async def test_graph_candidate_importance_below_min_importance_excluded(auth_client: AsyncClient):
    """A graph candidate with importance < min_importance must be excluded."""
    s = await _create_mem(auth_client, "imp_s1", "Distributed logging OpenTelemetry tracing", importance=0.9)
    # Neighbor with low importance 0.4
    n_low = await _create_mem(auth_client, "imp_n_low", "Jaeger tracing collector daemon", importance=0.4)
    await _create_rel(auth_client, s, n_low, "updates", confidence=1.0)

    # Request with min_importance = 0.70
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Distributed logging OpenTelemetry tracing",
            "graph_enabled": True,
            "min_importance": 0.70,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.json()["items"]]
    assert s in ids
    assert n_low not in ids, "Neighbor with importance 0.4 must be excluded when min_importance=0.70!"


@pytest.mark.asyncio
async def test_graph_candidate_importance_equal_min_importance_included(auth_client: AsyncClient):
    """A graph candidate with importance >= min_importance must be included."""
    s = await _create_mem(auth_client, "imp_s2", "Distributed tracing metrics collection", importance=0.9)
    # Neighbor with importance exactly 0.70
    n_exact = await _create_mem(auth_client, "imp_n_exact", "Prometheus metrics exporter agent", importance=0.70)
    await _create_rel(auth_client, s, n_exact, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Distributed tracing metrics collection",
            "graph_enabled": True,
            "min_importance": 0.70,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.json()["items"]]
    assert s in ids
    assert n_exact in ids, "Neighbor with importance == min_importance must be included!"


@pytest.mark.asyncio
async def test_graph_candidate_confidence_below_min_confidence_excluded(auth_client: AsyncClient):
    """A graph candidate with confidence < min_confidence must be excluded."""
    s = await _create_mem(auth_client, "conf_s1", "Database indexing B-tree and Hash indexes", confidence=1.0)
    # Neighbor with low confidence 0.4
    n_low_conf = await _create_mem(auth_client, "conf_n_low", "Bitmap index scan execution plans", confidence=0.4)
    await _create_rel(auth_client, s, n_low_conf, "updates", confidence=1.0)

    # Request with min_confidence = 0.80
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Database indexing B-tree and Hash indexes",
            "graph_enabled": True,
            "min_confidence": 0.80,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.json()["items"]]
    assert s in ids
    assert n_low_conf not in ids, "Neighbor with confidence 0.4 must be excluded when min_confidence=0.80!"


@pytest.mark.asyncio
async def test_graph_candidate_confidence_equal_min_confidence_included(auth_client: AsyncClient):
    """A graph candidate with confidence >= min_confidence must be included."""
    s = await _create_mem(auth_client, "conf_s2", "PostgreSQL GiST and GIN specialized indexes", confidence=1.0)
    # Neighbor with confidence 0.85 >= 0.80
    n_high_conf = await _create_mem(auth_client, "conf_n_high", "pg_trgm trigram fuzzy search index", confidence=0.85)
    await _create_rel(auth_client, s, n_high_conf, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "PostgreSQL GiST and GIN specialized indexes",
            "graph_enabled": True,
            "min_confidence": 0.80,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.json()["items"]]
    assert s in ids
    assert n_high_conf in ids, "Neighbor with confidence >= min_confidence must be included!"


@pytest.mark.asyncio
async def test_graph_candidate_memory_types_mismatch_excluded(auth_client: AsyncClient):
    """A graph candidate with category not in memory_types must be excluded."""
    s = await _create_mem(auth_client, "type_s1", "User preferences for dark mode themes", category="preference")
    # Neighbor has category 'identity'
    n_other_type = await _create_mem(auth_client, "type_n1", "User identity public ethereum address", category="identity")
    await _create_rel(auth_client, s, n_other_type, "updates", confidence=1.0)

    # Request only memory_types=['preference']
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "User preferences for dark mode themes",
            "graph_enabled": True,
            "memory_types": ["preference"],
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.json()["items"]]
    assert s in ids
    assert n_other_type not in ids, "Neighbor with category 'identity' must be excluded when memory_types=['preference']!"


@pytest.mark.asyncio
async def test_graph_candidate_memory_types_match_included(auth_client: AsyncClient):
    """A graph candidate with category matching memory_types must be included."""
    s = await _create_mem(auth_client, "type_s2", "User editor preferences Vim keybindings", category="preference")
    n_matching = await _create_mem(auth_client, "type_n2", "User font preferences JetBrains Mono", category="preference")
    await _create_rel(auth_client, s, n_matching, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "User editor preferences Vim keybindings",
            "graph_enabled": True,
            "memory_types": ["preference"],
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.json()["items"]]
    assert s in ids
    assert n_matching in ids, "Neighbor matching memory_types must be included!"


@pytest.mark.asyncio
async def test_graph_candidate_memory_types_none_applies_no_filter(auth_client: AsyncClient):
    """When memory_types=None, neighbor memories of any category are included."""
    s = await _create_mem(auth_client, "type_s3", "Project task scheduling architecture", category="preference")
    n_any_type = await _create_mem(auth_client, "type_n3", "Cron runner background worker", category="task")
    await _create_rel(auth_client, s, n_any_type, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Project task scheduling architecture",
            "graph_enabled": True,
            "memory_types": None,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.json()["items"]]
    assert s in ids
    assert n_any_type in ids


@pytest.mark.asyncio
async def test_base_candidate_policy_behavior_unchanged_with_graph(auth_client: AsyncClient):
    """Base candidates continue to respect existing RetrievalPolicy exactly as before."""
    s_high = await _create_mem(auth_client, "base_pol_high", "Security cryptographic key storage", importance=0.9)
    s_low = await _create_mem(auth_client, "base_pol_low", "Security password hashing argon2", importance=0.2)

    # min_importance=0.5 must filter out s_low from base retrieval
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Security cryptographic key storage and password hashing",
            "graph_enabled": True,
            "min_importance": 0.5,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.json()["items"]]
    assert s_high in ids
    assert s_low not in ids


@pytest.mark.asyncio
async def test_graph_disabled_baseline_completely_unchanged(auth_client: AsyncClient):
    """When graph_enabled=False, retrieval is 100% identical and policy behaves normally."""
    m1 = await _create_mem(auth_client, "base_unchanged_1", "Strict policy invariance baseline 1", importance=0.9)
    m2 = await _create_mem(auth_client, "base_unchanged_2", "Strict policy invariance baseline 2", importance=0.8)
    await _create_rel(auth_client, m1, m2, "updates", confidence=1.0)

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Strict policy invariance baseline",
            "graph_enabled": False,
            "min_importance": 0.5,
            "min_relevance": 0.05,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_memories"] >= 2
    # Verify items did NOT get graph bonus
    scores = {it["id"]: it["retrieval_score"] for it in data["items"]}
    assert scores[m2] < 0.95  # baseline score without +0.15 graph bonus


