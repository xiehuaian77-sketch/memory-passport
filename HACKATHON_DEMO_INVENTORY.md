# Memory Passport - Hackathon Demo Inventory & Presentation Guide

**Release Version:** `v1.10.1-evaluation-platform`  
**Target Environment:** Local Dev / Standalone Demo  
**Audience:** Hackathon Judges, Engineers, Product Evaluators  

---

## 1. Demo User Profile & Access Credentials

| Field | Value | Notes |
|---|---|---|
| **Email** | `demo@memorypassport.ai` | Primary Demo Account |
| **Password** | `demo123456` | bcrypt hashed in SQLite/PostgreSQL |
| **Display Name** | `Demo User` (Alex Chen) | Senior Full-Stack AI Engineer persona |
| **Passport ID** | `mp_demo_hackathon` | Portable cross-agent identity |
| **Web3 Wallet** | `0x71C2E63B48421882c7aE9D58E16503c403Be43F0` | Bound wallet address |
| **User ID** | Dynamic UUID | Reused idempotently across runs |

---

## 2. Seed Data Inventory

### A. Core Memories (10 High-Quality Records)

| Key | Type | Lifecycle Status | Importance | Version | Content Summary |
|---|---|---|---|---|---|
| `role_and_stack` | `identity` | `active` | 0.95 | 1 | Senior Full-Stack AI Engineer (Python, FastAPI, React, Vector DBs). |
| `editor_theme_preference` | `preference` | `active` | 0.80 | 1 | VS Code, dark modern theme, 2 spaces, strict TypeScript/Ruff. |
| `primary_database` | `context` | `active` | 0.90 | 1 | PostgreSQL with pgvector (production) / SQLite (development). |
| `python_runtime_version_v1` | `context` | `superseded` | 0.70 | 1 | Backend service runtime is Python 3.10 (historical). |
| `python_runtime_version_v2` | `context` | `active` | 0.92 | 2 | Upgraded backend runtime to Python 3.12 (current active). |
| `deployment_cloud_target` | `context` | `active` | 0.85 | 1 | Containerized Linux servers using Docker with non-root users. |
| `work_schedule_preference` | `preference` | `active` | 0.85 | 1 | Deep work focus mornings 9:00 AM - 12:00 PM without meetings. |
| `client_meeting_availability` | `preference` | `conflicted` | 0.75 | 1 | Available for urgent client standup syncs daily at 10:00 AM. |
| `agent_response_guideline` | `context` | `active` | 0.88 | 1 | Concise, actionable technical advice with code snippets before theory. |
| `hackathon_project_milestone` | `task` | `active` | 0.90 | 1 | Complete Hackathon Phase 6 demo integration showing real-time metrics. |

### B. Temporal Supersession Link
- **Historical Memory:** `python_runtime_version_v1` (Python 3.10)
  - `status`: `superseded`
  - `valid_from`: `2025-01-01T00:00:00Z`
  - `valid_until`: `2026-03-01T00:00:00Z`
  - `superseded_by_memory_id`: Points to `python_runtime_version_v2`
- **Active Memory:** `python_runtime_version_v2` (Python 3.12)
  - `status`: `active`
  - `valid_from`: `2026-03-01T00:00:00Z`
  - `valid_until`: `None`

### C. Conflict Intelligence Candidate
- **Conflict Edge:** `client_meeting_availability` $\leftrightarrow$ `work_schedule_preference`
  - **Type:** `CONTRADICTS` (Confidence: 0.95)
  - **Friction:** Morning focus hours (9-12) vs Daily 10:00 AM client standup.
  - **Agent Decision:** Intercepts schedule overlap before calendar booking.

### D. Relationship Graph (5 Directed Edges)
1. `python_runtime_version_v2` $\xrightarrow{\text{SUPERSEDES}}$ `python_runtime_version_v1` (Confidence: 1.00)
2. `python_runtime_version_v2` $\xrightarrow{\text{RELEVANT_TO}}$ `role_and_stack` (Confidence: 0.90)
3. `deployment_cloud_target` $\xrightarrow{\text{RELEVANT_TO}}$ `primary_database` (Confidence: 0.85)
4. `client_meeting_availability` $\xrightarrow{\text{CONTRADICTS}}$ `work_schedule_preference` (Confidence: 0.95)
5. `agent_response_guideline` $\xrightarrow{\text{RELEVANT_TO}}$ `role_and_stack` (Confidence: 0.80)

### E. Evaluation Dataset & Test Cases
- **Dataset:** `Developer Profile & Tech Stack Golden Dataset`
- **Case 1:** *"What Python version is currently used in the backend services?"* $\to$ expects `python_runtime_version_v2`
- **Case 2:** *"What are Alex's editor and tooling preferences?"* $\to$ expects `editor_theme_preference`
- **Case 3:** *"What is the primary database used by Memory Passport?"* $\to$ expects `primary_database`
- **Case 4:** *"What is Alex's preferred morning schedule for deep work?"* $\to$ expects `work_schedule_preference`
- **Case 5:** *"What guidelines should the AI agent follow when answering?"* $\to$ expects `agent_response_guideline`

