# Memory Passport — System Capabilities & Feature Matrix

**Release Version:** `v1.14.0-hackathon-demo`
**Audited Against Codebase:** Verified against real implementations in `backend/app`, `frontend/src`, `sdk/`, and `scripts/`.

---

## 1. Core Memory Intelligence Subsystem

| Capability | Implementation Status | Technical Implementation |
| :--- | :---: | :--- |
| **Memory CRUD** | **IMPLEMENTED** | Full lifecycle operations in `MemoryRepository` and `MemoryService`. Supports text content, type classifications (`identity`, `preference`, `fact`, `context`), and JSON metadata. |
| **Semantic Search** | **IMPLEMENTED** | Cosine similarity vector search over 1024-dimension embeddings (Qwen / OpenAI-compatible embedding models). Supports fallback to keyword search when embedding services are offline. |
| **Hybrid Search** | **IMPLEMENTED** | Weighted fusion algorithm: 70% vector similarity + 30% full-text keyword ranking, combined with monotonic recency decay scoring. |
| **Retrieval Policy** | **IMPLEMENTED** | Configurable token budget limits, similarity threshold cutoffs, max item count limits, and explainability payloads (`/memories/explain`). |
| **Temporal Memory** | **IMPLEMENTED** | `valid_from` and `valid_until` ISO 8601 timestamps, explicit version lineage tracking, and supersession chains (`supersedes_id`). |
| **Conflict Intelligence** | **IMPLEMENTED** | Deterministic detection of conflicting statements, automated resolution strategies (`overwrite`, `append`, `branch`), and conflict state tracking (`ACTIVE`, `SUPERSEDED`, `CONFLICTED`). |
| **Relationship Graph** | **IMPLEMENTED** | Directed graph edges between memories and entities with relationship types (`derived_from`, `relates_to`, `conflicts_with`) and confidence scores. Supports 1-hop graph traversal. |
| **Graph-Aware Retrieval** | **IMPLEMENTED** | Memory search expansion queries that traverse adjacent graph neighbors to enrich prompt contexts. |
| **Governance & Audit** | **IMPLEMENTED** | Tenant isolation strictly scoped to `user_id` UUIDs; immutable revision log records every memory creation, modification, and deletion. |

---

## 2. AI Interaction & Conversation Subsystem

| Capability | Implementation Status | Technical Implementation |
| :--- | :---: | :--- |
| **AI Memory Extraction** | **IMPLEMENTED** | Background or inline LLM extraction pipeline that identifies atomic user facts, preferences, and personal attributes from raw conversation turns. |
| **Memory-Aware Chat** | **IMPLEMENTED** | `/api/chat` router with dynamic prompt injection, injecting top-ranked memories based on conversation relevance. |
| **Multi-Turn Session Memory** | **IMPLEMENTED** | Context continuation across disparate sessions and UI tabs, keeping conversations grounded in user-owned memory. |

---

## 3. Developer & Integration Subsystem

| Capability | Implementation Status | Technical Implementation |
| :--- | :---: | :--- |
| **Standard MCP Gateway** | **IMPLEMENTED** | Streamable HTTP endpoint (`POST /mcp`) adhering strictly to the JSON-RPC 2.0 and Model Context Protocol 2026-07-28 specification. Exposes 15 standard memory tools. |
| **Python SDK** | **IMPLEMENTED** | `memory-passport` typed client library under `sdk/` covering search, memories, graph traversal, conflict detection, and evaluation runs. |
| **Evaluation Platform** | **IMPLEMENTED** | Built-in evaluation platform (`/dashboard/evaluation`) supporting datasets, golden test cases, execution runs, and IR metrics (Precision@k, Recall@k, MRR, NDCG). |

---

## 4. Web3 Sovereign Identity Subsystem

| Capability | Implementation Status | Technical Implementation |
| :--- | :---: | :--- |
| **EVM Wallet Connection** | **IMPLEMENTED** | RainbowKit / Wagmi frontend integration supporting MetaMask, WalletConnect, and injected Ethereum providers. |
| **Monad Testnet Anchor** | **IMPLEMENTED** | Primary Web3 network integration targeting Monad Testnet (Chain ID `10143`), anchoring user passport identity. |
| **SIWE Signature Auth** | **IMPLEMENTED** | EIP-4361 Sign-In with Ethereum protocol verification. Cryptographic signature validates wallet ownership without exposing private keys. |
| **Off-Chain Sovereign Memory** | **DESIGN PRINCIPLE** | Memory contents are stored off-chain in vector/relational databases for privacy, low latency, and zero gas fees; Web3 acts strictly as an identity and root ownership anchor. |

---

## 5. Autonomous Agent Access Control Subsystem

| Capability | Implementation Status | Technical Implementation |
| :--- | :---: | :--- |
| **Agent Identity Registry** | **IMPLEMENTED** | First-class agent entity model (`Agent`) with UUID `id`, `name`, `description`, and lifecycle status (`ACTIVE`, `REVOKED`). |
| **Hashed API Key Auth** | **IMPLEMENTED** | Dedicated API keys with `mp_ak_` prefix. Only SHA-256 hashes are stored in the database; keys cannot be decrypted or leaked from storage. |
| **CallerContext Protocol** | **IMPLEMENTED** | MCP middleware extracts credentials and constructs typed `CallerContext(is_agent=True, agent_id, permissions)`. |
| **Granular Permission Matrix** | **IMPLEMENTED** | Strict four-tier capability enforcement: `READ_MEMORY`, `READ_PREFERENCES`, `CREATE_MEMORY`, `UPDATE_MEMORY`. |
| **Dynamic Permission Grants** | **IMPLEMENTED** | Human users can delegate or revoke individual permissions on the fly via REST API and frontend UI without restarting services. |
| **Emergency Kill Switch** | **IMPLEMENTED** | Instant revocation endpoint (`POST /api/agents/{id}/revoke`). Transition to `REVOKED` immediately causes all future requests to fail with `HTTP 401`. |
| **Zero-Leakage Audit Trail** | **IMPLEMENTED** | Dedicated `agent_audit_logs` table logging all access decisions (`ALLOW`/`DENY`), grants, and revocations with zero credential exposure. |

---

## 6. Hackathon Live Demo & Stability Subsystem

| Capability | Implementation Status | Technical Implementation |
| :--- | :---: | :--- |
| **One-Command Launcher** | **IMPLEMENTED** | `python scripts/start_demo.py` orchestrates runtime validation, backend uvicorn startup, Next.js compilation, demo data seeding, and MCP readiness probing. |
| **Real HTTP MCP Demo Script** | **IMPLEMENTED** | `python scripts/demo_agent_mcp_auth.py` demonstrates the full 8-step live HTTP lifecycle: Auth -> Read (200) -> Write Denied (403) -> Grant -> Write Allowed (200) -> Update -> Revoke -> Access Blocked (401) -> Audit Trail. |
| **Cold-Start & Port Self-Healing** | **IMPLEMENTED** | Automatic detection of active ports (`8000`, `3000`), seamless service reuse, and graceful termination via process trees on `Ctrl+C`. |
| **Zero-Secret Hardcoding** | **IMPLEMENTED** | Masked credential outputs (`mp_ak_8f3f...46e9`), runtime environment injection, and complete exclusion of sensitive tokens from version control. |