### F. Pre-Executed Evaluation Runs
1. **Run 1: Baseline Keyword Retrieval**
   - Config: `{"search_mode": "keyword", "top_k": 5, "status": "active"}`
   - Recall@5: 0.80 | MRR: 0.54 | Mean Latency: ~2.3 ms | Pass Rate: 80%
2. **Run 2: Enhanced Context Retrieval (Hybrid)**
   - Config: `{"search_mode": "retrieve", "top_k": 5, "status": "active", "graph_enabled": true}`
   - Recall@5: 1.00 | MRR: 0.46 | Mean Latency: ~16.7 ms | Pass Rate: 100%

---

## 3. 3-5 Minute Pitch & Live Demo Script

### Minute 0:00 - 0:45: The Problem & The Passport
1. **Pitch:** *"Every AI agent today is amnesic or siloed. When you switch from Cursor to Claude or ChatGPT, you re-explain your preferences, your tech stack, and your business rules. Memory Passport is the open, portable memory layer for AI agents."*
2. **UI Action:**
   - Navigate to `/` and log in with `demo@memorypassport.ai` / `demo123456`.
   - Show User Identity card (`Passport ID: mp_demo_hackathon`, bound Web3 wallet, verified credential).

### Minute 0:45 - 1:45: Active Memories & Temporal Evolution
1. **Pitch:** *"Most vector search apps break when facts change over time because old facts still match embedding cosine similarity. Memory Passport solves this with first-class Temporal Memory and Supersession."*
2. **UI Action:**
   - Go to `/dashboard` $\to$ Memories table.
   - Filter by status: show the active memories, and then toggle `superseded` memories.
   - Highlight: `python_runtime_version_v1` (Python 3.10) is marked `SUPERSEDED`, pointing directly to `python_runtime_version_v2` (Python 3.12).
   - Show Audit Log / Provenance: inspect the `SUPERSEDE` event recorded in the immutable audit log.

### Minute 1:45 - 2:45: Conflict Intelligence & Knowledge Graph
1. **Pitch:** *"Users frequently tell agents contradictory things over weeks of chatting. Instead of hallucinating, Memory Passport detects semantic contradictions and builds a Knowledge Graph."*
2. **UI Action:**
   - In `/dashboard`, inspect `client_meeting_availability` marked `conflicted`.
   - Point to the relationship edge: `client_meeting_availability` CONTRADICTS `work_schedule_preference`.
   - Explain how an AI agent uses this graph to ask clarifying questions rather than double-booking the user during morning focus time.

### Minute 2:45 - 3:45: Scientific Evaluation & Quality Benchmark
1. **Pitch:** *"How do developers know their memory retrieval actually works? In Phase 5, we engineered a complete Evaluation & Quality Platform directly into the product."*
2. **UI Action:**
   - Navigate to `/dashboard/evaluation`.
   - Select `Developer Profile & Tech Stack Golden Dataset`.
   - Show Run Comparison: compare **Run 1 (Baseline Keyword)** vs **Run 2 (Enhanced Hybrid)**.
   - Point to real IR metrics: Precision@K, Recall@K, MRR, nDCG, and Latency distribution.
   - Show the 7 Quality Dimensions radar / score breakdown.

### Minute 3:45 - 4:45: Autonomous Agent Integration (SDK & CLI)
1. **Pitch:** *"How does an external agent interact with this? Exactly 3 lines of Python code using our official Python SDK or MCP server."*
2. **Terminal Action:**
   - Run in terminal:
     ```bash
     python scripts/demo_agent_run.py
     ```
   - Watch the agent:
     - Ingest context via `MemoryPassportClient`.
     - Filter out superseded Python 3.10 and choose Python 3.12.
     - Detect the schedule conflict before executing a simulated meeting booking.
   - Highlight: exit code 0, 100% offline-safe, zero external API key requirements.

---

## 4. One-Click Verification Commands

```bash
# 1. Initialize or Re-seed Demo Data (100% Idempotent)
python scripts/seed_demo_data.py

# 2. Run Autonomous CLI Agent Demo
python scripts/demo_agent_run.py

# 3. Verify Demo Seed Automated Test Suite
pytest backend/tests/test_demo_seed.py -v

# 4. Verify SDK Suite & Code Formatting
pytest tests/sdk -q
ruff check .

# 5. Verify Frontend Suite
cd frontend && npm run test && npm run typecheck
```

---

## 5. Security & Safety Boundaries

- **Zero Hardcoded Secrets:** No live OpenAI, DashScope, Anthropic, or GitHub tokens are embedded.
- **Offline Deterministic Fallback:** `DeterministicEmbeddingProvider` ensures complete offline demonstration capability.
- **Strict Tenant Isolation:** All SQL queries and SDK requests strictly enforce `user_id` scoping.
- **Repository Safety:** Core business logic, migrations, models, and released Git tags remain strictly immutable.
